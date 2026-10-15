# Projeto LimpaRuas

Otimização do índice de desempenho de velocidade (K) na malha viária do Gama (DF):
grafo da região, matriz origem-destino e coleta de velocidades para a alocação de
tráfego por Frank-Wolfe. Plano completo em `research/research_plan.md`; próximos
passos em `research/o_que_falta_fazer_pre_frank_wolfe.md`.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `cache/gama_drive_expanded.graphml` / `.gpkg` | Grafo de estudo: 134 nós, 236 arestas |
| `cache/gama_area_estudo_osm.graphml` | Download do OpenStreetMap da área (fonte do grafo) |
| `cache/gama_drive_sample_30.graphml` | Grafo de 30 nós original: base dos ids `0`–`29` do grafo de estudo |
| `cache/gama_drive_expanded_portoes.geojson` | Caixas usadas na análise O/D da TomTom |
| `cache/tomtom_flow_history.jsonl` | Velocidades no pico (18–19h), uma linha por aresta por rodada |
| `Tables/matriz_od_final.json` | Matriz OD nó a nó em veíc/h, com calibração e dados de validação |
| `Tables/od_tomtom_gama_final_bruto.json` | Resposta da TomTom O/D Analysis ("Gama Final") |
| `Tables/Roads.csv`, `Tables/trechos_com_coordenadas.csv` | Trechos do DER-DF e sua geometria (localizam os contadores) |

## Scripts

```bash
python scripts/expand_graph.py          # refaz o grafo de estudo (offline, a partir do cache)
python scripts/build_od_matrix.py       # refaz a matriz OD (--offline usa o bruto salvo)
python scripts/api_caller.py            # uma rodada de velocidades, se estiver na janela de pico
python scripts/mapping.py               # só se a tabela de trechos do DER mudar
```

Os scripts que chamam a TomTom leem a chave da variável `TOMTOM_API_KEY`.

## Coleta automática de velocidades

O workflow `.github/workflows/traffic.yml` dispara a cada 5 min entre 17:00 e 18:55
de Brasília. O `api_caller.py` só coleta em dia útil, entre 18:00 e 19:00, até 8
rodadas por dia, e para sozinho depois de 5 dias úteis com 3 ou mais rodadas.
A chave vem do secret `TOMTOM_API_KEY` do repositório.

## Dados do DETRAN

As contagens de tráfego calibram a matriz OD. O arquivo tem 134 MB e não fica no git:

1. Baixar um dos CSVs de [volume diário de tráfego do DETRAN](https://www.dados.df.gov.br/pt/dataset#/volume-diario-de-trafego-trechos-rodoviarios).
2. Salvar na raiz do repositório como `flow.csv`.
