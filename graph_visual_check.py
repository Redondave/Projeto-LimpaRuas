# Script para validar o grafo criado em 'osmnx-api.py' e gerar uma visualização do grafo em um arquivo PNG.
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx

workspace = Path(r'd:\Usuario\Área de trabalho\Estudo\2026.2\CE\Projeto-LimpaRuas')
file_path = workspace / 'cache' / 'gama_drive_projected.graphml'
out_path = workspace / 'graph_visualization.png'

print(f'Input file: {file_path}')
print(f'Exists: {file_path.exists()}')

try:
    G = nx.read_graphml(file_path)
    print(f'Graph loaded successfully.')
    print(f'Nodes: {G.number_of_nodes()}')
    print(f'Edges: {G.number_of_edges()}')

    pos = {n: (float(d.get('x', 0)), float(d.get('y', 0))) for n, d in G.nodes(data=True) if 'x' in d and 'y' in d}
    if len(pos) < 2:
        pos = nx.spring_layout(G, seed=42)

    fig, ax = plt.subplots(figsize=(14, 14), dpi=150)
    ax.set_axis_off()
    nx.draw_networkx_edges(G, pos, alpha=0.4, edge_color='gray', width=0.8, ax=ax)
    nx.draw_networkx_nodes(G, pos, node_size=8, node_color='tab:blue', alpha=0.7, ax=ax)
    fig.savefig(out_path, bbox_inches='tight')
    plt.close(fig)
    print(f'Image saved to: {out_path}')
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')
    raise
