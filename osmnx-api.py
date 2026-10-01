# Script para criar o grafo da área viária do gama a partir do OSM, projetar para SIRGAS 2000 / UTM zone 23S (EPSG:31983) e salvar em GraphML e GeoPackage.
import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import shapely
import osmnx as ox
from shapely import is_valid, make_valid

GRAPH_PATH = Path("cache/gama_drive_projected.graphml")
LAYERS_PATH = Path("cache/gama_drive_projected.gpkg")


def with_unique_edge_keys(graph):
    normalized = nx.MultiDiGraph()
    normalized.graph.update(graph.graph)
    normalized.add_nodes_from(graph.nodes(data=True))

    for edge_id, (source, target, _key, data) in enumerate(
        graph.edges(keys=True, data=True)
    ):
        normalized.add_edge(source, target, key=edge_id, **data)

    return normalized

# 1. Carrega o limite oficial da RA Gama (disponível no Geoportal do DF)
geojson_data = json.load(open("cache/limite_gama.geojson"))
geom = shapely.geometry.shape(geojson_data["geometry"])

if not is_valid(geom):
    # Corrigir auto-interseções ou problemas de anel
    geom = make_valid(geom)

gdf_gama = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:31983")

# 2. OSMnx exige que o polígono de entrada esteja em latitude/longitude.
# O limite original está em SIRGAS 2000 / UTM 23S (EPSG:31983).
polygon = gdf_gama.to_crs("EPSG:4326").geometry.union_all()

# 3. Reutiliza a malha salva quando disponível; caso contrário, baixa e salva-a, normalizando os vértices para IDs únicos.
if GRAPH_PATH.exists():
    G_proj = ox.load_graphml(GRAPH_PATH)
    G_proj = with_unique_edge_keys(G_proj)
    ox.save_graphml(G_proj, filepath=GRAPH_PATH)
else:
    G = ox.graph_from_polygon(polygon, network_type="drive")

    # Converte a projeção para metros (UTM SIRGAS 2000 / UTM zone 23S - EPSG:31983), normalizando os vértices para IDs únicos
    G_proj = ox.project_graph(G, to_crs="EPSG:31983")
    G_proj = with_unique_edge_keys(G_proj)
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G_proj, filepath=GRAPH_PATH)

nodes_gdf, edges_gdf = ox.graph_to_gdfs(G_proj)

if not LAYERS_PATH.exists():
    nodes_gdf.to_file(LAYERS_PATH, layer="nodes", driver="GPKG", index=True)
    edges_gdf.to_file(LAYERS_PATH, layer="edges", driver="GPKG", index=True)