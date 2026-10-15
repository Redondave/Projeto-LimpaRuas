"""
Faixas por sentido e limite de velocidade de cada aresta do grafo do Gama
(Etapa 3 do research/o_que_falta_fazer_pre_frank_wolfe.md).

Ordem de preenchimento, para cada atributo:
  1. OSM: tag da propria aresta (lanes / maxspeed);
  2. mesma via no OSM: outras arestas com o mesmo nome e a mesma classe tem a
     tag, e todas concordam -> usa esse valor (trecho da mesma rua sem tag);
  3. regra: limite pelo art. 61 do CTB, com a categoria da via deduzida da
     classe do OSM; faixas por classe (PADRAO_FAIXAS).
  4. correcao manual (Tables/faixas_limite_correcoes.csv), se existir: tem a
     palavra final, para registrar a conferencia feita no Google Maps.

Decisoes de conversao:
  - lanes do OSM conta as duas maos em via de mao dupla: faixas por sentido =
    lanes / 2 (arredondado para baixo, minimo 1). Em mao unica, lanes.
  - tag em lista ("['2', '3']", quando o OSMnx fundiu ways diferentes): o
    menor valor, que e o gargalo do trecho.
  - corredor de onibus (busway): permite_carro = False, sem limite.

O script so gera a tabela; o grafo atribuido (t0, capacidade) e montado na Etapa 4.

Uso (da raiz do repositorio):
    python scripts/faixas_limite.py

Saida:
    Tables/faixas_limite_arestas.csv   uma linha por aresta, com a fonte de cada
                                       valor e links do Google Maps para conferir
"""

import math
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import LineString

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
GRAFO = RAIZ / "cache/gama_drive_expanded.graphml"
CORRECOES = RAIZ / "Tables/faixas_limite_correcoes.csv"
SAIDA = RAIZ / "Tables/faixas_limite_arestas.csv"
CRS = "EPSG:31983"

# Classe do OSM -> categoria de via urbana do CTB (art. 60) e limite do art. 61,
# paragrafo 1o, inciso I: transito rapido 80, arterial 60, coletora 40, local 30.
# Correspondencia de classes segundo a pagina "Classificacao de vias" do OSM Brasil.
CATEGORIA_CTB = {
    "motorway": "transito rapido", "motorway_link": "transito rapido",
    "trunk": "transito rapido", "trunk_link": "transito rapido",
    "primary": "arterial", "primary_link": "arterial",
    "secondary": "arterial", "secondary_link": "arterial",
    "tertiary": "coletora", "tertiary_link": "coletora",
    "unclassified": "local", "residential": "local", "living_street": "local",
}
LIMITE_CTB = {"transito rapido": 80, "arterial": 60, "coletora": 40, "local": 30}

# Faixas por sentido quando nao ha tag: o padrao das proprias vias da area que
# tem a tag (trunk 2-3, primary 3, terciarias e alcas 1 por sentido).
PADRAO_FAIXAS = {
    "motorway": 2, "trunk": 2, "primary": 2, "secondary": 1, "tertiary": 1,
    "motorway_link": 1, "trunk_link": 1, "primary_link": 1, "secondary_link": 1,
    "tertiary_link": 1, "unclassified": 1, "residential": 1, "living_street": 1,
}
SEM_CARRO = {"busway"}


def classe(h: str) -> str:
    return h.strip("[]").split(",")[0].strip(" '") if h.startswith("[") else h


def menor_valor(tag) -> float | None:
    """'60' -> 60; "['2', '3']" -> 2; vazio -> None."""
    if tag is None or (isinstance(tag, float) and math.isnan(tag)):
        return None
    nums = [float(x) for x in str(tag).strip("[]").replace("'", "").split(",")
            if x.strip().replace(".", "", 1).isdigit()]
    return min(nums) if nums else None


def por_sentido(lanes: float, mao_unica: bool) -> int:
    return int(lanes) if mao_unica else max(1, int(lanes // 2))


def links_maps(geom: LineString, para_wgs) -> tuple[str, str]:
    """Satelite centrado no meio da aresta e Street View olhando no sentido de circulacao."""
    meio = geom.interpolate(0.5, normalized=True)
    a = geom.interpolate(max(0.0, geom.length / 2 - 5))
    b = geom.interpolate(min(geom.length, geom.length / 2 + 5))
    rumo = math.degrees(math.atan2(b.x - a.x, b.y - a.y)) % 360
    lon, lat = para_wgs.transform(meio.x, meio.y)
    sat = f"https://www.google.com/maps/@?api=1&map_action=map&center={lat:.6f},{lon:.6f}&zoom=20&basemap=satellite"
    rua = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat:.6f},{lon:.6f}&heading={rumo:.0f}"
    return sat, rua


def valor_da_via(arestas: pd.DataFrame, coluna: str) -> dict:
    """(nome, classe) -> valor, quando todas as arestas com tag daquela via concordam."""
    marcadas = arestas[arestas["nome"].notna() & arestas[coluna].notna()]
    unicos = marcadas.groupby(["nome", "highway"])[coluna].agg(lambda s: set(s))
    return {k: next(iter(v)) for k, v in unicos.items() if len(v) == 1}


def main() -> None:
    G = nx.read_graphml(GRAFO)
    para_wgs = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    pos = {n: (float(d["x"]), float(d["y"])) for n, d in G.nodes(data=True)}

    linhas = []
    for u, v, d in G.edges(data=True):
        geom = wkt.loads(d["geometry"]) if "geometry" in d else LineString([pos[u], pos[v]])
        mao_unica = d.get("oneway") == "True"
        lanes_osm = menor_valor(d.get("lanes"))
        sat, rua = links_maps(geom, para_wgs)
        linhas.append({
            "edge_id": f"{u}:{v}:0", "u": u, "v": v,
            "nome": d.get("name"), "highway": classe(d["highway"]), "oneway": mao_unica,
            "length_m": round(float(d["length"]), 1),
            "osm_lanes": d.get("lanes"), "osm_maxspeed": d.get("maxspeed"),
            "lanes_osm_sentido": por_sentido(lanes_osm, mao_unica) if lanes_osm else None,
            "maxspeed_osm": menor_valor(d.get("maxspeed")),
            "link_satelite": sat, "link_street_view": rua,
        })
    t = pd.DataFrame(linhas)

    via_lanes = valor_da_via(t, "lanes_osm_sentido")
    via_max = valor_da_via(t, "maxspeed_osm")

    def escolher(r, coluna_osm, via, regra):
        if pd.notna(r[coluna_osm]):
            return r[coluna_osm], "OSM"
        chave = (r["nome"], r["highway"])
        if pd.notna(r["nome"]) and chave in via:
            return via[chave], "OSM (mesma via)"
        return regra(r)

    def regra_lanes(r):
        return PADRAO_FAIXAS.get(r["highway"], 1), "padrao por classe"

    def regra_max(r):
        cat = CATEGORIA_CTB.get(r["highway"])
        return (LIMITE_CTB[cat], f"CTB art. 61 ({cat})") if cat else (None, "sem regra")

    t[["lanes_sentido", "fonte_lanes"]] = t.apply(
        lambda r: pd.Series(escolher(r, "lanes_osm_sentido", via_lanes, regra_lanes)), axis=1)
    t[["maxspeed_kmh", "fonte_maxspeed"]] = t.apply(
        lambda r: pd.Series(escolher(r, "maxspeed_osm", via_max, regra_max)), axis=1)
    t["categoria_ctb"] = t["highway"].map(CATEGORIA_CTB)
    t["permite_carro"] = ~t["highway"].isin(SEM_CARRO)
    t.loc[~t["permite_carro"], ["maxspeed_kmh", "fonte_maxspeed"]] = [None, "corredor de onibus"]

    if CORRECOES.exists():
        c = pd.read_csv(CORRECOES, dtype={"edge_id": str}).set_index("edge_id")
        for eid, r in c.iterrows():
            m = t["edge_id"] == eid
            if pd.notna(r.get("lanes_sentido")):
                t.loc[m, ["lanes_sentido", "fonte_lanes"]] = [int(r["lanes_sentido"]), "conferencia manual"]
            if pd.notna(r.get("maxspeed_kmh")):
                t.loc[m, ["maxspeed_kmh", "fonte_maxspeed"]] = [float(r["maxspeed_kmh"]), "conferencia manual"]
        print(f"Correcoes manuais aplicadas: {len(c)}")

    t["lanes_sentido"] = t["lanes_sentido"].astype(int)
    t["conferido"] = ""
    colunas = ["edge_id", "u", "v", "nome", "highway", "oneway", "length_m",
               "lanes_sentido", "fonte_lanes", "maxspeed_kmh", "fonte_maxspeed", "categoria_ctb",
               "permite_carro", "osm_lanes", "osm_maxspeed", "conferido",
               "link_satelite", "link_street_view"]
    t = t[colunas].sort_values(["highway", "nome", "u"], na_position="last")
    t.to_csv(SAIDA, index=False, encoding="utf-8-sig")

    print(f"{len(t)} arestas -> {SAIDA.relative_to(RAIZ)}\n")
    print("Faixas por sentido:")
    print(pd.crosstab(t["highway"], t["fonte_lanes"]).to_string(), "\n")
    print("Limite de velocidade:")
    print(pd.crosstab(t["highway"], t["fonte_maxspeed"]).to_string(), "\n")
    print("Valores adotados (limite km/h x classe):")
    print(pd.crosstab(t["highway"], t["maxspeed_kmh"].fillna(-1).astype(int)).to_string())


if __name__ == "__main__":
    main()
