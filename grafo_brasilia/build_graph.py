# -*- coding: utf-8 -*-
"""
build_graph.py - Constroi o grafo viario de Brasilia (DF) a partir do OpenStreetMap.

Uso:
    python grafo_brasilia/build_graph.py                      # DF inteiro, malha de carros
    python grafo_brasilia/build_graph.py --lugar "Plano Piloto, Brasilia, Distrito Federal, Brazil"
    python grafo_brasilia/build_graph.py --tipo drive_service --sem-plot
    python grafo_brasilia/build_graph.py --consolidar 15      # funde intersecoes num raio de 15 m

Saida (pasta grafo_brasilia/saida/):
    <nome>.graphml       grafo completo (recarregue com ox.load_graphml)
    <nome>.gpkg          nos e arestas como camadas GIS (abre no QGIS)
    <nome>_arestas.csv   tabela de arestas (u, v, length, speed_kph, ...)
    <nome>.png           figura da rede
    <nome>_stats.json    estatisticas descritivas
"""

import argparse
import json
import time
import unicodedata
from pathlib import Path

import matplotlib
matplotlib.use("Agg")            # nao abre janela; so grava arquivo

import networkx as nx
import osmnx as ox

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "saida"
CACHE = AQUI / "cache_osm"

# Servidores Overpass publicos (URL base, sem /interpreter - o OSMnx completa).
# O primeiro e o oficial do OSM; os outros sao espelhos comunitarios que servem
# os mesmos dados. Quando o oficial recusa conexao, o script cai para o proximo.
#
# CUIDADO: o cache do OSMnx e indexado pela URL completa da requisicao. Trocar de
# servidor invalida o que ja foi baixado do anterior. Por isso o script insiste
# no mesmo servidor algumas vezes antes de trocar.
#
# O OSMnx fixa o IP do servidor (socket.gethostbyname) para nao violar o controle
# de fila do Overpass. Se o round-robin do overpass-api.de entregar um IP fora do
# ar, TODAS as tentativas no mesmo processo batem no mesmo IP morto - por isso o
# script troca de servidor rapido em vez de insistir.
ESPELHOS = [
    "https://overpass-api.de/api",                    # oficial
    "https://maps.mail.ru/osm/tools/overpass/api",    # espelho, costuma responder rapido
    "https://overpass.kumi.systems/api",              # espelho
]
INSISTENCIA = 2          # tentativas por servidor antes de trocar


# --------------------------------------------------------------------------- #
# 1. Configuracao global do OSMnx
# --------------------------------------------------------------------------- #
def desligar_pin_de_ip() -> None:
    """
    Impede o OSMnx de fixar o IP do servidor Overpass.

    Por padrao o OSMnx resolve o hostname uma vez (socket.gethostbyname) e usa
    aquele IP em todas as requisicoes, para nao furar o controle de fila do
    servidor. O overpass-api.de faz round-robin entre maquinas (gall, lambert...)
    e, quando o IP sorteado esta sobrecarregado, TODA tentativa do processo bate
    nele e volta ConnectTimeout - trocar de servidor nao adianta porque invalida
    o cache. Desligando o pin, cada requisicao resolve o DNS de novo e pode cair
    numa maquina saudavel.

    Custo: a consulta de fila e a consulta de dados podem ir para maquinas
    diferentes. So use quando o pin estiver realmente impedindo o download.
    """
    from osmnx import _http
    _http._config_dns = lambda url: None


def configurar_osmnx(max_area_km2: float = 900.0, timeout_s: int = 180,
                     rate_limit: bool = True) -> None:
    """Ajusta as settings globais do OSMnx (valem para todas as chamadas seguintes)."""
    ox.settings.use_cache = True                 # guarda a resposta do Overpass em disco
    ox.settings.cache_folder = str(CACHE)        # ...aqui. Rodar de novo fica instantaneo.
    # Timeout curto de proposito: o Overpass as vezes aceita a conexao e nunca
    # responde. Melhor falhar rapido e deixar o retry pegar de novo do que ficar
    # 10 minutos pendurado num socket.
    # PRECISA ser int: o OSMnx injeta esse valor no cabecalho da consulta
    # Overpass ("[out:json][timeout:180]"). Um float vira "[timeout:180.0]" e o
    # servidor responde 400 Bad Request.
    ox.settings.requests_timeout = int(timeout_s)
    ox.settings.log_console = False
    # Antes de cada requisicao o OSMnx consulta /status para respeitar a fila do
    # servidor. Espelhos que nao expoem esse endpoint no formato esperado fazem o
    # OSMnx dormir um tempo fixo (ou recursivamente) a cada consulta - e o
    # download parece travado. Desligue APENAS em espelho, e so com poucas
    # requisicoes; no servidor oficial, mantenha ligado.
    ox.settings.overpass_rate_limit = rate_limit
    # O Overpass derruba a conexao em consultas muito grandes. O OSMnx fatia o
    # poligono em pedacos de no maximo este tamanho e faz uma requisicao por pedaco.
    ox.settings.max_query_area_size = max_area_km2 * 1e6
    # tags extras que interessam para modelagem de trafego (capacidade, VDF, etc.)
    extras = ["lanes:forward", "lanes:backward", "maxspeed:type", "surface", "width", "turn"]
    ox.settings.useful_tags_way = list(dict.fromkeys(list(ox.settings.useful_tags_way) + extras))


def slug(texto: str) -> str:
    """Converte um nome de lugar em nome de arquivo seguro (sem acento nem espaco)."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = "".join(c if c.isalnum() else "_" for c in t.lower())
    return "_".join(p for p in t.split("_") if p)


# --------------------------------------------------------------------------- #
# 2. Download + enriquecimento do grafo
# --------------------------------------------------------------------------- #
def _baixar_por_bbox(lugar: str, tipo: str) -> nx.MultiDiGraph:
    """
    Estrategia rapida para areas grandes: consultar o retangulo que contem o
    lugar e recortar o poligono depois, localmente.

    Motivo: o `graph_from_place` manda o contorno administrativo inteiro para o
    Overpass num filtro `(poly:"lat lon lat lon ...")`. O contorno do DF tem
    centenas de vertices, e avaliar esse poligono contra cada via custa caro no
    servidor - consultas de minutos, quando nao estouram o timeout. Um retangulo
    tem 4 vertices e responde em segundos. O recorte exato acontece aqui, com
    `truncate_graph_polygon`, sem custo para o servidor.
    """
    gdf = ox.geocoder.geocode_to_gdf(lugar)
    poligono = gdf.geometry.iloc[0]
    oeste, sul, leste, norte = poligono.bounds
    print(f"      bbox {oeste:.4f},{sul:.4f} -> {leste:.4f},{norte:.4f}")

    # retain_all=True: nao descartar componentes agora; o recorte vem depois
    G = ox.graph.graph_from_bbox((oeste, sul, leste, norte), network_type=tipo,
                                 simplify=True, retain_all=True)
    print(f"      retangulo: {G.number_of_nodes():,} nos. Recortando o poligono...")
    G = ox.truncate.truncate_graph_polygon(G, poligono)
    return ox.truncate.largest_component(G, strongly=False)


def baixar_grafo(lugar: str, tipo: str, tentativas: int = 9,
                 servidor_fixo: str | None = None,
                 via_bbox: bool = False) -> nx.MultiDiGraph:
    """
    Baixa a malha viaria do OSM e devolve um MultiDiGraph do NetworkX.

    O Overpass e um servico publico e gratuito: ele derruba conexoes quando esta
    sobrecarregado. Como o OSMnx guarda em cache cada pedaco ja baixado, basta
    repetir a chamada - as partes que ja vieram nao sao rebaixadas.
    """
    modo = "bbox + recorte" if via_bbox else "poligono"
    print(f"[1/5] Baixando '{lugar}' (network_type={tipo}, modo={modo})...")
    t0 = time.perf_counter()
    for i in range(1, tentativas + 1):
        if servidor_fixo:
            servidor = servidor_fixo
        else:
            servidor = ESPELHOS[min((i - 1) // INSISTENCIA, len(ESPELHOS) - 1)]
        ox.settings.overpass_url = servidor
        host = servidor.split("/")[2]
        try:
            print(f"      tentativa {i}/{tentativas} via {host}")
            if via_bbox:
                G = _baixar_por_bbox(lugar, tipo)
            else:
                G = ox.graph_from_place(lugar, network_type=tipo,
                                        simplify=True, retain_all=False)
            break
        except Exception as e:
            if i == tentativas:
                raise
            espera = min(30, 5 * 2 ** ((i - 1) % INSISTENCIA))
            print(f"      falhou ({type(e).__name__}). Nova tentativa em {espera}s "
                  f"(o que ja baixou desse servidor esta em cache)...")
            time.sleep(espera)
    print(f"      OK em {time.perf_counter() - t0:,.1f}s "
          f"-> {G.number_of_nodes():,} nos e {G.number_of_edges():,} arestas")
    return G


def enriquecer(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Adiciona velocidade (km/h) e tempo de viagem em fluxo livre (s) em cada aresta."""
    print("[2/5] Imputando velocidades e tempos de viagem...")
    # Se a via tem tag maxspeed, usa; senao, imputa a media do mesmo tipo de via.
    G = ox.routing.add_edge_speeds(G)
    G = ox.routing.add_edge_travel_times(G)
    return G


def consolidar(G: nx.MultiDiGraph, tolerancia_m: float) -> nx.MultiDiGraph:
    """
    Funde intersecoes proximas (ex.: as 4 pontas de um cruzamento de pista dupla
    viram 1 no). Precisa projetar o grafo para metros antes.
    ATENCAO: isso troca os IDs dos nos - eles deixam de ser osmid.
    """
    print(f"[2b]  Consolidando intersecoes (tolerancia = {tolerancia_m} m)...")
    Gp = ox.projection.project_graph(G)                       # WGS84 -> UTM (metros)
    Gc = ox.simplification.consolidate_intersections(
        Gp, tolerance=tolerancia_m, rebuild_graph=True, dead_ends=False
    )
    print(f"      {G.number_of_nodes():,} -> {Gc.number_of_nodes():,} nos")
    return Gc


# --------------------------------------------------------------------------- #
# 3. Estatisticas
# --------------------------------------------------------------------------- #
def estatisticas(G: nx.MultiDiGraph) -> dict:
    print("[3/5] Calculando estatisticas da rede...")
    Gp = G if ox.projection.is_projected(G.graph["crs"]) else ox.projection.project_graph(G)
    area_m2 = ox.convert.graph_to_gdfs(Gp, nodes=True, edges=False).union_all().convex_hull.area
    st = ox.stats.basic_stats(Gp, area=area_m2)

    st["n_componentes_fracos"] = nx.number_weakly_connected_components(G)
    st["n_componentes_fortes"] = nx.number_strongly_connected_components(G)
    maior = max(nx.strongly_connected_components(G), key=len)
    st["maior_componente_forte_pct"] = 100 * len(maior) / G.number_of_nodes()
    st["area_convexhull_km2"] = area_m2 / 1e6

    # composicao por tipo de via
    tipos: dict = {}
    for _, _, d in G.edges(data=True):
        h = d.get("highway")
        h = h[0] if isinstance(h, list) else h
        tipos[h] = tipos.get(h, 0) + 1
    st["arestas_por_highway"] = dict(sorted(tipos.items(), key=lambda x: -x[1]))
    return st


# --------------------------------------------------------------------------- #
# 4. Persistencia
# --------------------------------------------------------------------------- #
def salvar(G: nx.MultiDiGraph, nome: str, plotar: bool) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)

    print("[4/5] Salvando arquivos...")
    ox.io.save_graphml(G, SAIDA / f"{nome}.graphml")

    _, arestas = ox.convert.graph_to_gdfs(G)
    try:
        ox.io.save_graph_geopackage(G, SAIDA / f"{nome}.gpkg")
    except Exception as e:                                    # pyogrio/fiona ausente
        print(f"      (GeoPackage pulado: {e})")

    cols = [c for c in ["osmid", "name", "ref", "highway", "oneway", "lanes",
                        "maxspeed", "length", "speed_kph", "travel_time"]
            if c in arestas.columns]
    arestas[cols].to_csv(SAIDA / f"{nome}_arestas.csv", encoding="utf-8-sig")

    if plotar:
        print("[5/5] Renderizando figura...")
        ox.plot.plot_graph(
            G, node_size=0, edge_linewidth=0.25, edge_color="#4da6ff",
            bgcolor="#0b0f14", figsize=(16, 16), show=False, close=True,
            filepath=str(SAIDA / f"{nome}.png"), save=True, dpi=180,
        )
    else:
        print("[5/5] Figura pulada (--sem-plot).")


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(description="Gera o grafo viario de Brasilia via OSMnx.")
    p.add_argument("--lugar", default="Brasilia, Brazil",
                   help="consulta ao Nominatim (padrao: DF inteiro)")
    p.add_argument("--tipo", default="drive",
                   choices=["drive", "drive_service", "all", "all_public", "bike", "walk"],
                   help="filtro de vias (padrao: drive = vias trafegaveis por carro)")
    p.add_argument("--nome", default=None, help="nome base dos arquivos de saida")
    p.add_argument("--consolidar", type=float, default=0.0,
                   help="tolerancia em metros para fundir intersecoes (0 = nao consolidar)")
    p.add_argument("--sem-plot", action="store_true", help="nao gerar o PNG")
    p.add_argument("--max-area", type=float, default=900.0,
                   help="tamanho maximo (km2) de cada requisicao ao Overpass")
    p.add_argument("--timeout", type=int, default=180,
                   help="segundos de espera por resposta do Overpass antes de tentar de novo")
    p.add_argument("--via-bbox", action="store_true",
                   help="baixar pelo retangulo envolvente e recortar depois "
                        "(muito mais rapido em areas grandes como o DF inteiro)")
    p.add_argument("--overpass", default=None,
                   help=f"forcar um servidor Overpass (base, sem /interpreter). "
                        f"Conhecidos: {', '.join(ESPELHOS)}")
    p.add_argument("--sem-rate-limit", action="store_true",
                   help="nao consultar /status antes de cada requisicao "
                        "(use so em espelho que nao implementa o endpoint)")
    p.add_argument("--sem-pin-dns", action="store_true",
                   help="nao fixar o IP do servidor (contorna ConnectTimeout "
                        "repetido causado por round-robin com maquina fora do ar)")
    args = p.parse_args()

    configurar_osmnx(max_area_km2=args.max_area, timeout_s=args.timeout,
                     rate_limit=not args.sem_rate_limit)
    if args.sem_pin_dns:
        desligar_pin_de_ip()
    nome = args.nome or f"{slug(args.lugar)}_{args.tipo}"

    G = baixar_grafo(args.lugar, args.tipo, servidor_fixo=args.overpass,
                     via_bbox=args.via_bbox)
    G = enriquecer(G)
    if args.consolidar > 0:
        G = consolidar(G, args.consolidar)
        nome += f"_cons{int(args.consolidar)}"

    st = estatisticas(G)
    salvar(G, nome, plotar=not args.sem_plot)
    (SAIDA / f"{nome}_stats.json").write_text(
        json.dumps(st, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print("\n" + "=" * 62)
    print(f"GRAFO: {args.lugar}  [{args.tipo}]")
    print("=" * 62)
    print(f"  nos (intersecoes/fins de via) : {G.number_of_nodes():>12,}")
    print(f"  arestas (trechos de via)      : {G.number_of_edges():>12,}")
    print(f"  extensao total da malha       : {st['edge_length_total']/1000:>12,.1f} km")
    print(f"  comprimento medio da aresta   : {st['edge_length_avg']:>12,.1f} m")
    print(f"  grau medio (streets/no)       : {st['streets_per_node_avg']:>12,.2f}")
    print(f"  densidade de vias             : {st['edge_density_km']/1000:>12,.2f} km/km2")
    print(f"  circuidade media              : {st['circuity_avg']:>12,.3f}")
    print(f"  maior componente fortemente conexo: {st['maior_componente_forte_pct']:.2f}% dos nos")
    print(f"\n  arquivos em: {SAIDA}")


if __name__ == "__main__":
    main()
