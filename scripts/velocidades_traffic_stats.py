"""
Velocidade observada no pico por aresta do grafo do Gama, a partir do TomTom
Traffic Stats (Area Analysis), e o K inicial de cada aresta (Etapa 2 do
research/o_que_falta_fazer_pre_frank_wolfe.md).

A analise (job 10086419, "Gama") cobre julho/2026, dias uteis, 18:00-19:00 -
o mesmo periodo e janela da matriz OD. Ela devolve as vias da TomTom dentro do
poligono desenhado no portal, inclusive vias que nao estao no grafo; cada trecho
tem geometria no sentido de circulacao (segmentId negativo = sentido contrario
ao da digitalizacao) e, para a janela pedida, velocidade media, mediana e
harmonica, percentis e amostra normalizada.

Casamento trecho TomTom -> aresta do grafo:
  - o trecho precisa correr colado a aresta: a parte dele a ate BUFFER_M da
    aresta tem pelo menos SOBREPOSICAO_MIN_M;
  - e no mesmo sentido: cosseno entre os rumos locais >= COS_SENTIDO. Isso separa
    as duas maos de uma rua de mao dupla e descarta a pista paralela e as vias
    transversais nos cruzamentos;
  - vias da TomTom fora do grafo nao encostam em nenhuma aresta e ficam de fora.

Velocidade da aresta = media harmonica das velocidades harmonicas dos trechos,
ponderada pelo comprimento sobreposto:
    vmed = soma(L_i) / soma(L_i / v_i)
ou seja, a velocidade que reproduz o tempo de percurso somado dos trechos.

K inicial (SPI do research_plan.md) = vmed / limite de velocidade da aresta, com
o limite de Tables/faixas_limite_arestas.csv (OSM ou CTB art. 61).

Velocidade de madrugada (job 10086478, mesmo poligono e mesmos dias, 00:00-04:00):
mesmo casamento e mesma media harmonica, em colunas proprias (*_madrugada). E a
base da velocidade livre v0 do t0 (scripts/enrich_graph.py, Etapa 6).

Uso (da raiz do repositorio):
    python scripts/velocidades_traffic_stats.py

Entradas:
    Tables/traffic_stats_gama_julho.json       resultado do job do pico (download do portal/API)
    Tables/traffic_stats_gama_madrugada.json   resultado do job da madrugada
    cache/gama_drive_expanded.graphml
    Tables/faixas_limite_arestas.csv       (scripts/faixas_limite.py)
Saida:
    Tables/velocidades_arestas.csv
"""

import json
import math
import sys
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely import wkt
from shapely.geometry import LineString

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
TRAFFIC_STATS = RAIZ / "Tables/traffic_stats_gama_julho.json"
TRAFFIC_STATS_MADRUGADA = RAIZ / "Tables/traffic_stats_gama_madrugada.json"
GRAFO = RAIZ / "cache/gama_drive_expanded.graphml"
FAIXAS_LIMITE = RAIZ / "Tables/faixas_limite_arestas.csv"
SAIDA = RAIZ / "Tables/velocidades_arestas.csv"
CRS = "EPSG:31983"

BUFFER_M = 8              # trecho conta para a aresta se correr a ate 8 m dela
SOBREPOSICAO_MIN_M = 5    # ... por pelo menos 5 m
COS_SENTIDO = 0.7         # rumos alinhados (~45 graus no maximo)
COBERTURA_OK = 0.5        # fracao da aresta coberta por trechos com dado para valer
AMOSTRA_BAIXA = 0.01      # normalizedSampleSize abaixo disso: poucos veiculos
P85 = 16                  # speedPercentiles vem de 5 em 5 (5..95): indice 16 = p85


def carregar_trechos(arquivo: Path = TRAFFIC_STATS) -> gpd.GeoDataFrame:
    d = json.loads(arquivo.read_text(encoding="utf-8"))
    linhas = []
    for s in d["network"]["segmentResults"]:
        r = s["segmentTimeResults"][0]
        pct = r.get("speedPercentiles") or []
        linhas.append({
            "segmentId": s["segmentId"], "nome_tomtom": s.get("streetName"),
            "frc": s["frc"], "limite_tomtom": s.get("speedLimit"),
            "v_harm": r["harmonicAverageSpeed"], "v_mediana": r["medianSpeed"],
            "v_media": r["averageSpeed"], "v_p85": pct[P85] if len(pct) > P85 else None,
            "amostra": r["normalizedSampleSize"], "ttr": r["travelTimeRatio"],
            "geometry": LineString([(p["longitude"], p["latitude"]) for p in s["shape"]]),
        })
    info = {"job": d.get("jobName"), "periodo": f"{d['dateRanges'][0]['from']} a {d['dateRanges'][0]['to']}",
            "janela": d["timeSets"][0]["name"]}
    return gpd.GeoDataFrame(linhas, crs=4326).to_crs(CRS), info


def rumo_local(linha: LineString, ponto) -> np.ndarray:
    c = np.asarray(linha.coords)
    i = min(range(len(c) - 1), key=lambda k: LineString(c[k:k + 2]).distance(ponto))
    v = c[i + 1] - c[i]
    return v / (np.linalg.norm(v) or 1)


def casar(aresta: LineString, trechos: gpd.GeoDataFrame) -> list[tuple[int, float]]:
    """(indice do trecho, comprimento sobreposto) dos trechos que correm junto
    da aresta e no mesmo sentido."""
    zona = aresta.buffer(BUFFER_M)
    casados = []
    for i in trechos.sindex.query(zona, predicate="intersects"):
        seg = trechos.geometry.iloc[i]
        parte = seg.intersection(zona)
        if parte.length < SOBREPOSICAO_MIN_M:
            continue
        meio = parte.interpolate(0.5, normalized=True)
        if float(rumo_local(seg, meio) @ rumo_local(aresta, meio)) < COS_SENTIDO:
            continue
        casados.append((i, parte.length))
    return casados


def harmonica(geom: LineString, trechos: gpd.GeoDataFrame) -> tuple[float | None, float, float | None]:
    """(velocidade harmonica ponderada, cobertura, amostra) dos trechos com dado."""
    com_dado = [(i, w) for i, w in casar(geom, trechos) if trechos["v_harm"].iloc[i] > 0]
    if not com_dado:
        return None, 0.0, None
    w_total = sum(w for _, w in com_dado)
    v = w_total / sum(w / trechos["v_harm"].iloc[i] for i, w in com_dado)
    amostra = sum(trechos["amostra"].iloc[i] * w for i, w in com_dado) / w_total
    return v, min(w_total / geom.length, 1.0), amostra


def main() -> None:
    trechos, info = carregar_trechos()
    madrugada, info_m = carregar_trechos(TRAFFIC_STATS_MADRUGADA)
    G = nx.read_graphml(GRAFO)
    limites = pd.read_csv(FAIXAS_LIMITE).set_index("edge_id")
    pos = {n: (float(d["x"]), float(d["y"])) for n, d in G.nodes(data=True)}

    linhas = []
    for u, v, d in G.edges(data=True):
        eid = f"{u}:{v}:0"
        geom = wkt.loads(d["geometry"]) if "geometry" in d else LineString([pos[u], pos[v]])
        L = geom.length
        casados = casar(geom, trechos)
        com_dado = [(i, w) for i, w in casados if trechos["v_harm"].iloc[i] > 0]

        def ponderada(col, pares):
            vals = [(trechos[col].iloc[i], w) for i, w in pares if pd.notna(trechos[col].iloc[i])]
            return sum(x * w for x, w in vals) / sum(w for _, w in vals) if vals else None

        w_total = sum(w for _, w in com_dado)
        vmed = (w_total / sum(w / trechos["v_harm"].iloc[i] for i, w in com_dado)) if com_dado else None
        cobertura = min(w_total / L, 1.0) if L else 0.0
        amostra = ponderada("amostra", com_dado)
        status = ("ok" if cobertura >= COBERTURA_OK else "parcial") if com_dado else (
            "trecho sem dado" if casados else "sem trecho TomTom")

        lim = limites["maxspeed_kmh"].get(eid)
        v_m, cob_m, am_m = harmonica(geom, madrugada)
        linhas.append({
            "edge_id": eid, "u": u, "v": v, "nome": d.get("name"),
            "highway": d["highway"], "length_m": round(L, 1),
            "vmed_kmh": round(vmed, 1) if vmed else None,
            "v_mediana_kmh": round(ponderada("v_mediana", com_dado), 1) if com_dado else None,
            "v_p85_kmh": round(ponderada("v_p85", com_dado), 1) if com_dado else None,
            "maxspeed_kmh": lim,
            "k_inicial": round(vmed / lim, 3) if vmed and pd.notna(lim) and status == "ok" else None,
            "cobertura": round(cobertura, 2),
            "amostra_normalizada": round(amostra, 4) if amostra is not None else None,
            "amostra_baixa": bool(amostra is not None and amostra < AMOSTRA_BAIXA),
            "n_trechos": len(casados), "n_trechos_com_dado": len(com_dado),
            "limite_tomtom_kmh": ponderada("limite_tomtom", casados),
            "status": status,
            "v_madrugada_kmh": round(v_m, 1) if v_m else None,
            "cobertura_madrugada": round(cob_m, 2),
            "amostra_madrugada": round(am_m, 4) if am_m is not None else None,
            "segment_ids": ";".join(str(trechos["segmentId"].iloc[i]) for i, _ in casados),
        })

    t = pd.DataFrame(linhas)
    t.loc[t["highway"] == "busway", ["status", "k_inicial", "v_madrugada_kmh"]] = ["corredor de onibus", None, None]
    t.to_csv(SAIDA, index=False, encoding="utf-8-sig")

    usados = {int(s) for ids in t["segment_ids"] if ids for s in ids.split(";")}
    print(f"Traffic Stats '{info['job']}': {info['periodo']}, {info['janela']} | "
          f"{len(trechos)} trechos, {int((trechos['v_harm'] > 0).sum())} com velocidade, "
          f"{len(usados)} casados com arestas")
    print(f"\n{len(t)} arestas -> {SAIDA.relative_to(RAIZ)}")
    print(t["status"].value_counts().to_string())
    ok = t[t["status"] == "ok"]
    print(f"\nPor classe (arestas ok / total, mediana de vmed e de K):")
    resumo = t.groupby("highway").agg(total=("edge_id", "size"))
    resumo["ok"] = ok.groupby("highway").size()
    resumo["vmed_mediana"] = ok.groupby("highway")["vmed_kmh"].median()
    resumo["k_mediano"] = ok.groupby("highway")["k_inicial"].median()
    print(resumo.fillna(0).round(2).to_string())
    print(f"\nArestas ok com amostra baixa (< {AMOSTRA_BAIXA}): {int(ok['amostra_baixa'].sum())}")
    print(f"K inicial: {ok['k_inicial'].describe()[['min', '25%', '50%', '75%', 'max']].round(2).to_dict()}")
    m = t[t["cobertura_madrugada"] >= COBERTURA_OK]
    print(f"\nMadrugada '{info_m['janela']}': {len(m)} arestas com velocidade "
          f"(cobertura >= {COBERTURA_OK}), {int((m['amostra_madrugada'] < AMOSTRA_BAIXA).sum())} com amostra baixa")


if __name__ == "__main__":
    main()
