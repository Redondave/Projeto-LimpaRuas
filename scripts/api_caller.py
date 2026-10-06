# Script para chamar a API de TomTom para obter dados de fluxo de tráfego para cada aresta em um grafo OSMnx.

"""Usage:
    set TOMTOM_API_KEY=your_key
    python scripts/api_caller.py
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests

# Define os paths e parâmetros de configuração
INPUT_GEOPACKAGE = Path("../cache/gama_drive_reduced.gpkg")
OUTPUT_GEOPACKAGE = Path("../cache/gama_drive_reduced_tomtom.gpkg")
INPUT_LAYER = "edges"

ZOOM = 10
BASE_URL = (
    "https://api.tomtom.com/traffic/services/4/"
    "flowSegmentData/absolute/{zoom}/json"
)
REQS_PER_SECOND = 4
REQUEST_INTERVAL = 1.0 / REQS_PER_SECOND
MAX_ATTEMPTS = 4
CHECKPOINT = Path("../cache/tomtom_flow_results.jsonl")

# Colunas para mapeamento no json retornado pela API da TomTom
TOMTOM_COLUMNS = {
    "tomtom_current_speed": "currentSpeed",
    "tomtom_free_flow_speed": "freeFlowSpeed",
    "tomtom_current_travel_time": "currentTravelTime",
    "tomtom_free_flow_travel_time": "freeFlowTravelTime",
    "tomtom_confidence": "confidence",
    "tomtom_road_closure": "roadClosure",
    "tomtom_query_lat": "queryLat",
    "tomtom_query_lon": "queryLon",
}

# Retorna um identificador único para cada aresta, baseado nos nós de origem, destino e chave da aresta.
def edge_id(row: Any) -> str:
    return f"{int(row['u'])}:{int(row['v'])}:{int(row['key'])}"


# Carrega os resultados previamente salvos em checkpoint, se existirem, para evitar chamadas repetidas à API.
def load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return results
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            try:
                record = json.loads(line)
                if record.get("edge_id"):
                    results[record["edge_id"]] = record
            except json.JSONDecodeError:
                continue
    return results


def call_flow_segment(
    session: requests.Session, lat: float, lon: float, api_key: str
) -> dict[str, Any]:
    params = {"key": api_key, "point": f"{lat:.7f},{lon:.7f}"}
    last_error = "no response"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = session.get(
            BASE_URL.format(zoom=ZOOM), params=params, timeout=20
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json()}

        last_error = f"{response.status_code}: {response.text[:300]}"
        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else 2**attempt
            time.sleep(wait)
            continue

        return {"success": False, "error": last_error}

    return {"success": False, "error": f"Attempts exhausted: {last_error}"}


# Cria o ponto médio em WGS84 para cada aresta, sem assumir o CRS de entrada, a fim de consultar a API da TomTom com segurança.
def midpoint_wgs84(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if edges.crs is None:
        raise ValueError("The edges layer has no CRS; cannot query TomTom safely.")
    projected_midpoints = edges.geometry.interpolate(0.5, normalized=True)
    return gpd.GeoSeries(
        projected_midpoints, index=edges.index, crs=edges.crs
    ).to_crs("EPSG:4326")


def flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    flow = record.get("data", {}).get("flowSegmentData", {})
    flattened = {
        "tomtom_success": record.get("success", False),
        "tomtom_error": record.get("error"),
    }
    flattened.update(
        {
            output: flow.get(source)
            for output, source in TOMTOM_COLUMNS.items()
            if source not in {"queryLat", "queryLon"}
        }
    )
    flattened["tomtom_query_lat"] = record.get("lat")
    flattened["tomtom_query_lon"] = record.get("lon")
    return flattened


def write_output(
    nodes: gpd.GeoDataFrame,
    edges: gpd.GeoDataFrame,
    results: dict[str, dict[str, Any]],
) -> None:
    output = edges.copy()
    for column in ["tomtom_success", "tomtom_error", *TOMTOM_COLUMNS]:
        output[column] = [None] * len(output)

    for index, row in output.iterrows():
        output.loc[index, list(flatten_record(results[edge_id(row)]))] = list(
            flatten_record(results[edge_id(row)]).values()
        )

    OUTPUT_GEOPACKAGE.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_GEOPACKAGE.exists():
        OUTPUT_GEOPACKAGE.unlink()
    nodes.to_file(OUTPUT_GEOPACKAGE, layer="nodes", driver="GPKG", index=False)
    output.to_file(OUTPUT_GEOPACKAGE, layer="edges", driver="GPKG", index=False)


def main() -> None:
    api_key = os.environ.get("TOMTOM_API_KEY")
    if not api_key:
        sys.exit("Set TOMTOM_API_KEY before running this script.")
    if not INPUT_GEOPACKAGE.exists():
        sys.exit(f"Input GeoPackage not found: {INPUT_GEOPACKAGE}")

    nodes = gpd.read_file(INPUT_GEOPACKAGE, layer="nodes")
    edges = gpd.read_file(INPUT_GEOPACKAGE, layer=INPUT_LAYER)
    required = {"u", "v", "key", "geometry"}
    missing = required - set(edges.columns)
    if missing:
        sys.exit(f"Missing required edge columns: {sorted(missing)}")

    points = midpoint_wgs84(edges)
    results = load_checkpoint(CHECKPOINT)
    pending = [
        (index, row)
        for index, row in edges.iterrows()
        if edge_id(row) not in results
    ]
    print(f"{len(pending)} edges to query; {len(results)} already checkpointed.")

    session = requests.Session()
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    with CHECKPOINT.open("a", encoding="utf-8") as checkpoint:
        for position, (index, row) in enumerate(pending, start=1):
            point = points.loc[index]
            lon, lat = point.x, point.y
            result = call_flow_segment(session, lat, lon, api_key)
            record = {
                "edge_id": edge_id(row),
                "u": int(row["u"]),
                "v": int(row["v"]),
                "key": int(row["key"]),
                "lat": lat,
                "lon": lon,
                **result,
            }
            checkpoint.write(json.dumps(record, ensure_ascii=False) + "\n")
            checkpoint.flush()
            results[record["edge_id"]] = record
            status = "ok" if result["success"] else f"failed: {result['error']}"
            print(f"[{position}/{len(pending)}] {record['edge_id']}: {status}")
            time.sleep(REQUEST_INTERVAL)

    write_output(nodes, edges, results)
    print(f"TomTom-enriched GeoPackage written to {OUTPUT_GEOPACKAGE}")


if __name__ == "__main__":
    main()
