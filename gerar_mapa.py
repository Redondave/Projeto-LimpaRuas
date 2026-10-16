import osmnx as ox
import geopandas as gpd

# 1. Carregar o arquivo GraphML
# Substitua 'rede.graphml' pelo caminho do seu arquivo
G = ox.load_graphml(r"D:\Projetos_UnB\Semestre_6\Projeto-LimpaRuas\cache\gama_drive_expanded.graphml")

# Adicione esta linha para imprimir a quantidade de vértices (nós) e arestas
print(f"O grafo possui {G.number_of_nodes()} vértices e {G.number_of_edges()} arestas.")

# 2. Converter o grafo do NetworkX para GeoDataFrames
gdf_nodes, gdf_edges = ox.graph_to_gdfs(G)

# 3. Definir o sistema de coordenadas atual (UTM 23S) e re-projetar para Lat/Lon
if gdf_nodes.crs is None:
    gdf_nodes.set_crs(epsg=31983, inplace=True)
    gdf_edges.set_crs(epsg=31983, inplace=True)

gdf_nodes = gdf_nodes.to_crs(epsg=4326)
gdf_edges = gdf_edges.to_crs(epsg=4326)

# 4. Criar o mapa interativo
# Desenha as arestas (ruas) com dicas contendo o nome da via
mapa = gdf_edges.explore(
    color="blue", 
    tooltip="name", 
    style_kwds={'weight': 2}
)

# Desenha os nós (interseções) por cima das arestas
gdf_nodes.explore(
    m=mapa, 
    color="red", 
    marker_kwds={'radius': 3}
)

# 5. Salvar o resultado
mapa.save("mapa_viario.html")
print("Mapa salvo com sucesso em 'mapa_viario.html'. Abra no seu navegador.")