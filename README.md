# Projeto LimpaRuas

Otimização do índice de desempenho de velocidade (K) na malha viária do Gama (DF):
grafo da região, matriz origem-destino, velocidades observadas e atributos de via
para a alocação de tráfego por Frank-Wolfe. Plano completo em
`research/research_plan.md`; próximos passos em
`research/o_que_falta_fazer_pre_frank_wolfe.md`.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `cache/gama_drive_expanded.graphml` / `.gpkg` | Grafo de estudo: 134 nós, 236 arestas |
| `cache/gama_drive_expanded_atributos.graphml` | Grafo pronto para o Frank-Wolfe (`t0`, capacidade, `v0`, K observado); ler com `nx.read_graphml` |
| `cache/gama_area_estudo_osm.graphml` | Download do OpenStreetMap da área (fonte do grafo) |
| `cache/gama_drive_sample_30.graphml` | Grafo de 30 nós original: base dos ids `0`–`29` do grafo de estudo |
| `cache/gama_drive_expanded_portoes.geojson` | Caixas usadas na análise O/D da TomTom |
| `Tables/matriz_od_final.json` | Matriz OD nó a nó em veíc/h, com calibração e dados de validação |
| `Tables/od_tomtom_gama_final_bruto.json` | Resposta da TomTom O/D Analysis ("Gama Final") |
| `Tables/traffic_stats_gama_julho.json` | TomTom Traffic Stats (job 10086419): velocidades por trecho, julho/2026, dias úteis, 18–19h |
| `Tables/traffic_stats_gama_madrugada.json` | TomTom Traffic Stats (job 10086478): mesma área e mesmos dias, 00–04h (velocidade livre) |
| `Tables/velocidades_arestas.csv` | Velocidade observada e K inicial por aresta |
| `Tables/faixas_limite_arestas.csv` | Faixas por sentido e limite de velocidade por aresta (OSM + CTB) |
| `Tables/Roads.csv`, `Tables/trechos_com_coordenadas.csv` | Trechos do DER-DF e sua geometria (localizam os contadores) |

## Scripts

```bash
python scripts/expand_graph.py               # refaz o grafo de estudo (offline, a partir do cache)
python scripts/build_od_matrix.py --offline  # refaz a matriz OD a partir do bruto salvo
python scripts/faixas_limite.py              # faixas e limite por aresta
python scripts/velocidades_traffic_stats.py  # velocidade e K por aresta (usa faixas_limite)
python scripts/enrich_graph.py               # grafo atribuído: capacidade, t0 e checagens
python scripts/mapping.py                    # só se a tabela de trechos do DER mudar
```

O `build_od_matrix.py` sem `--offline` baixa a análise de novo e lê a chave da
variável `TOMTOM_API_KEY`.

## Dados do DETRAN

As contagens de tráfego calibram a matriz OD. O arquivo tem 134 MB e não fica no git:

1. Baixar um dos CSVs de [volume diário de tráfego do DETRAN](https://www.dados.df.gov.br/pt/dataset#/volume-diario-de-trafego-trechos-rodoviarios).
2. Salvar na raiz do repositório como `flow.csv`.
