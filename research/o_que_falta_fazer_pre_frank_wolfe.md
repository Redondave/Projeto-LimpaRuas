# O que falta antes do Frank-Wolfe

*Atualizado em 15/10/2026. Escopo: só o que precisa estar pronto **antes** de rodar a alocação. A implementação do Frank-Wolfe, a validação do simulador e os cenários de intervenção ficam para o próximo documento.*

## Onde estamos

| Peça | Arquivo | Situação |
|---|---|---|
| Grafo | `cache/gama_drive_expanded.graphml` (+ `.gpkg`) | ✅ 134 nós, 236 arestas (`scripts/expand_graph.py`) |
| Matriz OD | `Tables/matriz_od_final.json` | ✅ 1.031 pares, 8.309 veíc/h, 18–19h de dia útil (`scripts/build_od_matrix.py`) |
| Bruto da TomTom O/D | `Tables/od_tomtom_gama_final_bruto.json` | ✅ análise "Gama Final", 134 caixas |
| Velocidades no pico e K inicial | `Tables/velocidades_arestas.csv` | ✅ Traffic Stats de julho/2026, 233 de 236 arestas (Etapas 1 e 2) |
| Faixas e limite de velocidade por aresta | `Tables/faixas_limite_arestas.csv` | ✅ falta conferência manual (Etapa 3a) |
| Grafo atribuído (capacidade, `t0`, `v0`, K) | `cache/gama_drive_expanded_atributos.graphml` | ✅ checagens ok; refazer após a conferência manual (Etapas 3b e 4) |
| Vias críticas | — | ❌ Etapa 5 |

## O que o Frank-Wolfe vai receber

Tudo abaixo já existe; o grafo foi conferido pelas checagens da Etapa 4.

1. **Grafo atribuído** (`cache/gama_drive_expanded_atributos.graphml`), com estes campos em **cada aresta**:

   | Campo | Unidade | Origem |
   |---|---|---|
   | `length` | m | OSM (já existe) |
   | `v0_kmh` | km/h | velocidade de madrugada, entre a de pico e o limite (Etapa 6) |
   | `t0_min` | min | `length / v0` |
   | `lanes_sentido`, `fonte_lanes` | faixas | Etapa 3 |
   | `capacidade_veic_h` | veíc/h | Etapa 3 |
   | `permite_carro` | bool | `False` no corredor de ônibus (aresta 23→24) |
   | `vmed_kmh`, `k_inicial` | km/h, — | Etapas 1 e 2. Não entra na alocação; serve para escolher as vias críticas e validar o modelo |

2. **Matriz OD** (`Tables/matriz_od_final.json`): pares `origem` → `destino` (ids do GraphML, como strings) e `veic_h`.
3. **Parâmetros fixados** (Etapa 6): α e β da BPR, fator de expansão e critério de parada.

As unidades precisam bater: demanda e capacidade em veículos por hora, tempo em minutos, TSTT em veíc·min.

---

## Etapas 1 e 2 — Velocidades observadas e K inicial (feito em 15/10)

**Fonte:** TomTom Traffic Stats, *Area Analysis* (job 10086419, "Gama"): julho/2026, dias úteis (2 a 31/07), 18:00–19:00. É **o mesmo período e a mesma janela da matriz OD**. O resultado bruto está em `Tables/traffic_stats_gama_julho.json`: 1.473 trechos da TomTom dentro do polígono, 886 com velocidade, cada um com a geometria no sentido de circulação.

Substitui a coleta em tempo real pela Flow API, que foi removida. O GitHub disparou só 1 dos 24 agendamentos por dia, com atraso de horas, e o histórico nunca recebeu uma rodada válida.

`python scripts/velocidades_traffic_stats.py` → `Tables/velocidades_arestas.csv`.

**Casamento trecho TomTom → aresta:**
- o trecho precisa correr a até 8 m da aresta por pelo menos 5 m;
- e no mesmo sentido (ângulo de até ~45°). Isso separa as duas mãos de uma rua de mão dupla e descarta a pista paralela e as vias transversais. Nas vias de mão única, 212 encaixes saíram no mesmo sentido e 21 no oposto, que eram a pista paralela;
- vias da TomTom fora do grafo não encostam em nenhuma aresta e ficam de fora. Foram usados 431 dos 1.473 trechos.

**Velocidade da aresta:** média harmônica das velocidades harmônicas dos trechos, ponderada pelo comprimento sobreposto, `vmed = Σ Lᵢ / Σ (Lᵢ / vᵢ)`. É a velocidade que reproduz o tempo de percurso somado dos trechos. A tabela também traz a mediana e o percentil 85, ponderados, e a amostra normalizada da TomTom (`amostra_baixa` quando < 0,01).

**K inicial** = `vmed / maxspeed_kmh`, com o limite da Etapa 3a. É o SPI do `research_plan.md`. **Decisão:** no K, o denominador é o **limite da via**, como no plano e no SPI de He et al. (2016). No `t0` da BPR, a velocidade livre é a medida de madrugada (Etapa 6).

**Resultado (236 arestas):**

| Status | Arestas |
|---|---|
| ok (≥ 50% da aresta coberta por trechos com dado) | 233 |
| parcial | 1 (alça de 18 m) |
| sem trecho TomTom | 1 (alça de 18 m) |
| corredor de ônibus | 1 |

| Classe | vmed mediana | K mediano |
|---|---|---|
| trunk (EPCT) | 29 km/h | 0,41 |
| trunk_link | 36 km/h | 0,44 |
| primary (DF-480) | 57 km/h | 0,71 |
| tertiary | 25 km/h | 0,59 |
| unclassified | 27 km/h | 0,90 |

A EPCT trava no pico perto do trevo (K entre 0,29 e 0,40), o que é coerente com os volumes altos do DETRAN. **Há congestionamento**, então a VDF tem onde agir.

**Para a conferência manual da Etapa 3a:**
- **K acima de 1 em 10 arestas,** todas sem nome: terciárias onde a regra do CTB pôs 40 km/h mas o tráfego roda a 40–54 km/h, e unclassified com 30 km/h que rodam a ~31. Provavelmente são vias de categoria mais alta (marginais, por exemplo): conferir e corrigir o limite.
- **Amostra baixa em 14 arestas:** valor menos confiável.

## Etapa 3 — Faixas, limite de velocidade e capacidade

### 3a. Faixas e limite de velocidade (feito em 15/10, falta a conferência manual)

`python scripts/faixas_limite.py` → `Tables/faixas_limite_arestas.csv`, com uma linha por aresta, a fonte de cada valor e dois links do Google Maps (satélite e Street View, este olhando no sentido de circulação).

**Regra adotada, em ordem de prioridade:**

1. **Tag do próprio trecho no OSM** (`lanes`, `maxspeed`).
2. **Mesma via no OSM:** se outros trechos com o mesmo nome e a mesma classe têm a tag e **todos concordam**, o trecho sem tag recebe esse valor. Só a Avenida do Sol se encaixou: 18 trechos sem limite herdaram os 60 km/h e 30 trechos herdaram 1 faixa por sentido.
3. **Regra legal ou de classe:**
   - **Limite de velocidade: art. 61, § 1º, I do CTB (Lei 9.503/1997)**, que define o limite das vias urbanas sem sinalização pela categoria da via. A categoria vem da classe do OSM, pela correspondência usada pelo OSM Brasil na página "Classificação de vias":

     | Classe OSM | Categoria (CTB art. 60) | Limite |
     |---|---|---|
     | motorway, trunk e alças | trânsito rápido | 80 km/h |
     | primary, secondary e alças | arterial | 60 km/h |
     | tertiary, tertiary_link | coletora | 40 km/h |
     | unclassified, residential, living_street | local | 30 km/h |

   - **Faixas por sentido:** o padrão das próprias vias da área que têm a tag: rodovias 2 faixas; terciárias, alças e locais 1 faixa.
4. **Conferência manual** (`Tables/faixas_limite_correcoes.csv`, colunas `edge_id`, `lanes_sentido`, `maxspeed_kmh`, `observacao`): quando existe, tem a palavra final, com fonte "conferencia manual". Basta rodar o script de novo.

**Conversões:**
- **Mão dupla:** `lanes` do OSM conta as duas mãos, então faixas por sentido = `lanes / 2`, arredondado para baixo, com mínimo de 1. Hoje toda via de mão dupla com a tag tem `lanes=2`, então nenhum arredondamento entrou em jogo.
- **Tag em lista** (`['2', '3']`, quando o OSMnx fundiu trechos diferentes): o menor valor, que é o gargalo.
- **Corredor de ônibus** (aresta 23→24): `permite_carro = False`, sem limite.

**Resultado (236 arestas):**

| | OSM | OSM (mesma via) | Regra |
|---|---|---|---|
| Faixas | 113 | 30 | 93 |
| Limite | 71 | 18 | 146 (CTB) |

Limites adotados por classe:

| Classe | Limites adotados |
|---|---|
| trunk | 80 em 8 arestas, 60 em 12 (todas do OSM) |
| primary | 80 em todas (OSM) |
| trunk_link | 80 em todas |
| tertiary | 40 em 119, 60 em 49 |
| tertiary_link | 40 em todas |
| unclassified | 30 em todas |

**Por que não a TomTom:** a Snap to Roads foi testada nas 236 arestas e descartada (ver "Limpeza do repositório", no fim). O limite só bateu com o OSM em 14 de 71 arestas e veio 100 km/h em ruas locais; as faixas vieram em só 6 de 168 terciárias.

**Pontos a conferir no Google Maps** (coluna `conferido` da tabela; corrigir pelo arquivo de correções):
- **Terciárias sem tag (115 a 40 km/h, 70 com 1 faixa):** principalmente Avenida JK, Rua Bolivar 2, Avenida São Francisco e a rua "DF-480 Km 5". A TomTom classifica 167 das 168 terciárias como `LocalStreet`, o que daria 30 km/h. Se a conferência mostrar que são de fato ruas locais, a categoria do CTB muda para local (30 km/h).
- **Alças da EPCT/DF-480 (`trunk_link`, 13 sem tag):** o CTB as põe na categoria da rodovia (80 km/h), mas alças em laço de trevo costumam ter placa de 40 a 60 km/h.
- **Avenidas largas com 1 faixa por regra** (ex.: Avenida JK): checar no satélite se não são 2 por sentido.

**Como isso entra no modelo:** o limite é o denominador do K e o teto da velocidade livre do `t0` (Etapa 6). Por isso a conferência manual pesa direto no modelo. As faixas entram na capacidade (3b).

### 3b. Capacidade (feito em 15/10)

Capacidade por faixa dentro das faixas do `research_plan.md`:

| Classe | veíc/h/faixa |
|---|---|
| trunk (EPCT) | 1.800 |
| trunk_link, primary (DF-480) | 1.200 |
| primary_link, secondary, tertiary | 900 |
| tertiary_link, unclassified | 600 |

`capacidade_veic_h = lanes_sentido × capacidade_por_faixa`, por sentido. Valores resultantes:
- EPCT: 3.600 ou 5.400 veíc/h;
- DF-480: 3.600;
- terciárias: 900 ou 1.800;
- alças: 1.200;
- locais: 600.

**Checagem de sanidade (V/C nas 4 pistas com contador do DETRAN):** 0,60 e 0,42 na EPCT, 0,42 e 0,67 na DF-480. Todas abaixo de 1,2, então nenhuma capacidade está subestimada.

## Etapa 4 — Grafo atribuído (feito em 15/10)

`python scripts/enrich_graph.py` → `cache/gama_drive_expanded_atributos.graphml`, com relatório em `cache/gama_drive_expanded_atributos_relatorio.json` e mapa do K inicial em `cache/gama_drive_expanded_k_inicial.png`.

**Campos de cada aresta:** `length` (m), `limite_kmh`, `fonte_limite`, `v0_kmh`, `fonte_v0`, `v_madrugada_kmh`, `t0_min`, `lanes_sentido`, `fonte_lanes`, `capacidade_por_faixa`, `capacidade_veic_h`, `permite_carro`, `categoria_ctb`, `classe`; e, para validação, `vmed_kmh`, `t_obs_min`, `k_inicial`, `status_velocidade`.

**Atributos do grafo:** `bpr_alpha = 0,15`, `bpr_beta = 4`, a fórmula da VDF, as unidades e a regra de exclusão (`permite_carro = False`).

**Leitura:** `nx.read_graphml` devolve os atributos já tipados (float, int, bool). O `ox.load_graphml` não serve para este arquivo.

**Checagens (todas ok):**
- todas as 235 arestas de carro têm `t0 > 0` e capacidade > 0;
- `v0` entre 10 e 120 km/h;
- os 1.031 pares da matriz têm caminho sem o corredor de ônibus;
- todos os nós da matriz existem no grafo.

**Depois da conferência manual da Etapa 3a:** rodar de novo, em ordem, `faixas_limite.py` → `velocidades_traffic_stats.py` → `enrich_graph.py`.

## Etapa 5 — Vias críticas (diagnóstico, Passo 1 do plano)

**O que fazer:** com o K inicial, listar as arestas com pior desempenho no pico e confirmar que a matriz OD passa por elas.

**Saídas possíveis:**
- **Há vias com K baixo** (ex.: abaixo de 0,7) e com demanda passando: são as candidatas a via crítica. Sai daqui a lista de vias para os cenários.
- **K alto em toda a rede:** a área não congestiona nesse horário. Opções:
  - escolher como críticas as de maior V/C calculado na Etapa 3;
  - rodar a análise com a demanda escalada, usando o fator máximo de 20,8;
  - rever a região de estudo.

  Precisa ser decidido em grupo antes de seguir.

**Saída:** lista de vias críticas e das intervenções candidatas (faixa extra, mudança de sentido, fechamento para testar Braess), com a justificativa de cada uma.

## Etapa 6 — Parâmetros a fixar (pode ser feito já)

| Parâmetro | Proposta | Sensibilidade |
|---|---|---|
| BPR α, β | 0,15 e 4 (BPR, 1964) | 0,8 e 4,7 (arteriais urbanas, Bagdá) |
| Fator de expansão da OD | 12,21 (mediana de 4 pistas DETRAN) | 8,18 e 20,81 (demanda × 0,67 e × 1,70) |
| Parada | gap relativo < 10⁻⁴ ou 500 iterações | — |
| Pares OD com poucas viagens | manter todos (são 9% da demanda) | rodar sem os pares com menos de 5 viagens |

**Velocidade livre `v0` (decidido em 15/10): velocidade medida de madrugada.**

*Problema.* Com `v0` igual ao limite, o tempo no pico dava, na mediana, 1,67 vez o `t0`. Com V/C entre 0,42 e 0,67, a BPR padrão só produz 1 a 3% de aumento. A maior parte desse "atraso" não era congestionamento: eram curva, trevo, conversão e semáforo, que existem também com a via vazia.

*Solução.* TomTom Traffic Stats, job 10086478: mesmo polígono, dias úteis de julho/2026, das 00:00 às 04:00. O bruto está em `Tables/traffic_stats_gama_madrugada.json`, com a mesma regra de casamento das Etapas 1 e 2.

*Regra:* `v0 = min(limite, max(v_madrugada, v_pico))`.
- **Nunca abaixo da velocidade de pico.** De madrugada passam poucos carros. Em 52 arestas com amostra baixa (terciárias e locais), a média saiu mais lenta que no pico: ônibus, caminhão de lixo, carro estacionando.
- **Nunca acima do limite.** Excesso de velocidade não serve de referência.
- **Sem dado de madrugada:** o limite.

| Fonte do `v0` | Arestas |
|---|---|
| madrugada | 142 |
| pico (madrugada mais lenta) | 76 |
| limite (madrugada acima dele) | 16 |
| limite (sem dado de madrugada) | 1 |

O K continua `vmed / limite`, como no `research_plan.md`. A madrugada entra só no `t0`.

*Resultado.* O `t0` total da rede passou de 36,3 para 55,7 min. O tempo de pico sobre o `t0` caiu de 1,67 para **1,04** na mediana; na rede toda, de 1,72 para **1,12**.

| Classe | Mediana de `t_obs/t0` |
|---|---|
| terciárias | 1,03 |
| locais | 1,00 |
| alças | 1,08 |
| DF-480 | 1,22 |
| EPCT | 1,36 |

*O que ainda sobra.* Fora do corredor, o modelo-base já fica próximo do observado. Na EPCT e na DF-480 sobram 20 a 36% de atraso. Com V/C de 0,6, a BPR só reproduziria isso com α ≈ 2,8, um valor fora de qualquer referência. É fila no trevo (atraso de nó e entrelaçamento), que a BPR por aresta não representa.

Opções para esse resíduo:
- **(a)** reduzir a capacidade das arestas de gargalo do trevo;
- **(b)** declarar a limitação e analisar os cenários pela variação relativa (ΔTSTT, ΔK).

**α e β:** referência 0,15 e 4, a BPR original e a mais citada; não há valor nacional padronizado. Sensibilidade com 0,8 e 4,7. Com V/C ≤ 0,67, o β quase não pesa; ele importa nos cenários que levem vias para perto da capacidade.

O grafo traz `t_obs_min` e `v_madrugada_kmh` em cada aresta para essa comparação.

**Opcional:** recalibrar o fator com as contagens do DETRAN de **julho/2026**, o mesmo mês da matriz, baixadas do portal de dados abertos do DF. Basta substituir o `flow.csv` e rodar `python scripts/build_od_matrix.py --offline`.

## Etapa 7 — Dados para validação (pode ser feito já)

Não é rodar a validação; é deixar os dados à mão.
- **Sioux Falls**, para validar o código do Frank-Wolfe: baixar `SiouxFalls_net.tntp`, `SiouxFalls_trips.tntp` e `SiouxFalls_flow.tntp` do repositório público *TransportationNetworks*.
- **Gama**, para validar o modelo:
  - `regioes[].passagens_veic_h` na matriz: fluxo observado em cada caixa (126 caixas com 100 ou mais passagens);
  - `fator_expansao.observacoes`: as 4 pistas com contagem do DETRAN.

---

## Ordem e dependências

```
Feito:                   Etapas 1 e 2 (velocidades e K) · 3a (faixas e limite, sem a conferência) · 3b (capacidade) · 4 (grafo atribuído)
Agora (em paralelo):     Etapa 3a (conferência manual) · Etapa 6 (parâmetros e a decisão sobre a calibração) · Etapa 7 (dados de validação)
Depois da conferência:   faixas_limite.py → velocidades_traffic_stats.py → enrich_graph.py → Etapa 5 (vias críticas)
Então:                   Frank-Wolfe
```

## Pendências opcionais (não bloqueiam)

| Item | Ganho |
|---|---|
| Caixas TomTom nos nós 32 e 41, e as duas ligações até o nó 127 (ficaram fora do recorte) | Recupera 1,6% da demanda descartada e evita arestas vazias no modelo |
| Ponto de calibração na EPIP | Hoje nenhuma caixa da EPIP passa no critério; o recorte só pega a EPIP dentro do trevo |
| Contagens do DETRAN de julho/2026 | Calibração sem defasagem de meses (Etapa 6) |

## Limpeza do repositório (feita em 15/10/2026)

Removidos (continuam no histórico do git, se precisar recuperar):
- K antigo: `scripts/organizer.py`, `Tables/K_Table.csv`, `Tables/tomtom_flow_consolidado.csv`, `Tables/Speeds.csv`;
- análise O/D "Gama 3": `Tables/matriz_od_gama3.json`, `Tables/matriz_od_gama3_expandido.json`, `Tables/od_tomtom_gama3_bruto.json`;
- grafos e coletas antigas: `cache/gama_drive_reduced_tomtom.gpkg`, `cache/tomtom_flow_results.jsonl`, `cache/gama_drive_sample_30.gpkg`, `cache/gama_drive_sample_30_selection.json`, `cache/gama_drive_sample_30_tomtom.gpkg`;
- grafo da RA inteira, cortado na divisa: `scripts/osmnx-api.py`, `cache/gama_drive_projected.*`, `cache/limite_gama.geojson`;
- utilitários quebrados: `scripts/graphml_to_geopackage.py`, `scripts/graph_visual_check.py`, `graph_visualization.png`;
- `scripts/__pycache__/`, agora no `.gitignore`;
- `cache/gama_drive_expanded_tomtom.gpkg` saiu do git (é regerado a cada rodada) e foi para o `.gitignore`.

Mantido de propósito: `cache/gama_drive_sample_30.graphml`, porque o `expand_graph.py` usa esse grafo para preservar os ids `0`–`29`.

O `README.md` foi reescrito para o fluxo atual.

**Teste descartado:** a TomTom Snap to Roads API foi testada em 15/10 nas 236 arestas, como fonte de faixas e limite de velocidade:
- o limite só bateu com o OSM em 14 de 71 arestas comparáveis, e veio 100 km/h em 31 ruas locais;
- as faixas vieram em só 6 de 168 terciárias.

Por isso, a Etapa 3 segue com o OSM mais regras: limite pelo art. 61 do CTB (80 km/h em via de trânsito rápido, 60 em arterial, 40 em coletora, 30 em local) e faixas por classe de via. O script e os dados do teste foram removidos.

**Coleta de velocidades em tempo real removida (15/10/2026):** `scripts/api_caller.py`, `.github/workflows/traffic.yml` e `cache/tomtom_flow_history.jsonl` (vazio: nenhuma rodada válida), substituídos pelo Traffic Stats (Etapas 1 e 2). O secret `TOMTOM_API_KEY` continua no repositório, mas nenhum workflow o usa mais.
