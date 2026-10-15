"""
Expande o grafo de 30 nos do Gama (cache/gama_drive_sample_30.graphml) para um
recorte com escolha de rota, sem invalidar o que ja usa o grafo antigo.

Por que: no grafo de 30 nos, 25 das 37 arestas sao de mao unica e ha so uma
pista de cada rodovia; nenhum par OD tem duas rotas realmente distintas, entao
o equilibrio de Wardrop seria identico ao tudo-ou-nada. Ao redor do trevo
EPCT / EPIP / DF-480 existem a pista oposta, as alcas e a malha de vias
terciarias da Ponte Alta Norte, que formam rotas paralelas.

Fonte: um download do OpenStreetMap so da area de estudo, e nao o
cache/gama_drive_projected.graphml. Aquele grafo foi recortado pelo limite da
RA Gama, e a EPCT corre a 2-12 m dessa divisa: a pista no sentido norte da
EPCT e o trecho da EPIP depois do trevo ficam do lado de fora e nao existem
nele. O download e simplificado com os 30 nos atuais forcados como pontas de
aresta, o que reproduz as 37 arestas atuais identicas (o script confere).
O resultado fica salvo em cache/ e as proximas execucoes nao usam a rede.

Como o recorte e feito (deterministico, reproduzivel):
  1. poligono = envoltoria convexa dos 30 nos atuais + BUFFER_M metros;
  2. entram as arestas da area baixada cujas duas pontas estao no
     poligono e cuja classe esta em CLASSES (terciaria para cima);
  3. os 30 nos atuais entram sempre, com todas as suas arestas;
  4. poda: remove, repetidamente, nos sem saida (so um vizinho) que estejam a
     mais de BORDA_M da borda do poligono - becos internos que nao fazem parte
     de rota nenhuma. Nos perto da borda ficam, porque sao entradas/saidas;
  5. fica a componente fracamente conexa que contem os 30 nos.

Compatibilidade com o que ja existe:
  - os 30 nos mantem os ids "0".."29" e as 37 arestas mantem u, v e "id".
    O historico de velocidade (edge_id "u:v:key") continua valendo no grafo novo;
  - nos novos recebem ids a partir de "30", em ordem de osmid;
  - os arquivos do grafo de 30 nos NAO sao alterados (api_caller.py e o
    workflow do GitHub Actions continuam funcionando como hoje).

Uso (da raiz do repositorio):
    python scripts/expand_graph.py
    python scripts/expand_graph.py --buffer 400
    python scripts/expand_graph.py --baixar      # forca novo download do OSM

Saidas em cache/:
    gama_area_estudo_osm.graphml           download do OSM da area (fonte do recorte)
    gama_drive_expanded.graphml            grafo (DiGraph, mesmo formato do de 30 nos)
    gama_drive_expanded.gpkg               camadas nodes/edges no esquema do api_caller.py
    gama_drive_expanded_selection.json     parametros, mapeamento de ids, diagnostico
    gama_drive_expanded_portoes.geojson    caixas sugeridas para a analise O/D da TomTom
    gama_drive_expanded.png                figura de conferencia
"""

import argparse
import itertools
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import networkx as nx
import osmnx as ox
from shapely import wkt
from shapely.geometry import LineString, MultiPoint, Point, box

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
CACHE = RAIZ / "cache"
AREA_OSM = CACHE / "gama_area_estudo_osm.graphml"
GRAFO_ATUAL = CACHE / "gama_drive_sample_30.graphml"
# matriz da analise "Gama 3" (30 caixas), usada so no diagnostico de rotas que
# justificou a expansao. Foi removida do repositorio: sem ela o diagnostico e pulado.
MATRIZ_OD = RAIZ / "Tables/matriz_od_gama3.json"
NOME = "gama_drive_expanded"
CRS = "EPSG:31983"

BUFFER_M = 200
MARGEM_DOWNLOAD_M = 100     # o download vai um pouco alem do recorte
BORDA_M = 60
CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
}
# colunas do GeoPackage, no esquema que o api_caller.py le
COLUNAS_ARESTA = ["osmid", "highway", "lanes", "maxspeed", "ref", "oneway", "reversed",
                  "length", "name", "bridge", "junction", "access"]


def classe(d: dict) -> str:
    """highway pode vir como lista ("['unclassified', 'tertiary']")."""
    h = d.get("highway", "")
    return h.strip("[]").split(",")[0].strip(" '") if h.startswith("[") else h


# ---------------------------------------------------------------------------
# 0. Download da area de estudo
# ---------------------------------------------------------------------------
def poligono_base(S: nx.DiGraph, buffer_m: float):
    pts = [Point(float(d["x"]), float(d["y"])) for _, d in S.nodes(data=True)]
    return MultiPoint(pts).convex_hull.buffer(buffer_m)


def baixar_area(S: nx.DiGraph, buffer_m: float) -> None:
    """Baixa a malha 'drive' sem simplificar e simplifica forcando os 30 nos
    atuais como pontas de aresta (node_attrs_include), para nao fundi-los."""
    ox.settings.use_cache = False          # o cache padrao do OSMnx e ./cache, a pasta do projeto
    ox.settings.requests_timeout = 180
    area = gpd.GeoSeries([poligono_base(S, buffer_m + MARGEM_DOWNLOAD_M)], crs=CRS)
    bruto = ox.graph_from_polygon(area.to_crs(4326).iloc[0], network_type="drive",
                                  simplify=False, retain_all=True, truncate_by_edge=True)
    P = ox.project_graph(bruto, to_crs=CRS)
    for _, d in S.nodes(data=True):
        P.nodes[int(d["original_osmid"])]["ponta_fixa"] = True
    Q = ox.simplification.simplify_graph(P, node_attrs_include=["ponta_fixa"])
    for n in Q.nodes:
        Q.nodes[n].pop("ponta_fixa", None)
    Q.graph["buffer_download_m"] = buffer_m + MARGEM_DOWNLOAD_M
    Q.graph["baixado_em"] = __import__("datetime").date.today().isoformat()
    ox.save_graphml(Q, AREA_OSM)
    print(f"Area baixada do OSM: {Q.number_of_nodes()} nos -> {AREA_OSM.relative_to(RAIZ)}")


# ---------------------------------------------------------------------------
# 1. Selecao
# ---------------------------------------------------------------------------
def selecionar(F: nx.MultiDiGraph, base: set, buffer_m: float):
    pos = {n: Point(float(d["x"]), float(d["y"])) for n, d in F.nodes(data=True)}
    poligono = MultiPoint([pos[n] for n in base]).convex_hull.buffer(buffer_m)
    falta = base - set(F)
    if falta:
        sys.exit(f"Nos do grafo atual ausentes na area baixada: {sorted(falta)}")

    manter = set(base)
    for u, v, d in F.edges(data=True):
        if classe(d) in CLASSES and poligono.covers(pos[u]) and poligono.covers(pos[v]):
            manter |= {u, v}
    H = nx.DiGraph(F.subgraph(manter))

    mudou = True
    while mudou:
        mudou = False
        for n in list(H):
            vizinhos = set(H.predecessors(n)) | set(H.successors(n))
            if n not in base and len(vizinhos) <= 1 and poligono.exterior.distance(pos[n]) > BORDA_M:
                H.remove_node(n)
                mudou = True

    comp = max(nx.weakly_connected_components(H), key=lambda c: len(c & base))
    if not base <= comp:
        sys.exit("Os 30 nos atuais nao ficaram na mesma componente: revise os parametros.")
    return H.subgraph(comp).copy(), poligono


# ---------------------------------------------------------------------------
# 2. Ids compativeis com o grafo de 30 nos
# ---------------------------------------------------------------------------
def montar(F, H, S) -> nx.DiGraph:
    osm2id = {d["original_osmid"]: n for n, d in S.nodes(data=True)}
    novos = sorted((n for n in H if n not in osm2id), key=int)
    osm2id.update({o: str(30 + i) for i, o in enumerate(novos)})

    id_aresta = {(d["original_u"], d["original_v"]): int(d["id"]) for _, _, d in S.edges(data=True)}
    proximo = max(id_aresta.values()) + 1

    G = nx.DiGraph(crs=CRS, fonte=AREA_OSM.name,
                   descricao="Expansao do grafo de 30 nos; ids 0-29 preservados")
    for o in sorted(H, key=lambda o: int(osm2id[o])):
        d = F.nodes[o]
        G.add_node(osm2id[o], original_osmid=o, x=d["x"], y=d["y"],
                   street_count=d.get("street_count", ""),
                   **({"highway": d["highway"]} if "highway" in d else {}))

    for u, v in sorted(H.edges, key=lambda e: (int(osm2id[e[0]]), int(osm2id[e[1]]))):
        dados = list(F[u][v].values())
        if len(dados) > 1:   # nao acontece no recorte padrao, mas fica explicito
            dados.sort(key=lambda d: float(d["length"]))
        d = dict(dados[0])
        if (u, v) in id_aresta:
            ident = id_aresta[(u, v)]
        else:
            ident, proximo = proximo, proximo + 1
        G.add_edge(osm2id[u], osm2id[v], original_u=u, original_v=v, id=str(ident), **d)
    return G


# ---------------------------------------------------------------------------
# 3. Diagnostico: quanta demanda tem rota alternativa de verdade
# ---------------------------------------------------------------------------
def rotas_distintas(G, a, b, tolerancia=1.3, sobreposicao=0.6, limite=40) -> int:
    """Rotas ate `tolerancia` x a mais curta que compartilham menos de
    `sobreposicao` das arestas com as ja aceitas."""
    if not nx.has_path(G, a, b):
        return 0
    aceitas, menor = [], None
    for p in itertools.islice(nx.shortest_simple_paths(G, a, b, weight="w"), limite):
        L = sum(G[u][v]["w"] for u, v in zip(p, p[1:]))
        menor = menor or L
        if L > tolerancia * menor:
            break
        e = set(zip(p, p[1:]))
        if all(len(e & q) / len(e) < sobreposicao for q in aceitas):
            aceitas.append(e)
    return len(aceitas)


def diagnostico(G, S) -> dict | None:
    if not MATRIZ_OD.exists():
        return None
    m = json.loads(MATRIZ_OD.read_text(encoding="utf-8"))
    pares = m["pares"] + m["pares_sem_caminho"]

    def resumo(grafo):
        W = nx.DiGraph(grafo)
        for u, v, d in W.edges(data=True):
            d["w"] = float(d["length"])
        total = sum(p["veic_h"] for p in pares)
        com_caminho = sum(p["veic_h"] for p in pares if nx.has_path(W, p["origem"], p["destino"]))
        multiplas = sum(p["veic_h"] for p in pares if rotas_distintas(W, p["origem"], p["destino"]) >= 2)
        return {"demanda_com_caminho": round(com_caminho / total, 3),
                "demanda_com_2_ou_mais_rotas": round(multiplas / total, 3)}

    return {"criterio": "rotas ate 30% mais longas que a mais curta e com menos de 60% "
                        "de arestas em comum, ponderado pela matriz OD atual (veic/h)",
            "grafo_30_nos": resumo(S), "grafo_expandido": resumo(G)}


# ---------------------------------------------------------------------------
# 4. Portoes: onde a analise O/D da TomTom precisa de caixa
# ---------------------------------------------------------------------------
def portoes(F, G) -> list[dict]:
    """No de borda = tem via no grafo completo que sai do recorte (ou e fonte /
    sumidouro do recorte). 'principal' se essa via e terciaria para cima."""
    id2osm = nx.get_node_attributes(G, "original_osmid")
    dentro = set(id2osm.values())
    saida = []
    for n, o in id2osm.items():
        externas = [classe(d) for _, w, d in F.out_edges(o, data=True) if w not in dentro]
        externas += [classe(d) for w, _, d in F.in_edges(o, data=True) if w not in dentro]
        extremo = G.in_degree(n) == 0 or G.out_degree(n) == 0
        if externas or extremo:
            principal = extremo or any(c in CLASSES for c in externas)
            saida.append({"no": n, "osmid": o, "tipo": "principal" if principal else "acesso_local",
                          "vias_externas": sorted(set(externas))})
    return saida


def caixas_geojson(G, lista: list[dict]) -> dict:
    """Quadrado em volta de cada portao, menor que a metade da distancia ao no
    vizinho, para duas caixas nunca se sobreporem no trevo."""
    pts = {n: Point(float(d["x"]), float(d["y"])) for n, d in G.nodes(data=True)}
    feats = []
    for p in lista:
        c = pts[p["no"]]
        viz = min(c.distance(q) for m, q in pts.items() if m != p["no"])
        meio = max(4.0, min(12.0, 0.4 * viz))
        feats.append({"no": p["no"], "osmid": p["osmid"], "tipo": p["tipo"],
                      "geometry": box(c.x - meio, c.y - meio, c.x + meio, c.y + meio)})
    gdf = gpd.GeoDataFrame(feats, crs=CRS).to_crs(4326)
    gdf["name"] = "no " + gdf["no"]
    return json.loads(gdf[["name", "no", "osmid", "tipo", "geometry"]].to_json())


# ---------------------------------------------------------------------------
# 5. Saidas
# ---------------------------------------------------------------------------
def geopackage(G, destino: Path) -> None:
    nos = gpd.GeoDataFrame(
        [{"osmid": int(n), "y": float(d["y"]), "x": float(d["x"]),
          "street_count": int(d["street_count"]) if d.get("street_count") else None,
          "highway": d.get("highway"), "original_osmid": int(d["original_osmid"]),
          "geometry": Point(float(d["x"]), float(d["y"]))} for n, d in G.nodes(data=True)],
        crs=CRS)
    arestas = []
    for u, v, d in G.edges(data=True):
        geom = wkt.loads(d["geometry"]) if "geometry" in d else LineString(
            [(float(G.nodes[u]["x"]), float(G.nodes[u]["y"])),
             (float(G.nodes[v]["x"]), float(G.nodes[v]["y"]))])
        linha = {"u": int(u), "v": int(v), "key": 0}
        linha.update({c: d.get(c) for c in COLUNAS_ARESTA})
        linha["oneway"] = d.get("oneway") == "True"
        linha["length"] = float(d["length"])
        linha.update({"original_u": int(d["original_u"]), "original_v": int(d["original_v"]),
                      "geometry": geom})
        arestas.append(linha)
    if destino.exists():
        destino.unlink()
    nos.to_file(destino, layer="nodes", driver="GPKG", index=False)
    gpd.GeoDataFrame(arestas, crs=CRS).to_file(destino, layer="edges", driver="GPKG", index=False)


def figura(G, base_ids: set, poligono, lista, destino: Path) -> None:
    cores = {"trunk": "#ff5a36", "trunk_link": "#ff8c42", "primary": "#ffc145",
             "primary_link": "#ffc145", "secondary": "#7fd1b9", "tertiary": "#4da6ff",
             "tertiary_link": "#4da6ff", "unclassified": "#9aa5b1", "busway": "#c77dff"}
    fig, ax = plt.subplots(figsize=(12, 12), dpi=120)
    fig.patch.set_facecolor("#0b0f14")
    ax.set_facecolor("#0b0f14")
    xy = {n: (float(d["x"]), float(d["y"])) for n, d in G.nodes(data=True)}
    for u, v, d in G.edges(data=True):
        g = wkt.loads(d["geometry"]) if "geometry" in d else LineString([xy[u], xy[v]])
        antiga = u in base_ids and v in base_ids
        ax.plot(*g.xy, color=cores.get(classe(d), "#666"), lw=3.4 if antiga else 1.3,
                alpha=1 if antiga else 0.85, solid_capstyle="round")
    ax.plot(*poligono.exterior.xy, color="white", lw=0.7, ls="--", alpha=0.6)
    for tipo, cor, tam in (("principal", "#ffffff", 26), ("acesso_local", "#7a8794", 10)):
        pts = [xy[p["no"]] for p in lista if p["tipo"] == tipo]
        if pts:
            ax.scatter(*zip(*pts), s=tam, c=cor, zorder=5, label=f"portao {tipo.replace('_', ' ')}")
    for k in ("trunk", "primary", "tertiary", "busway"):
        ax.plot([], [], color=cores[k], lw=3, label=k)
    ax.plot([], [], color="#cccccc", lw=3.4, label="traco grosso = grafo de 30 nos")
    ax.legend(facecolor="#0b0f14", labelcolor="white", loc="upper left", frameon=False)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(destino, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--buffer", type=float, default=BUFFER_M, help="metros em volta dos 30 nos")
    ap.add_argument("--baixar", action="store_true", help="baixar a area do OSM de novo")
    args = ap.parse_args()

    S = nx.read_graphml(GRAFO_ATUAL)
    precisa = args.baixar or not AREA_OSM.exists()
    if not precisa:
        salvo = float(nx.read_graphml(AREA_OSM).graph.get("buffer_download_m", 0))
        precisa = salvo < args.buffer + MARGEM_DOWNLOAD_M
    if precisa:
        baixar_area(S, args.buffer)
    F = nx.read_graphml(AREA_OSM)
    base = {d["original_osmid"] for _, d in S.nodes(data=True)}

    H, poligono = selecionar(F, base, args.buffer)
    G = montar(F, H, S)

    # garantia de compatibilidade: o grafo de 30 nos tem que estar contido no novo
    for u, v, d in S.edges(data=True):
        assert G.has_edge(u, v) and G[u][v]["id"] == d["id"], f"aresta {u}->{v} mudou"
    for n, d in S.nodes(data=True):
        assert G.nodes[n]["original_osmid"] == d["original_osmid"], f"no {n} mudou"

    lista = portoes(F, G)
    diag = diagnostico(G, S)

    nx.write_graphml(G, CACHE / f"{NOME}.graphml")
    geopackage(G, CACHE / f"{NOME}.gpkg")
    (CACHE / f"{NOME}_portoes.geojson").write_text(
        json.dumps(caixas_geojson(G, lista), ensure_ascii=False), encoding="utf-8")
    figura(G, set(S.nodes), poligono, lista, CACHE / f"{NOME}.png")

    classes = {}
    for _, _, d in G.edges(data=True):
        classes[classe(d)] = classes.get(classe(d), 0) + 1
    selecao = {
        "source_graphml": AREA_OSM.name,
        "base_graphml": GRAFO_ATUAL.name,
        "parametros": {"buffer_m": args.buffer, "borda_m": BORDA_M, "classes": sorted(CLASSES)},
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "nos_novos": G.number_of_nodes() - S.number_of_nodes(),
        "arestas_novas": G.number_of_edges() - S.number_of_edges(),
        "weakly_connected": nx.is_weakly_connected(G),
        "maior_componente_forte": len(max(nx.strongly_connected_components(G), key=len)),
        "fontes": sorted((n for n in G if G.in_degree(n) == 0), key=int),
        "sumidouros": sorted((n for n in G if G.out_degree(n) == 0), key=int),
        "highway_types": dict(sorted(classes.items(), key=lambda x: -x[1])),
        "avisos": [
            "A aresta 23->24 do grafo de 30 nos e 'busway' (corredor de onibus). Ela foi "
            "mantida para nao quebrar a compatibilidade; exclua highway == 'busway' da "
            "alocacao de carros no Frank-Wolfe.",
        ],
        "diagnostico_rotas": diag,
        "portoes": lista,
        "node_id_mapping": {n: d["original_osmid"] for n, d in G.nodes(data=True)},
    }
    (CACHE / f"{NOME}_selection.json").write_text(
        json.dumps(selecao, ensure_ascii=False, indent=1), encoding="utf-8")

    principais = sum(p["tipo"] == "principal" for p in lista)
    print(f"Grafo expandido: {G.number_of_nodes()} nos ({selecao['nos_novos']} novos), "
          f"{G.number_of_edges()} arestas ({selecao['arestas_novas']} novas)")
    print(f"Classes: {selecao['highway_types']}")
    print(f"Maior componente fortemente conexa: {selecao['maior_componente_forte']} nos")
    print(f"Portoes: {principais} principais, {len(lista) - principais} acessos locais")
    if diag:
        a, b = diag["grafo_30_nos"], diag["grafo_expandido"]
        print(f"Demanda com 2+ rotas distintas: {a['demanda_com_2_ou_mais_rotas']:.0%} -> "
              f"{b['demanda_com_2_ou_mais_rotas']:.0%} | com caminho: "
              f"{a['demanda_com_caminho']:.0%} -> {b['demanda_com_caminho']:.0%}")
    print(f"Arquivos em {CACHE.relative_to(RAIZ)}/{NOME}*")


if __name__ == "__main__":
    main()
