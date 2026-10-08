import json
import pandas as pd
from pathlib import Path

# ---------------- CONFIGURAÇÃO ----------------
# MAPEAMENTO: ZONAS DO TOMTOM -> IDs DOS NÓS DO GRAFO (OSMnx)
# Você criou 7 Linhas (Portões) no TomTom. 
# Preencha abaixo com os IDs (osmid) dos nós que ficam exatamente nessas linhas.
ZONE_TO_NODES = {
    0: [], # Nós do Portão 0 (Region 1)
    1: [], # Nós do Portão 1 (Region 2)
    2: [], # Nós do Portão 2 (Region 3)
    3: [], # Nós do Portão 3 (Region 4)
    4: [], # Nós do Portão 4 (Region 5)
    5: [], # Nós do Portão 5 (Region 6)
    6: []  # Nós do Portão 6 (Region 7)
}

FILE_TOMTOM = Path('Tables/resultado_trips_tomtom.json')
FILE_OUTPUT = Path('Tables/od_matrix_nodes.csv')
# EXPANSÃO DE FROTA: A TomTom captura uma % da frota. Ajuste o multiplicador abaixo.
FATOR_EXPANSAO = 20.0  # Ex: multiplica os carros com GPS TomTom para estimar o total

def main():
    print('Lendo resultados da TomTom...')
    with open(FILE_TOMTOM, 'r') as f:
        data = json.load(f)
        
    links = data.get('links', [])
    
    zone_flows = {}
    for row in links:
        o_zone = int(row[0])
        d_zone = int(row[1])
        trips = float(row[-1]) * FATOR_EXPANSAO
        
        if o_zone == d_zone:
            continue
            
        pair = (o_zone, d_zone)
        zone_flows[pair] = zone_flows.get(pair, 0.0) + trips
        
    node_flows = []
    for (o_zone, d_zone), total_trips in zone_flows.items():
        o_nodes = ZONE_TO_NODES.get(o_zone, [])
        d_nodes = ZONE_TO_NODES.get(d_zone, [])
        
        if not o_nodes or not d_nodes:
            continue
            
        trips_per_pair = total_trips / (len(o_nodes) * len(d_nodes))
        
        for o_n in o_nodes:
            for d_n in d_nodes:
                node_flows.append({
                    'origin_node': o_n,
                    'destination_node': d_n,
                    'trips': trips_per_pair
                })
                
    if node_flows:
        df = pd.DataFrame(node_flows)
        df = df[df['trips'] > 0]
        df.to_csv(FILE_OUTPUT, index=False)
        print(f'\n✅ Matriz OD final salva em: {FILE_OUTPUT}')
        print(f'Total de rotas ativas: {len(df)}')
    else:
        print('\n❌ Você precisa preencher os IDs dos nós no script antes de rodar!')

if __name__ == '__main__':
    main()
