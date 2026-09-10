# -*- coding: utf-8 -*-
"""
exemplos_networkx.py - Tutorial executavel: o que da para fazer com o grafo de
Brasilia depois que o OSMnx o entrega como um objeto do NetworkX.

Rode primeiro o build_graph.py, depois:

    python grafo_brasilia/exemplos_networkx.py
    python grafo_brasilia/exemplos_networkx.py --grafo brasilia_df_drive
    python grafo_brasilia/exemplos_networkx.py --secao 6

Cada secao e independente e imprime o que aprendeu. Leia o codigo junto da saida.

Rode o conjunto todo no grafo do Plano Piloto: e pequeno e responde em segundos.
No grafo do DF inteiro (85 mil nos) prefira secoes especificas - a 8 (centralidade)
e a 12 (figura) levam varios minutos nessa escala.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import networkx as nx
import osmnx as ox

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "saida"

# dois pontos bem separados dentro do Plano Piloto (lat, lon)
ORIGEM = (-15.8100, -47.9270)      # Setor Policial Sul
DESTINO = (-15.7645, -47.8698)     # UnB, Campus Darcy Ribeiro

# par usado na secao 10: viagem classica Asa Norte -> Asa Sul, que usa o Eixao
ORIGEM_EIXO = (-15.7396, -47.8830)    # CLN 416, Asa Norte
DESTINO_EIXO = (-15.8330, -47.9070)   # SQS 416, Asa Sul


def dist_m(p, q) -> float:
    """Distancia haversine em metros entre (lat, lon) e (lat, lon)."""
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, [p[0], p[1], q[0], q[1]])
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(h))


def nomes_de(gdf) -> list:
    """Extrai nomes de via legiveis de um GeoDataFrame de arestas (o OSM as vezes
    guarda uma lista de nomes numa aresta so, quando ela funde varios ways)."""
    out = []
    for v in gdf["name"]:
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str) and x not in out:
                out.append(x)
    return out


def titulo(n: int, texto: str) -> None:
    print(f"\n{'=' * 72}\n{n}. {texto}\n{'=' * 72}")


# --------------------------------------------------------------------------- #
def secao_1_anatomia(G):
    titulo(1, "ANATOMIA DO GRAFO")
    print(f"Tipo do objeto           : {type(G).__name__}")
    print(f"Dirigido?                : {G.is_directed()}   (mao unica importa)")
    print(f"Multigrafo?              : {G.is_multigraph()} (duas ruas podem ligar o mesmo par de nos)")
    print(f"Nos                      : {G.number_of_nodes():,}")
    print(f"Arestas                  : {G.number_of_edges():,}")
    print(f"CRS (sistema de coord.)  : {G.graph['crs']}")

    n = next(iter(G.nodes))
    print(f"\n--- um NO (id = osmid do OpenStreetMap) ---\n{n}")
    for k, v in G.nodes[n].items():
        print(f"    {k:14s} = {v}")

    u, v, k = next(iter(G.edges(keys=True)))
    print(f"\n--- uma ARESTA (u={u}, v={v}, key={k}) ---")
    for kk, vv in G.edges[u, v, k].items():
        vv = str(vv)
        print(f"    {kk:14s} = {vv[:70]}{'...' if len(vv) > 70 else ''}")

    print("\nLeitura: no = intersecao ou fim de via; aresta = trecho de rua entre")
    print("duas intersecoes, com 'length' em metros e geometria real da curva.")


def secao_2_atributos(G):
    titulo(2, "COMPLETUDE DOS ATRIBUTOS (o que o OSM realmente informa)")
    total = G.number_of_edges()
    campos = ["name", "highway", "lanes", "maxspeed", "oneway", "length", "speed_kph", "travel_time"]
    for c in campos:
        tem = sum(1 for _, _, d in G.edges(data=True) if d.get(c) is not None)
        print(f"    {c:12s}: {tem:>7,} / {total:,}  ({100*tem/total:5.1f}%)")

    print("\nPor classe de via (tag highway):")
    cont = Counter()
    comp = Counter()
    for _, _, d in G.edges(data=True):
        h = d.get("highway")
        h = h[0] if isinstance(h, list) else h
        cont[h] += 1
        comp[h] += d.get("length", 0)
    for h, q in cont.most_common(10):
        print(f"    {h:18s} {q:>6,} arestas   {comp[h]/1000:>8,.1f} km")

    print("\nATENCAO: 'lanes' e 'maxspeed' faltam na maior parte das vias locais.")
    print("Para modelar capacidade, impute por classe de via (o speed_kph ja faz isso).")


def secao_3_geodataframes(G):
    titulo(3, "GRAFO <-> TABELA (GeoDataFrames)")
    nos, arestas = ox.convert.graph_to_gdfs(G)
    print(f"nos    : {nos.shape[0]:,} linhas x {nos.shape[1]} colunas -> {list(nos.columns)}")
    print(f"arestas: {arestas.shape[0]:,} linhas x {arestas.shape[1]} colunas")
    print(f"         indice = (u, v, key); colunas = {list(arestas.columns)[:9]} ...")

    print("\nAs 5 vias nomeadas mais extensas da area:")
    tab = (arestas.assign(nome=arestas["name"].astype(str))
                  .groupby("nome")["length"].sum()
                  .sort_values(ascending=False))
    for nome, m in tab.head(6).items():
        if nome in ("nan", "None"):
            continue
        print(f"    {m/1000:7.2f} km   {nome[:60]}")

    print("\nVoltar de tabela para grafo: ox.convert.graph_from_gdfs(nos, arestas)")


def secao_4_rotas(G):
    titulo(4, "ROTEAMENTO: menor caminho por DISTANCIA vs por TEMPO")
    o = ox.distance.nearest_nodes(G, X=ORIGEM[1], Y=ORIGEM[0])
    d = ox.distance.nearest_nodes(G, X=DESTINO[1], Y=DESTINO[0])
    so = dist_m(ORIGEM, (G.nodes[o]["y"], G.nodes[o]["x"]))
    sd = dist_m(DESTINO, (G.nodes[d]["y"], G.nodes[d]["x"]))
    print(f"no de origem  : {o}  ({so:.0f} m do ponto pedido {ORIGEM})")
    print(f"no de destino : {d}  ({sd:.0f} m do ponto pedido {DESTINO})")
    print("(nearest_nodes 'gruda' a coordenada no no mais proximo da rede)")

    rota_dist = ox.routing.shortest_path(G, o, d, weight="length")
    rota_tempo = ox.routing.shortest_path(G, o, d, weight="travel_time")

    print()
    for nome, rota in [("menor DISTANCIA", rota_dist), ("menor TEMPO", rota_tempo)]:
        gdf = ox.routing.route_to_gdf(G, rota)
        print(f"    {nome:16s}: {len(rota):3d} nos | {gdf['length'].sum()/1000:6.2f} km | "
              f"{gdf['travel_time'].sum()/60:5.1f} min")

    print(f"\nAs duas rotas sao iguais? {rota_dist == rota_tempo}")
    print("Mudar o 'weight' muda o caminho: e a mesma rede, com outro custo por aresta.")
    print("Por baixo do capo isso e Dijkstra do NetworkX:")
    print("    nx.shortest_path(G, o, d, weight='travel_time')")
    return o, d, rota_tempo


def secao_5_alternativas(G, o, d):
    titulo(5, "ROTAS ALTERNATIVAS (k caminhos mais curtos)")
    rotas = list(ox.routing.k_shortest_paths(G, o, d, k=3, weight="travel_time"))
    for i, r in enumerate(rotas, 1):
        gdf = ox.routing.route_to_gdf(G, r, weight="travel_time")
        vias = nomes_de(gdf)[:4]
        print(f"    rota {i}: {gdf['travel_time'].sum()/60:5.1f} min | "
              f"{gdf['length'].sum()/1000:5.2f} km | via {', '.join(v[:22] for v in vias)}")
    print("\nUtil para a pergunta do projeto: se uma via fecha, para onde o fluxo vai?")


def secao_6_subgrafos(G):
    titulo(6, "SUBGRAFOS: recortar so a malha arterial")
    classes = {"motorway", "trunk", "primary", "secondary",
               "motorway_link", "trunk_link", "primary_link", "secondary_link"}

    def eh_arterial(u, v, k):
        h = G.edges[u, v, k].get("highway")
        h = h if isinstance(h, list) else [h]
        return any(x in classes for x in h)

    arteriais = [(u, v, k) for u, v, k in G.edges(keys=True) if eh_arterial(u, v, k)]
    H = G.edge_subgraph(arteriais).copy()
    print(f"    grafo completo : {G.number_of_nodes():>7,} nos | {G.number_of_edges():>7,} arestas")
    print(f"    so arteriais   : {H.number_of_nodes():>7,} nos | {H.number_of_edges():>7,} arestas")
    ext = sum(d.get("length", 0) for _, _, d in H.edges(data=True)) / 1000
    print(f"    extensao arterial: {ext:,.1f} km")
    print("\nEsse recorte e o que interessa para os dados do DETRAN: as contagens")
    print("de fluxo existem para rodovias/arteriais, nao para rua de quadra.")
    return H


def secao_7_conectividade(G):
    titulo(7, "CONECTIVIDADE (armadilha classica)")
    fortes = list(nx.strongly_connected_components(G))
    print(f"    componentes fortemente conexos : {len(fortes):,}")
    print(f"    componentes fracamente conexos : {nx.number_weakly_connected_components(G):,}")
    maior = max(fortes, key=len)
    print(f"    maior componente forte         : {len(maior):,} nos "
          f"({100*len(maior)/G.number_of_nodes():.1f}%)")
    print("\nFora do componente forte existem nos de onde NAO da para sair (ou chegar)")
    print("por causa de mao unica mal mapeada. Antes de rodar roteamento em massa:")
    print("    G = ox.truncate.largest_component(G, strongly=True)")
    Gc = ox.truncate.largest_component(G, strongly=True)
    print(f"    -> sobra {Gc.number_of_nodes():,} nos, e todo par origem-destino tem rota.")
    return Gc


def secao_8_centralidade(G):
    titulo(8, "CENTRALIDADE: quais vias sao estruturalmente criticas")
    Gc = ox.truncate.largest_component(G, strongly=True)
    D = nx.DiGraph(Gc)                       # betweenness nao aceita multigrafo
    k = min(400, D.number_of_nodes())        # amostragem: exato seria O(n*m)
    print(f"    calculando betweenness aproximada com k={k} pivos...")
    bc = nx.betweenness_centrality(D, k=k, weight="travel_time", seed=42)
    nx.set_node_attributes(Gc, bc, "bc")

    top = sorted(bc.items(), key=lambda x: -x[1])[:10]
    print("\n    top 10 nos por intermediacao (proxy de gargalo):")
    for n, val in top:
        nomes = {str(dd.get("name")) for _, _, dd in Gc.edges(n, data=True)}
        nomes.discard("None")
        print(f"      no {n:>12} | bc={val:.4f} | {', '.join(list(nomes)[:3])[:55]}")

    print("\n    LEMBRE (research/articles.md): centralidade descreve topologia, nao")
    print("    prediz fluxo em regime de alta densidade. Use como descritor.")


def secao_9_isocrona(G):
    titulo(9, "ISOCRONA: ate onde da para chegar em 10 minutos")
    centro = ox.distance.nearest_nodes(G, X=-47.8825, Y=-15.7935)   # Rodoviaria do Plano
    for minutos in (2, 5, 10):
        alcance = nx.single_source_dijkstra_path_length(
            G, centro, cutoff=minutos * 60, weight="travel_time")
        sub = G.subgraph(alcance)
        km = sum(d.get("length", 0) for _, _, d in sub.edges(data=True)) / 1000
        print(f"    {minutos:2d} min -> {len(alcance):>6,} nos alcancaveis | {km:7.1f} km de via")
    print("\n    (isso e um Dijkstra com corte; a 'mancha' e o convex hull desses nos)")


def secao_10_bpr(G):
    titulo(10, "APLICACAO AO PROJETO: congestionamento com a funcao BPR")
    print("    t = t0 * (1 + alpha * (V/C)^beta)     alpha=0.8  beta=4.7  (arteriais urbanas)")
    alpha, beta = 0.8, 4.7

    def capacidade(d):
        """Capacidade horaria grosseira: faixas x 1800 veic/h/faixa."""
        f = d.get("lanes", 1)
        f = f[0] if isinstance(f, list) else f
        try:
            f = int(float(f))
        except (TypeError, ValueError):
            h = d.get("highway")
            h = h[0] if isinstance(h, list) else h
            f = {"motorway": 3, "trunk": 3, "primary": 2, "secondary": 2}.get(h, 1)
        return max(1, f) * 1800

    def tem_nome(d, alvo):
        n = d.get("name")
        return any(alvo in x for x in (n if isinstance(n, list) else [n]) if isinstance(x, str))

    # Cenario: pico no Eixo Rodoviario (V/C = 1.15) e rede folgada no resto (V/C = 0.40).
    CORREDOR = "Eixo Rodoviário"          # como o nome aparece na tag 'name' do OSM
    n_corredor = 0
    novos = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        C = capacidade(d)
        no_corredor = tem_nome(d, CORREDOR)
        n_corredor += no_corredor
        V = (1.15 if no_corredor else 0.40) * C
        novos[(u, v, k)] = d["travel_time"] * (1 + alpha * (V / C) ** beta)
    nx.set_edge_attributes(G, novos, "travel_time_bpr")
    print(f"    arestas no corredor '{CORREDOR}': {n_corredor}")

    o = ox.distance.nearest_nodes(G, X=ORIGEM_EIXO[1], Y=ORIGEM_EIXO[0])
    d_ = ox.distance.nearest_nodes(G, X=DESTINO_EIXO[1], Y=DESTINO_EIXO[0])
    print(f"    viagem testada: Asa Norte -> Asa Sul ({ORIGEM_EIXO} -> {DESTINO_EIXO})")
    r_livre = ox.routing.shortest_path(G, o, d_, weight="travel_time")
    r_cong = ox.routing.shortest_path(G, o, d_, weight="travel_time_bpr")

    def custo(rota, peso):
        return sum(min(dd[peso] for dd in G[u][v].values())
                   for u, v in zip(rota[:-1], rota[1:])) / 60

    print(f"\n    rota de fluxo livre : {custo(r_livre,'travel_time'):5.1f} min livres "
          f"-> {custo(r_livre,'travel_time_bpr'):5.1f} min no pico")
    print(f"    rota reotimizada    : {custo(r_cong,'travel_time'):5.1f} min livres "
          f"-> {custo(r_cong,'travel_time_bpr'):5.1f} min no pico")
    print(f"    o motorista desviou do Eixo? {r_livre != r_cong}")
    print(f"    vias da rota no pico: "
          f"{', '.join(nomes_de(ox.routing.route_to_gdf(G, r_cong))[:5])[:70]}")

    print("\n    Isso e um passo de alocacao de trafego. Iterando (Frank-Wolfe) ate")
    print("    ninguem ganhar trocando de rota, chega-se ao equilibrio de Wardrop.")
    print("    Proximo passo real: trocar o V ficticio pelo fluxo do DETRAN (Flow.csv),")
    print("    casando o codigo do trecho (Roads.csv) com a tag 'ref' das arestas.")


def secao_11_ponte_detran(G):
    titulo(11, "PONTE COM OS DADOS DO DETRAN (tag 'ref' = DF-000 / BR-000)")
    refs = Counter()
    for _, _, d in G.edges(data=True):
        r = d.get("ref")
        for x in (r if isinstance(r, list) else [r]):
            if x:
                refs[x] += d.get("length", 0) / len(r if isinstance(r, list) else [r])
    if not refs:
        print("    nenhuma aresta com tag 'ref' nesta area.")
        return
    print(f"    {len(refs)} rodovias identificadas por codigo no OSM. Maiores extensoes:")
    for r, m in refs.most_common(12):
        print(f"      {r:14s} {m/1000:7.2f} km")
    print("\n    Roads.csv usa codigos como '001EDF0010' -> DF-001. Normalize os dois")
    print("    lados e voce liga o TMD do DETRAN direto na aresta do grafo.")


def secao_12_plot(G, rota):
    titulo(12, "VISUALIZACAO DA ROTA")
    caminho = SAIDA / "exemplo_rota.png"
    ox.plot.plot_graph_route(
        G, rota, route_color="#ff5a36", route_linewidth=3, node_size=0,
        edge_linewidth=0.3, edge_color="#3d5a80", bgcolor="#0b0f14",
        figsize=(12, 12), show=False, close=True, save=True,
        filepath=str(caminho), dpi=160,
    )
    print(f"    figura salva em {caminho}")


# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--grafo", default="plano_piloto_drive",
                   help="nome base do .graphml em grafo_brasilia/saida")
    p.add_argument("--secao", type=int, default=0, help="rodar so uma secao (1-12)")
    args = p.parse_args()

    caminho = SAIDA / f"{args.grafo}.graphml"
    if not caminho.exists():
        sys.exit(f"Grafo nao encontrado: {caminho}\nRode antes: python grafo_brasilia/build_graph.py")

    print(f"Carregando {caminho.name} ...")
    G = ox.io.load_graphml(caminho)          # tipos numericos ja voltam convertidos
    print(f"OK: {G.number_of_nodes():,} nos, {G.number_of_edges():,} arestas")

    s = args.secao
    if s in (0, 1):  secao_1_anatomia(G)
    if s in (0, 2):  secao_2_atributos(G)
    if s in (0, 3):  secao_3_geodataframes(G)

    o = d = rota = None
    if s in (0, 4, 5, 12):
        o, d, rota = secao_4_rotas(G)
    if s in (0, 5):  secao_5_alternativas(G, o, d)
    if s in (0, 6):  secao_6_subgrafos(G)
    if s in (0, 7):  secao_7_conectividade(G)
    if s in (0, 8):  secao_8_centralidade(G)
    if s in (0, 9):  secao_9_isocrona(G)
    if s in (0, 10): secao_10_bpr(G)
    if s in (0, 11): secao_11_ponte_detran(G)
    if s in (0, 12): secao_12_plot(G, rota)

    print("\nFim.")


if __name__ == "__main__":
    main()
