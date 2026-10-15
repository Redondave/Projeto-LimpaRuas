"""
Coleta numero de faixas e limite de velocidade de cada aresta do grafo do Gama na
TomTom Snap to Roads API (Etapa 3 do research/o_que_falta_fazer_pre_frank_wolfe.md).

Por que esta API, e nao a Flow API do api_caller.py: a Flow API so devolve
velocidades. A Snap to Roads recebe um trajeto (pontos em sequencia), o encaixa
na malha da TomTom e devolve, para cada elemento de via percorrido, os atributos
do mapa: laneInfo.numberOfLanes, speedLimits (type "Maximum" = limite legal),
frc, formOfWay e roadUse. Cada aresta vira um trajeto curto no SENTIDO DE
CIRCULACAO, com o rumo (heading) de cada ponto. Assim o encaixe cai na pista
certa das vias duplicadas e nao "pula" para a via principal ao lado, como
acontecia com um ponto isolado na Flow API.

Os pontos ficam entre 10% e 90% do comprimento da aresta, para nao encaixar na
via transversal do cruzamento. Cada elemento devolvido pesa pelo trecho que
coincide com a aresta (ate BUFFER_M de distancia); o valor adotado e o de maior
peso, e a fracao de concordancia fica registrada.

Validacao embutida (vai para o relatorio): onde o OSM tambem informa lanes e
maxspeed, mede a concordancia. Em via de mao dupla tambem testa se numberOfLanes
da TomTom conta as duas maos ou uma so; a documentacao nao diz.

Uso (da raiz do repositorio):
    set TOMTOM_API_KEY=...       (a chave precisa ter a Snap to Roads API habilitada)
    python scripts/coletar_atributos_via.py --limite 10   # teste com 10 arestas
    python scripts/coletar_atributos_via.py               # todas (236 requisicoes)
    python scripts/coletar_atributos_via.py --offline     # refaz as tabelas a partir do bruto

A coleta pode ser interrompida e retomada: arestas ja gravadas no bruto sao puladas.
Os atributos do mapa nao dependem do horario: basta uma coleta.

Saidas:
    cache/tomtom_atributos_bruto.jsonl         resposta da API por aresta (checkpoint)
    Tables/atributos_tomtom_arestas.csv        faixas e limite por aresta, com qualidade
    Tables/atributos_tomtom_relatorio.json     cobertura e concordancia com o OSM
"""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import LineString

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]

# ---------------- CONFIGURACAO ----------------
GPKG = RAIZ / "cache/gama_drive_expanded.gpkg"
BRUTO = RAIZ / "cache/tomtom_atributos_bruto.jsonl"
SAIDA = RAIZ / "Tables/atributos_tomtom_arestas.csv"
RELATORIO = RAIZ / "Tables/atributos_tomtom_relatorio.json"

URL = "https://api.tomtom.com/snapToRoads/1"
FIELDS = ("{projectedPoints{type,geometry{type,coordinates},properties{routeIndex,snapResult}},"
          "route{type,geometry{type,coordinates},properties{id,speedLimits{value,unit,type},"
          "frc,formOfWay,roadUse,laneInfo{numberOfLanes},traveledDistance{value,unit}}}}")
PASSO_M = 20            # um ponto a cada 20 m ao longo da aresta
MARGEM = 0.10           # ignora 10% de cada ponta (cruzamentos)
MIN_PONTOS, MAX_PONTOS = 3, 25
BUFFER_M = 10           # elemento da TomTom conta para a aresta se estiver a ate 10 m dela
COBERTURA_MIN = 0.6     # fracao da aresta que precisa ser coberta para a leitura valer
CONCORDANCIA_MIN = 0.7  # fracao do comprimento coberto que precisa ter o valor adotado
REQUEST_INTERVAL = 0.25
MAX_ATTEMPTS = 4


def edge_id(row) -> str:
    return f"{int(row['u'])}:{int(row['v'])}:{int(row['key'])}"


# ---------------------------------------------------------------------------
# 1. Trajeto de cada aresta
# ---------------------------------------------------------------------------
def trajeto(geom: LineString, crs) -> tuple[list, list]:
    """Pontos (lon, lat) em sequencia no sentido da aresta e o rumo em cada um."""
    L = geom.length
    margem = MARGEM if L >= 10 else 0.25
    a, b = margem * L, (1 - margem) * L
    n = int(np.clip(math.ceil((b - a) / PASSO_M) + 1, MIN_PONTOS, MAX_PONTOS))
    dists = np.linspace(a, b, n)
    pts = [geom.interpolate(d) for d in dists]
    rumos = []
    for d in dists:
        p0, p1 = geom.interpolate(max(d - 2, 0)), geom.interpolate(min(d + 2, L))
        rumos.append(round(math.degrees(math.atan2(p1.x - p0.x, p1.y - p0.y)) % 360, 1))
    ll = gpd.GeoSeries(pts, crs=crs).to_crs(4326)
    return [(round(p.x, 7), round(p.y, 7)) for p in ll], rumos


def consultar(session, chave: str, pontos: list, rumos: list) -> dict:
    params = {"key": chave, "fields": FIELDS, "vehicleType": "PassengerCar",
              "measurementSystem": "metric",
              "points": ";".join(f"{x},{y}" for x, y in pontos),
              "headings": ";".join(str(r) for r in rumos)}
    erro = "sem resposta"
    for tentativa in range(1, MAX_ATTEMPTS + 1):
        r = session.get(URL, params=params, timeout=30)
        if r.status_code == 200:
            return {"ok": True, "resposta": r.json()}
        erro = f"{r.status_code}: {r.text[:300]}"
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(float(r.headers.get("Retry-After", 2 ** tentativa)))
            continue
        break
    return {"ok": False, "erro": erro}


# ---------------------------------------------------------------------------
# 2. Resposta -> faixas e limite da aresta
# ---------------------------------------------------------------------------
def valor_osm(v):
    """OSM pode trazer lista ("['2', '3']") quando o OSMnx fundiu vias: usa o menor."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    nums = [float(x) for x in str(v).strip("[]").replace("'", "").split(",") if x.strip().replace(".", "").isdigit()]
    return min(nums) if nums else None


def km_h(limite: dict | None) -> float | None:
    if not limite or limite.get("type", "Maximum") != "Maximum" or limite.get("value") is None:
        return None
    return float(limite["value"]) * (1.609344 if limite.get("unit") == "mph" else 1.0)


def dominante(pesos: dict) -> tuple:
    """Valor de maior peso e a fracao do peso total que ele representa."""
    if not pesos:
        return None, None
    v = max(pesos, key=pesos.get)
    return v, round(pesos[v] / sum(pesos.values()), 2)


def resumir(geom: LineString, crs, registro: dict) -> dict:
    vazio = {"tt_lanes": None, "tt_lanes_concordancia": None, "tt_maxspeed_kmh": None,
             "tt_maxspeed_concordancia": None, "tt_frc": None, "tt_formOfWay": None,
             "tt_roadUse": None, "pontos_casados": None, "cobertura": None,
             "qualidade": "falhou", "erro": registro.get("erro")}
    if not registro.get("ok"):
        return vazio
    resp = registro["resposta"]
    proj = resp.get("projectedPoints", [])
    casados = sum(1 for p in proj if p.get("properties", {}).get("snapResult") == "Matched")
    zona = geom.buffer(BUFFER_M)
    L = geom.length
    trecho_util = (1 - 2 * (MARGEM if L >= 10 else 0.25)) * L

    pesos = {"lanes": {}, "max": {}, "frc": {}, "fow": {}, "uso": {}}
    coberto = 0.0
    for el in resp.get("route", []):
        coords = el.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        linha = gpd.GeoSeries([LineString(coords)], crs=4326).to_crs(crs).iloc[0]
        w = linha.intersection(zona).length
        if w <= 0:
            continue
        coberto += w
        p = el.get("properties", {})
        lanes = (p.get("laneInfo") or {}).get("numberOfLanes")
        for chave, valor in (("lanes", lanes), ("max", km_h(p.get("speedLimits"))),
                             ("frc", p.get("frc")), ("fow", p.get("formOfWay")),
                             ("uso", p.get("roadUse"))):
            if valor is not None:
                pesos[chave][valor] = pesos[chave].get(valor, 0) + w

    lanes, c_lanes = dominante(pesos["lanes"])
    vmax, c_max = dominante(pesos["max"])
    cobertura = round(min(coberto / trecho_util, 1.0), 2) if trecho_util > 0 else None
    boa = (cobertura or 0) >= COBERTURA_MIN and casados >= max(2, 0.8 * len(proj))
    return {"tt_lanes": lanes, "tt_lanes_concordancia": c_lanes,
            "tt_maxspeed_kmh": vmax, "tt_maxspeed_concordancia": c_max,
            "tt_frc": dominante(pesos["frc"])[0], "tt_formOfWay": dominante(pesos["fow"])[0],
            "tt_roadUse": dominante(pesos["uso"])[0],
            "pontos_casados": f"{casados}/{len(proj)}", "cobertura": cobertura,
            "qualidade": "ok" if boa else "parcial", "erro": None}


# ---------------------------------------------------------------------------
# 3. Relatorio: cobertura e concordancia com o OSM
# ---------------------------------------------------------------------------
def relatorio(t: pd.DataFrame) -> dict:
    ok = t[t["qualidade"] == "ok"]
    rel = {
        "arestas": len(t),
        "leitura_ok": int(len(ok)),
        "leitura_parcial": int((t["qualidade"] == "parcial").sum()),
        "falhou": int((t["qualidade"] == "falhou").sum()),
        "por_classe": {},
    }
    for classe, g in t.groupby("highway"):
        gok = g[g["qualidade"] == "ok"]
        rel["por_classe"][classe] = {
            "arestas": len(g),
            "com_lanes_osm": int(g["osm_lanes"].notna().sum()),
            "com_lanes_tomtom": int(gok["tt_lanes"].notna().sum()),
            "com_maxspeed_osm": int(g["osm_maxspeed"].notna().sum()),
            "com_maxspeed_tomtom": int(gok["tt_maxspeed_kmh"].notna().sum()),
        }

    # limite de velocidade: igualdade exata com o OSM onde os dois existem
    m = ok[ok["osm_maxspeed"].notna() & ok["tt_maxspeed_kmh"].notna()]
    rel["maxspeed_vs_osm"] = {
        "arestas_comparaveis": len(m),
        "iguais": int((m["osm_maxspeed"].round() == m["tt_maxspeed_kmh"].round()).sum()),
        "diferenca_mediana_kmh": float((m["tt_maxspeed_kmh"] - m["osm_maxspeed"]).median()) if len(m) else None,
    }

    # faixas: em mao unica o OSM conta o sentido; em mao dupla conta as duas maos.
    # Comparar com as duas leituras diz como a TomTom conta.
    lf = ok[ok["osm_lanes"].notna() & ok["tt_lanes"].notna()]
    unica = lf[lf["oneway"]]
    dupla = lf[~lf["oneway"]]
    rel["lanes_vs_osm"] = {
        "mao_unica": {"comparaveis": len(unica),
                      "iguais": int((unica["tt_lanes"] == unica["osm_lanes"]).sum())},
        "mao_dupla": {"comparaveis": len(dupla),
                      "tomtom_igual_total_osm": int((dupla["tt_lanes"] == dupla["osm_lanes"]).sum()),
                      "tomtom_igual_metade_osm": int((dupla["tt_lanes"] == dupla["osm_lanes"] / 2).sum())},
    }
    d = rel["lanes_vs_osm"]["mao_dupla"]
    if d["comparaveis"]:
        rel["lanes_interpretacao"] = (
            "numberOfLanes conta as duas maos" if d["tomtom_igual_total_osm"] > d["tomtom_igual_metade_osm"]
            else "numberOfLanes conta so o sentido de circulacao"
            if d["tomtom_igual_metade_osm"] > d["tomtom_igual_total_osm"] else "inconclusivo")
    return rel


def montar_tabela(edges: gpd.GeoDataFrame, brutos: dict) -> pd.DataFrame:
    linhas = []
    for _, row in edges.iterrows():
        eid = edge_id(row)
        base = {"edge_id": eid, "u": int(row["u"]), "v": int(row["v"]), "key": int(row["key"]),
                "highway": row["highway"], "oneway": bool(row["oneway"]),
                "length_m": round(float(row["length"]), 1),
                "osm_lanes": valor_osm(row.get("lanes")), "osm_maxspeed": valor_osm(row.get("maxspeed"))}
        if eid in brutos:
            base |= resumir(row.geometry, edges.crs, brutos[eid])
        else:
            base |= {"qualidade": "nao_coletada"}
        linhas.append(base)
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
def ler_brutos() -> dict:
    brutos = {}
    if BRUTO.exists():
        for linha in BRUTO.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                r = json.loads(linha)
                brutos[r["edge_id"]] = r
    return brutos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None, help="coletar so as N primeiras arestas pendentes")
    ap.add_argument("--offline", action="store_true", help="so refaz as tabelas a partir do bruto")
    args = ap.parse_args()

    edges = gpd.read_file(GPKG, layer="edges")
    brutos = ler_brutos()

    if not args.offline:
        chave = os.environ.get("TOMTOM_API_KEY")
        if not chave:
            sys.exit("Defina TOMTOM_API_KEY (com a Snap to Roads API habilitada).")
        pendentes = [(i, r) for i, r in edges.iterrows() if edge_id(r) not in brutos]
        if args.limite:
            pendentes = pendentes[:args.limite]
        print(f"{len(brutos)} arestas ja no bruto; coletando {len(pendentes)}")
        session = requests.Session()
        with BRUTO.open("a", encoding="utf-8") as f:
            for k, (_, row) in enumerate(pendentes, start=1):
                pontos, rumos = trajeto(row.geometry, edges.crs)
                reg = {"edge_id": edge_id(row), "pontos": pontos, "rumos": rumos,
                       **consultar(session, chave, pontos, rumos)}
                if not reg["ok"] and reg["erro"].startswith("403"):
                    sys.exit(f"403: a chave nao tem acesso a Snap to Roads API. {reg['erro']}")
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                f.flush()
                brutos[reg["edge_id"]] = reg
                if k % 20 == 0 or k == len(pendentes):
                    print(f"  {k}/{len(pendentes)}")
                time.sleep(REQUEST_INTERVAL)

    tabela = montar_tabela(edges, brutos)
    tabela.to_csv(SAIDA, index=False, encoding="utf-8")
    rel = relatorio(tabela[tabela["qualidade"] != "nao_coletada"])
    RELATORIO.write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nLeituras: {rel['leitura_ok']} ok, {rel['leitura_parcial']} parciais, {rel['falhou']} falharam "
          f"(de {rel['arestas']} coletadas)")
    print("Por classe (lanes OSM / TomTom | maxspeed OSM / TomTom):")
    for c, v in rel["por_classe"].items():
        print(f"  {c:14s} {v['arestas']:3d} arestas | lanes {v['com_lanes_osm']:3d} / {v['com_lanes_tomtom']:3d}"
              f" | maxspeed {v['com_maxspeed_osm']:3d} / {v['com_maxspeed_tomtom']:3d}")
    print(f"maxspeed igual ao OSM: {rel['maxspeed_vs_osm']}")
    print(f"lanes x OSM: {rel['lanes_vs_osm']}")
    print(f"Interpretacao de numberOfLanes: {rel.get('lanes_interpretacao', 'sem dados para decidir')}")
    print(f"\nTabela: {SAIDA} | relatorio: {RELATORIO}")


if __name__ == "__main__":
    main()
