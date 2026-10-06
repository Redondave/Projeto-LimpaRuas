# Script para converter o grafo em GraphML para GeoPackage, aplicando o esquema de referência e normalizando valores nulos.

from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd



GRAPHML_PATH = Path("../cache/gama_drive_reduced.graphml")
GEOPACKAGE_PATH = Path("../cache/gama_drive_reduced.gpkg")
CRS = "EPSG:31983"

NODE_COLUMNS = {
    "osmid": "int64",
    "y": "float64",
    "x": "float64",
    "street_count": "int64",
    "highway": "string",
}
EDGE_COLUMNS = {
    "u": "int64",
    "v": "int64",
    "key": "int64",
    "osmid": "string",
    "highway": "string",
    "lanes": "string",
    "maxspeed": "string",
    "ref": "string",
    "oneway": "boolean",
    "reversed": "string",
    "length": "float64",
    "name": "string",
    "bridge": "string",
    "junction": "string",
    "access": "string",
}


def normalize_nulls(frame: gpd.GeoDataFrame, columns: dict[str, str]) -> gpd.GeoDataFrame:
    """Apply the reference schema and write missing values as real SQL NULLs."""
    result = frame.copy()
    for column, dtype in columns.items():
        nullable_dtype = {
            "int64": "Int64",
            "float64": "Float64",
            "boolean": "boolean",
            "string": "string",
        }[dtype]
        if column not in result:
            result[column] = pd.Series(
                pd.NA, index=result.index, dtype=nullable_dtype
            )
        else:
            result[column] = result[column].replace(
                {"nan": pd.NA, "None": pd.NA, "null": pd.NA}
            )
            result[column] = result[column].astype(nullable_dtype)

    result = result[list(columns) + ["geometry"]]
    return result


def convert() -> None:
    graph = ox.load_graphml(GRAPHML_PATH)
    nodes, edges = ox.graph_to_gdfs(
        graph,
        nodes=True,
        edges=True,
        node_geometry=True,
        fill_edge_geometry=True,
    )

    nodes = nodes.reset_index()
    edges = edges.reset_index()
    nodes = normalize_nulls(nodes, NODE_COLUMNS)
    edges = normalize_nulls(edges, EDGE_COLUMNS)
    nodes = nodes.set_crs(CRS, allow_override=True)
    edges = edges.set_crs(CRS, allow_override=True)

    GEOPACKAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if GEOPACKAGE_PATH.exists():
        GEOPACKAGE_PATH.unlink()
    nodes.to_file(GEOPACKAGE_PATH, layer="nodes", driver="GPKG", index=False)
    edges.to_file(GEOPACKAGE_PATH, layer="edges", driver="GPKG", index=False)


if __name__ == "__main__":
    convert()
