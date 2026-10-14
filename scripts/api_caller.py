# Coletor de velocidades da TomTom (Flow Segment Data) no horario de pico, para
# cada aresta do grafo do Gama.

"""
Uso:
    set TOMTOM_API_KEY=sua_chave          (Windows)  /  export TOMTOM_API_KEY=...
    python scripts/api_caller.py              # coleta uma rodada, se estiver na janela
    python scripts/api_caller.py --verificar  # so diz se deve coletar agora (sem API)
    python scripts/api_caller.py --forcar     # coleta agora, fora da janela, em
                                              # cache/tomtom_flow_teste.jsonl (nao conta
                                              # como rodada nem e commitado)

Regras da coleta oficial (todas checadas antes de gastar cota):
  - so em dia util (seg-sex, fora de FERIADOS), entre 18:00 e 19:00 de Brasilia,
    a mesma janela da matriz OD;
  - no maximo MAX_RODADAS_DIA rodadas por dia, com INTERVALO_MIN_MIN entre elas,
    para caber na cota gratuita (2.500 req/dia) e espalhar as rodadas pela hora;
  - para sozinha quando houver DIAS_ALVO dias uteis com pelo menos
    MIN_RODADAS_DIA rodadas cada (dias com poucas rodadas nao contam).

O GitHub Actions nao garante o horario do cron (ja rodou com 3 h de atraso). Por
isso o workflow dispara a cada 5 min antes e durante a janela, e este script
decide se a rodada vale. Disparos fora da janela saem sem chamar a API.

Cada rodada grava uma linha por aresta em HISTORY_FILE, com a qualidade do
"encaixe" do segmento devolvido pela TomTom na aresta consultada:
    snap_dist_m  distancia do ponto consultado ao segmento devolvido
    snap_cos     alinhamento entre a aresta e o segmento (1 = mesmo sentido,
                 -1 = sentido oposto)
Na agregacao, descartar leituras com snap_dist_m alto: o segmento e de outra via.
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]

# ---------------- CONFIGURACAO ----------------
INPUT_GEOPACKAGE = RAIZ / "cache/gama_drive_expanded.gpkg"
OUTPUT_GEOPACKAGE = RAIZ / "cache/gama_drive_expanded_tomtom.gpkg"   # ultima rodada, para o QGIS
HISTORY_FILE = RAIZ / "cache/tomtom_flow_history.jsonl"
TESTE_FILE = RAIZ / "cache/tomtom_flow_teste.jsonl"            # destino do --forcar
INPUT_LAYER = "edges"

# Zoom define quais classes de via a TomTom considera ao encaixar o ponto. Com
# zoom 10, so as vias principais: nas terciarias o segmento devolvido ficava a
# ~300 m (mediana), na DF-480 ou na EPCT. Zoom alto inclui as vias locais.
ZOOM = int(os.environ.get("TOMTOM_ZOOM", "18"))
BASE_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/{zoom}/json"
REQS_PER_SECOND = 4
REQUEST_INTERVAL = 1.0 / REQS_PER_SECOND
MAX_ATTEMPTS = 4

BRT = timezone(timedelta(hours=-3))       # Brasil nao tem horario de verao desde 2019
JANELA = ((18, 0), (19, 0))               # mesma janela da matriz OD (18-19h)
MAX_RODADAS_DIA = 8                       # 8 x 236 arestas < 2.500 req/dia
INTERVALO_MIN_MIN = 7                     # minutos entre rodadas do mesmo dia
DIAS_ALVO = 5
MIN_RODADAS_DIA = 3
FERIADOS = {date(2026, 10, 28),           # Dia do Servidor (ponto facultativo no GDF)
            date(2026, 11, 2), date(2026, 11, 20)}


# ---------------------------------------------------------------------------
# 1. Decidir se a rodada vale (so biblioteca padrao: roda antes do pip install)
# ---------------------------------------------------------------------------
def rodadas_por_dia() -> dict[date, list[datetime]]:
    """Inicio de cada rodada ja gravada, agrupado pelo dia em Brasilia."""
    inicios = set()
    if HISTORY_FILE.exists():
        with HISTORY_FILE.open(encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    inicios.add(json.loads(linha)["rodada"])
    dias: dict[date, list[datetime]] = {}
    for r in sorted(inicios):
        t = datetime.fromisoformat(r).astimezone(BRT)
        dias.setdefault(t.date(), []).append(t)
    return dias


def verificar(agora: datetime) -> tuple[bool, str]:
    agora = agora.astimezone(BRT)
    dias = rodadas_por_dia()
    completos = [d for d, r in dias.items() if len(r) >= MIN_RODADAS_DIA]
    if len(completos) >= DIAS_ALVO and agora.date() not in dias:
        return False, f"coleta concluida: {len(completos)} dias uteis com {MIN_RODADAS_DIA}+ rodadas"
    if agora.weekday() >= 5 or agora.date() in FERIADOS:
        return False, "nao e dia util"
    (h0, m0), (h1, m1) = JANELA
    inicio, fim = agora.replace(hour=h0, minute=m0, second=0), agora.replace(hour=h1, minute=m1, second=0)
    if not inicio <= agora < fim:
        return False, f"fora da janela {h0:02d}:{m0:02d}-{h1:02d}:{m1:02d} ({agora:%H:%M} em Brasilia)"
    hoje = dias.get(agora.date(), [])
    if len(hoje) >= MAX_RODADAS_DIA:
        return False, f"ja ha {len(hoje)} rodadas hoje"
    if hoje and agora - hoje[-1] < timedelta(minutes=INTERVALO_MIN_MIN):
        return False, f"ultima rodada ha menos de {INTERVALO_MIN_MIN} min"
    return True, f"rodada {len(hoje) + 1} de hoje, dia {len(completos) + (agora.date() not in completos)} de {DIAS_ALVO}"


# ---------------------------------------------------------------------------
# 2. Coleta
# ---------------------------------------------------------------------------
def edge_id(row: Any) -> str:
    return f"{int(row['u'])}:{int(row['v'])}:{int(row['key'])}"


def midpoint_wgs84(edges):
    import geopandas as gpd
    if edges.crs is None:
        raise ValueError("The edges layer has no CRS; cannot query TomTom safely.")
    projected_midpoints = edges.geometry.interpolate(0.5, normalized=True)
    return gpd.GeoSeries(projected_midpoints, index=edges.index, crs=edges.crs).to_crs("EPSG:4326")


def call_flow_segment(session, lat: float, lon: float, api_key: str) -> dict[str, Any]:
    params = {"key": api_key, "point": f"{lat:.7f},{lon:.7f}"}
    last_error = "no response"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = session.get(BASE_URL.format(zoom=ZOOM), params=params, timeout=20)
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        last_error = f"{response.status_code}: {response.text[:300]}"
        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after else 2**attempt)
            continue
        return {"success": False, "error": last_error}
    return {"success": False, "error": f"Attempts exhausted: {last_error}"}


def qualidade_encaixe(flow: dict, aresta, ponto_proj, crs) -> tuple[float | None, float | None]:
    """Distancia do ponto consultado ao segmento devolvido e alinhamento entre
    os dois, medidos no sistema metrico do grafo."""
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString

    coords = flow.get("coordinates", {}).get("coordinate", [])
    if len(coords) < 2:
        return None, None
    seg = gpd.GeoSeries([LineString([(c["longitude"], c["latitude"]) for c in coords])],
                        crs="EPSG:4326").to_crs(crs).iloc[0]

    def rumo_local(linha):
        c = np.asarray(linha.coords)
        i = min(range(len(c) - 1), key=lambda k: LineString(c[k:k + 2]).distance(ponto_proj))
        d = c[i + 1] - c[i]
        return d / (np.linalg.norm(d) or 1)

    return round(float(seg.distance(ponto_proj)), 1), round(float(rumo_local(seg) @ rumo_local(aresta)), 2)


def write_latest_output(nodes, edges, ultimos: dict[str, dict[str, Any]]) -> None:
    """GeoPackage com a ultima rodada, para conferencia no QGIS (nao e commitado)."""
    output = edges.copy()
    campos = ["success", "frc", "currentSpeed", "freeFlowSpeed", "confidence",
              "roadClosure", "snap_dist_m", "snap_cos"]
    for campo in campos:
        output[f"tomtom_{campo}"] = [ultimos.get(edge_id(r), {}).get(campo) for _, r in output.iterrows()]
    if OUTPUT_GEOPACKAGE.exists():
        OUTPUT_GEOPACKAGE.unlink()
    nodes.to_file(OUTPUT_GEOPACKAGE, layer="nodes", driver="GPKG", index=False)
    output.to_file(OUTPUT_GEOPACKAGE, layer="edges", driver="GPKG", index=False)


def coletar(api_key: str, destino: Path) -> None:
    import geopandas as gpd
    import requests

    nodes = gpd.read_file(INPUT_GEOPACKAGE, layer="nodes")
    edges = gpd.read_file(INPUT_GEOPACKAGE, layer=INPUT_LAYER)
    missing = {"u", "v", "key", "geometry"} - set(edges.columns)
    if missing:
        sys.exit(f"Missing required edge columns: {sorted(missing)}")

    pontos_proj = edges.geometry.interpolate(0.5, normalized=True)
    pontos = midpoint_wgs84(edges)
    # as duas maos de uma via de mao dupla tem o mesmo ponto medio: consulta uma vez
    chaves = [f"{p.y:.7f},{p.x:.7f}" for p in pontos]
    unicos = list(dict.fromkeys(chaves))
    rodada = datetime.now(BRT)
    print(f"Rodada {rodada:%d/%m %H:%M}: {len(edges)} arestas, {len(unicos)} pontos unicos, zoom {ZOOM}")

    session = requests.Session()
    respostas: dict[str, dict] = {}
    for i, chave in enumerate(unicos, start=1):
        lat, lon = map(float, chave.split(","))
        respostas[chave] = call_flow_segment(session, lat, lon, api_key) | {
            "momento": datetime.now(BRT).isoformat(timespec="seconds")}
        if i % 25 == 0:
            print(f"  {i}/{len(unicos)} pontos")
        time.sleep(REQUEST_INTERVAL)

    ultimos = {}
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("a", encoding="utf-8") as history:
        for (index, row), chave in zip(edges.iterrows(), chaves):
            res = respostas[chave]
            flow = res.get("data", {}).get("flowSegmentData", {}) if res["success"] else {}
            dist, cos = qualidade_encaixe(flow, row.geometry, pontos_proj[index], edges.crs) if flow else (None, None)
            momento = datetime.fromisoformat(res["momento"])
            record = {
                "rodada": rodada.isoformat(timespec="seconds"),
                "momento": res["momento"],
                "dia_semana": momento.weekday(),          # 0 = segunda, horario de Brasilia
                "hora": momento.hour,
                "edge_id": edge_id(row),
                "u": int(row["u"]), "v": int(row["v"]), "key": int(row["key"]),
                "lat": float(chave.split(",")[0]), "lon": float(chave.split(",")[1]),
                "zoom": ZOOM,
                "success": res["success"],
                "error": res.get("error"),
                "frc": flow.get("frc"),
                "currentSpeed": flow.get("currentSpeed"),
                "freeFlowSpeed": flow.get("freeFlowSpeed"),
                "currentTravelTime": flow.get("currentTravelTime"),
                "freeFlowTravelTime": flow.get("freeFlowTravelTime"),
                "confidence": flow.get("confidence"),
                "roadClosure": flow.get("roadClosure"),
                "snap_dist_m": dist,
                "snap_cos": cos,
            }
            history.write(json.dumps(record, ensure_ascii=False) + "\n")
            ultimos[record["edge_id"]] = record

    ok = [r for r in ultimos.values() if r["success"]]
    longe = sum(1 for r in ok if r["snap_dist_m"] is not None and r["snap_dist_m"] > 20)
    print(f"Sucesso em {len(ok)}/{len(ultimos)} arestas | segmento a mais de 20 m da aresta: {longe} "
          f"| gravado em {destino.name}")
    write_latest_output(nodes, edges, ultimos)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificar", action="store_true",
                    help="so decide se deve coletar agora; escreve coletar=true/false no GITHUB_OUTPUT")
    ap.add_argument("--forcar", action="store_true", help="ignora a janela (teste)")
    args = ap.parse_args()

    pode, motivo = verificar(datetime.now(timezone.utc))
    print(("COLETAR: " if pode else "PULAR: ") + motivo)
    if args.verificar:
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
                out.write(f"coletar={'true' if pode else 'false'}\n")
        return
    if not (pode or args.forcar):
        return

    api_key = os.environ.get("TOMTOM_API_KEY")
    if not api_key:
        sys.exit("Set TOMTOM_API_KEY before running this script.")
    if not INPUT_GEOPACKAGE.exists():
        sys.exit(f"Input GeoPackage not found: {INPUT_GEOPACKAGE}")
    coletar(api_key, HISTORY_FILE if pode else TESTE_FILE)


if __name__ == "__main__":
    main()
