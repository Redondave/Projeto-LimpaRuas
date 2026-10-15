# O que falta antes do Frank-Wolfe

*Atualizado em 14/10/2026. Escopo: só o que precisa estar pronto **antes** de rodar a alocação. A implementação do Frank-Wolfe, a validação do simulador e os cenários de intervenção ficam para o próximo documento. Nada daqui foi executado ainda.*

## Onde estamos

| Peça | Arquivo | Situação |
|---|---|---|
| Grafo | `cache/gama_drive_expanded.graphml` (+ `.gpkg`) | ✅ 134 nós, 236 arestas (`scripts/expand_graph.py`) |
| Matriz OD | `Tables/matriz_od_final.json` | ✅ 1.031 pares, 8.309 veíc/h, 18–19h de dia útil (`scripts/build_od_matrix.py`) |
| Bruto da TomTom O/D | `Tables/od_tomtom_gama_final_bruto.json` | ✅ análise "Gama Final", 134 caixas |
| Velocidades no pico | `cache/tomtom_flow_history.jsonl` | ⏳ coleta rodando de 14 a 20/10 (Etapa 1) |
| Velocidade livre, faixas, capacidade e `t0` por aresta | — | ❌ Etapas 2 a 4 |
| K inicial e vias críticas | — | ❌ Etapa 5 |

## O que o Frank-Wolfe vai receber

É a meta deste documento: tudo abaixo existe e foi conferido.

1. **Grafo atribuído** (`cache/gama_drive_expanded_atributos.graphml`), com estes campos em **cada aresta**:

   | Campo | Unidade | Origem |
   |---|---|---|
   | `length` | m | OSM (já existe) |
   | `v0_kmh`, `fonte_v0` | km/h | Etapa 2 |
   | `t0_min` | min | `length / v0` |
   | `lanes_sentido`, `fonte_lanes` | faixas | Etapa 3 |
   | `capacidade_veic_h` | veíc/h | Etapa 3 |
   | `permite_carro` | bool | `False` no corredor de ônibus (aresta 23→24) |
   | `vmed_kmh`, `k_inicial`, `n_leituras` | km/h, —, — | Etapa 2. Não entra na alocação; serve para escolher as vias críticas e validar o modelo |

2. **Matriz OD** (`Tables/matriz_od_final.json`): pares `origem` → `destino` (ids do GraphML, como strings) e `veic_h`.
3. **Parâmetros fixados** (Etapa 6): α e β da BPR, fator de expansão e critério de parada.

As unidades precisam bater: demanda e capacidade em veículos por hora, tempo em minutos, TSTT em veíc·min.

---

## Etapa 1 — Acompanhar a coleta de velocidades (em andamento)

**O que está rodando:** o workflow do GitHub coleta a cada ~7 min, das 18:00 às 19:00 de dia útil, até reunir 5 dias com 3 ou mais rodadas cada (previsão: 14, 15, 16, 19 e 20/10). Cada rodada faz 156 consultas à Flow API da TomTom, com zoom 18, e grava uma linha por aresta.

**O que fazer:**
- Depois da primeira rodada, abrir o log no Actions e ler *"segmento a mais de 20 m da aresta: N"*.
- A cada dia, conferir com `git pull` se o histórico cresceu. São 236 linhas por rodada; o esperado é de 3 a 8 rodadas por dia.

**Saídas possíveis:**

| Situação | O que fazer |
|---|---|
| N baixo (até ~20 de 236) | Seguir; as leituras ruins são descartadas na Etapa 2 |
| N alto, sobretudo nas terciárias | O zoom 18 não resolveu. Testar `TOMTOM_ZOOM=22` e `14` com `python scripts/api_caller.py --forcar` (grava em arquivo de teste), escolher o melhor, apagar o conteúdo do histórico e recomeçar a coleta |
| A TomTom não tem dado próprio para as ruas locais (segmento é sempre de outra via, em qualquer zoom) | Usar a TomTom só nas rodovias e alças; nas ruas locais, `V0` e capacidade por classe (Etapas 2 e 3). Declarar como limitação |
| O GitHub perde o horário vários dias seguidos | Rodar o mesmo script pelo Agendador de Tarefas do Windows, a cada 5 min entre 17:55 e 19:00. O próprio script decide se a rodada vale. Lembrar de dar `git push` no histórico |
| Erro 403 ou 429 no log | A chave do secret não tem a Flow API ou estourou a cota: trocar o secret `TOMTOM_API_KEY` |
| A conta tem acesso ao TomTom Traffic Stats | Alternativa melhor: uma *Area Analysis* de julho/2026, 18–19h, dias úteis, dá velocidades no mesmo período da matriz OD. Substitui as Etapas 1 e 2 |

**Saída:** `cache/tomtom_flow_history.jsonl` com 5 dias completos.

## Etapa 2 — Velocidades por aresta (depois de 20/10)

**O que fazer** (script a criar, sugestão: `scripts/aggregate_speeds.py`):

1. **Filtrar leituras:**
   - `success` verdadeiro, `roadClosure` falso;
   - `snap_dist_m ≤ 20`: o segmento devolvido é desta aresta;
   - `confidence ≥ 0,7`: leitura baseada em dado real, não em histórico da TomTom;
   - **sentido:** em rua de mão dupla, as duas mãos são consultadas no mesmo ponto e recebem o mesmo segmento. Usar a leitura na aresta em que `snap_cos > 0` e decidir a outra mão: copiar o valor ou tratar como sem dado.
2. **Agregar por aresta:** `vmed_kmh` = mediana de `currentSpeed`; `v0_kmh` = mediana de `freeFlowSpeed`; `n_leituras`; e a dispersão (intervalo interquartil) para relatar a incerteza.
3. **Preencher a velocidade livre de quem ficou sem leitura válida**, nesta ordem: `freeFlowSpeed` da TomTom → `maxspeed` do OSM (71 de 236 arestas) → valor por classe. Registrar a fonte em `fonte_v0`.
4. **`k_inicial = vmed / v0`**, só nas arestas com leitura própria.

**Saídas possíveis:**
- **Maioria das arestas com leitura válida:** o K inicial cobre a rede, e a velocidade livre vem de dado medido.
- **Só rodovias e alças com leitura** (provável, se as terciárias não tiverem dado da TomTom): o K inicial fica restrito às vias principais, o que basta para escolher a via crítica; a velocidade livre das ruas locais vem por classe.
- **`vmed` igual a `v0` em quase tudo:** não há congestionamento no pico nesta área. Isso precisa ser discutido antes dos cenários, porque sem congestionamento a VDF não age.

**Saída:** `Tables/velocidades_arestas.csv` (uma linha por aresta, com fonte e número de leituras).

## Etapa 3 — Faixas e capacidade (pode começar já)

Cobertura no OSM:

| Classe | Arestas | Com `lanes` | Com `maxspeed` |
|---|---|---|---|
| trunk | 20 | 20 | 20 |
| primary | 12 | 12 | 12 |
| trunk_link | 17 | 13 | 4 |
| tertiary | 168 | 68 | 35 |
| tertiary_link | 4 | 0 | 0 |
| unclassified | 14 | 0 | 0 |
| busway | 1 | — | — |
| **Total** | **236** | **113 (48%)** | **71 (30%)** |

**O que fazer:**

1. **Faixas por sentido:**
   - em via de mão dupla, `lanes` do OSM conta as duas mãos: dividir por 2;
   - valores em lista (`['2', '3']`, quando o OSMnx funde vias): usar o mínimo, que é o gargalo;
   - registrar a fonte em `fonte_lanes`.
2. **Faltantes (123 arestas).** Opções:
   - **(a) Regra por classe:** ex.: terciária e alças = 1 faixa por sentido; unclassified = 1. Rápido e reprodutível; impreciso nas terciárias largas, como a Avenida JK.
   - **(b) Conferência por imagem de satélite**, só nas terciárias que carregam muita demanda: as que aparecem nos maiores pares da matriz ou que têm muitas passagens nas caixas. Mais preciso; uma tarde de trabalho.
   - **(c) Híbrido:** (a) para todas e (b) para as ~20 mais carregadas. **Sugerido.**
3. **Capacidade por faixa**, com os valores do `research_plan.md`. Proposta para fixar:

   | Classe | veíc/h/faixa |
   |---|---|
   | trunk | 1.800 |
   | trunk_link, primary | 1.200 |
   | primary_link, tertiary | 900 |
   | tertiary_link, unclassified | 600 |

   `capacidade_veic_h = lanes_sentido × capacidade_por_faixa`.

4. **Corredor de ônibus:** `permite_carro = False` na aresta 23→24.
5. **Checagem de sanidade:** comparar a capacidade das 4 pistas com contador do DETRAN com o volume medido no pico. A razão V/C deve ficar abaixo de ~1,2. Se passar disso, as faixas ou a capacidade por faixa estão subestimadas (foi o que aconteceu no grafo rodoviário antigo).

**Saídas possíveis:** regra pura (a), entregável hoje, ou híbrido (c), mais defensável no artigo. Em ambos os casos, a cobertura vira uma limitação quantificada, como o `research_plan.md` pede.

**Saída:** colunas `lanes_sentido`, `fonte_lanes` e `capacidade_veic_h`.

## Etapa 4 — Montar o grafo atribuído (depois das Etapas 2 e 3)

**O que fazer** (sugestão: `scripts/enrich_graph.py`):
1. Juntar os resultados das Etapas 2 e 3 no grafo e calcular `t0_min = length / v0`.
2. **Checagens antes de liberar para o Frank-Wolfe:**
   - toda aresta com `permite_carro` tem `t0 > 0` e capacidade > 0;
   - os 1.031 pares da matriz continuam com caminho no grafo sem o corredor de ônibus;
   - nenhuma aresta com `t0` absurdo: velocidade livre abaixo de 10 ou acima de 120 km/h;
   - ids e unidades conferidos.
3. Gerar uma figura com a velocidade livre e o K inicial por aresta, para conferência visual.

**Saída:** `cache/gama_drive_expanded_atributos.graphml` + um relatório de cobertura (quantas arestas têm cada atributo medido e quantas imputado).

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
Agora (em paralelo):     Etapa 3 (faixas/capacidade) · Etapa 6 (parâmetros) · Etapa 7 (dados de validação)
Até 20/10:               Etapa 1 (coleta rodando sozinha; só acompanhar)
Depois de 20/10:         Etapa 2 (velocidades) → Etapa 4 (grafo atribuído) → Etapa 5 (vias críticas)
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
