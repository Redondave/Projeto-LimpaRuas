# O que falta antes do Frank-Wolfe

*Atualizado em 14/10/2026, depois da matriz OD final. Este documento descreve os passos; nenhum deles foi executado ainda.*

## Onde estamos

| Peça | Arquivo | Situação |
|---|---|---|
| Grafo | `cache/gama_drive_expanded.graphml` (+ `.gpkg`) | ✅ 134 nós, 236 arestas, gerado por `scripts/expand_graph.py` |
| Matriz OD | `Tables/matriz_od_final.json` | ✅ 1.031 pares, 8.309 veíc/h, pico 18–19h de dia útil |
| Bruto da TomTom | `Tables/od_tomtom_gama_final_bruto.json` | ✅ análise "Gama Final" (id 6604531297533426895), 134 caixas |
| Atributos de aresta para a VDF (`t0`, capacidade) | — | ❌ não calculados (Etapa 1) |
| Velocidade observada no pico (`Vmed`, K inicial) | — | ❌ não coletada para o grafo novo (Etapa 2) |
| Implementação do Frank-Wolfe | — | ❌ não existe (Etapa 3) |

### Como a matriz final foi feita

`python scripts/build_od_matrix.py` (o padrão já aponta para a análise "Gama Final" e o grafo expandido).

- **Amostra:** 15.429 viagens TomTom em 22 dias úteis de julho/2026, 18–19h. 86% são de passagem pelo recorte.
- **Caixa → nó:** 129 das 134 caixas contêm um nó. 4 caem sobre via de mão dupla (vai para a ponta mais próxima) e 1 sobre aresta de mão única (vai para o nó seguinte).
- **Nós sem caixa:** 24 (só alcançável pelo corredor de ônibus, irrelevante), 32, 41 e 129. Quem entra por eles aparece no nó vizinho com caixa; as arestas até eles ficam vazias no modelo.
- **Descartes:** 229 viagens que entram e saem pelo mesmo nó e 240 sem caminho no grafo (1,6%). Destas, 146 terminam no nó 127, que só é alcançável por duas ligações de 15 e 112 m que ficaram fora do recorte.
- **Fator de expansão: 12,21**, a mediana de 4 pistas com contador do DETRAN, encontradas automaticamente em 25 caixas que cobrem só uma pista de rodovia:

  | Pista | DETRAN (veíc/h) | TomTom (viagens/h) | Fator |
  |---|---|---|---|
  | EPCT (001EDF0270) crescente | 1.508 | 184 | 8,18 |
  | DF-480 (480EDF0030) crescente | 1.505 | 141 | 10,68 |
  | DF-480 (480EDF0030) decrescente | 2.424 | 176 | 13,75 |
  | EPCT (001EDF0250) decrescente | 2.146 | 103 | 20,81 |

  A análise "Gama 3", com outras caixas, deu 11,6 pelo mesmo princípio. A faixa 8,2–20,8 deve entrar na análise de sensibilidade. A EPIP ficou sem ponto de calibração: o recorte só pega a EPIP dentro do trevo.
- **Robustez:** 91% da demanda está em pares com 5 ou mais viagens na amostra. Os 830 pares com 1–4 viagens são ruído de amostragem, mas pesam só 9%.

> **Atenção ao CSV exportado do portal:** há nomes de região repetidos ("Rodovia EPCT (18)" ×2, "Rua Dois Ponte Alta Norte (12)" ×3), então o CSV é ambíguo. O script usa os índices da API, não os nomes.

---

## O que falta, em ordem

### Etapa 1 — Atributos das arestas (bloqueante)

A VDF de cada aresta precisa de `t0` (tempo em fluxo livre) e `c` (capacidade em veíc/h). Cobertura atual no OSM:

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

O que fazer (sugestão: um `scripts/enrich_graph.py` que grava `cache/gama_drive_expanded_atributos.graphml`):

1. **Faixas:** usar `lanes` do OSM; quando faltar, regra por classe (ex.: terciária e alças = 1 por sentido). `lanes` do OSM conta as duas mãos em via de mão dupla: dividir por 2. Atributos com lista (`['2', '3']`) aparecem quando o OSMnx funde vias: usar o mínimo, que é o gargalo.
2. **Velocidade livre `V0`:** prioridade `freeFlowSpeed` da TomTom (Etapa 2) → `maxspeed` do OSM → valor por classe.
3. **Capacidade:** `c = faixas × capacidade por faixa` com os valores do `research_plan.md` (expressa ~1.800–2.000, arterial ~1.000–1.200, local ~500–900 veíc/h/faixa).
4. **`t0 = length / V0`**, em segundos ou minutos, mantendo a mesma unidade do TSTT.
5. **Corredor de ônibus:** marcar `highway == "busway"` (aresta 23→24) como proibido para carro. A matriz já ignora essa aresta no teste de caminho.
6. **Registrar a cobertura** (a tabela acima, por atributo imputado). O `research_plan.md` pede que essa dependência seja relatada como limitação quantificada.

### Etapa 2 — Velocidades observadas (dado que falta coletar)

Situação atual: o `cache/tomtom_flow_history.jsonl` tem 37 registros, todos do grafo antigo de 30 nós, coletados à meia-noite de 13/10. A velocidade atual é igual à livre em 100% deles, então não servem para `Vmed`. O workflow está agendado para 18–19h, mas o GitHub rodou à meia-noite: agendamento do GitHub Actions não garante horário.

Duas opções:

- **A (recomendada, se a conta tiver acesso): TomTom Traffic Stats**, no mesmo portal Move. Uma *Area Analysis* sobre o recorte, de julho/2026, dias úteis, 18–19h, devolve velocidade média e de referência por segmento. É o **mesmo período e a mesma janela da matriz OD**, sem semanas de coleta.
- **B: coleta com a Flow API no grafo expandido.**
  - Trocar `INPUT_GEOPACKAGE`/`OUTPUT_GEOPACKAGE` do `api_caller.py` para `cache/gama_drive_expanded*.gpkg` e o `git add` do workflow para o arquivo novo.
  - Cada rodada faz 236 requisições. A cota gratuita (~2.500/dia; confirmar no painel) permite até 10 rodadas por dia; as 8 do workflow cabem.
  - Rodar localmente (Agendador de Tarefas do Windows) ou aceitar o atraso do GitHub e filtrar por horário depois.
  - Mínimo de 5 dias úteis; usar a mediana por aresta.
  - Limitação a declarar: velocidades de outubro com demanda de julho.

Com `Vmed` e `V0`: **K inicial = Vmed / V0** por aresta, o mapa das vias críticas (Passo 1 do plano).

### Etapa 3 — Implementar e validar o Frank-Wolfe

1. **Entrada:** grafo atribuído + `Tables/matriz_od_final.json` (campos `pares[].origem`, `pares[].destino`, `pares[].veic_h`; os ids são as strings do GraphML).
2. **Algoritmo:** alocação tudo-ou-nada inicial → direção pelo caminho mínimo com custos BPR → busca linear do passo → repetir até gap relativo < 1e-4. BPR com a = 0,15, b = 4 como padrão e a = 0,8, b = 4,7 como sensibilidade.
3. **Saídas:** fluxo `x`, tempo `t` e `K = (L/t)/V0` por aresta, e TSTT.
4. **Validação do código:** rede de Sioux Falls, que tem equilíbrio publicado (**dado a baixar**: arquivos `SiouxFalls_net.tntp`, `SiouxFalls_trips.tntp` e `SiouxFalls_flow.tntp` do repositório público *TransportationNetworks*).
5. **Validação do modelo no Gama:**
   - `regioes[].passagens_veic_h` da matriz: fluxo observado por caixa, comparável ao fluxo modelado no nó correspondente (126 caixas com 100 ou mais passagens);
   - as 4 pistas do DETRAN da calibração;
   - estatística GEH.
6. **Sensibilidade:** rodar com o fator de expansão em 8,2 e em 20,8 (demanda × 0,67 e × 1,70).

### Etapa 4 — Cenários (Passos 5 e 6 do `research_plan.md`)

Escolher as vias críticas pelo K inicial e testar intervenções (faixa extra, sentido, fechamento para testar Braess) em cópias do grafo. A rede agora tem escolha de rota para cerca de 40% da demanda (medido com a matriz anterior), o que dá espaço para redistribuição.

---

## Dados que ainda faltam coletar

| Dado | Necessário para | Prioridade |
|---|---|---|
| Velocidade por aresta no pico (Traffic Stats ou Flow API) | `V0`, `Vmed`, K inicial | **Bloqueante** |
| Faixas das 123 arestas sem `lanes` (ao menos as terciárias principais, por imagem de satélite) | capacidade | Alta (pode começar por regra) |
| Arquivos de Sioux Falls | validar o código | Alta |
| Contagens do DETRAN de julho/2026 (portal de dados abertos do DF), mês da matriz | recalibrar o fator sem defasagem; basta trocar o `flow.csv` e rodar `build_od_matrix.py --offline` | Média |
| Caixas TomTom nos nós 32 e 41 e as duas ligações até o nó 127 | recuperar 1,6% da demanda e arestas vazias | Baixa |

---

## Arquivos que não serão mais usados

Nada foi apagado. Sugestão de ação para cada um:

| Arquivo | Por quê | Sugestão |
|---|---|---|
| `scripts/organizer.py`, `Tables/K_Table.csv`, `Tables/tomtom_flow_consolidado.csv` | K antigo: limite de outra rodovia e coleta do feriado (já apontado no `research_plan.md`) | Apagar |
| `Tables/matriz_od_gama3.json`, `Tables/matriz_od_gama3_expandido.json`, `Tables/od_tomtom_gama3_bruto.json` | Análise "Gama 3" (30 caixas), substituída pela "Gama Final" | Apagar (o histórico fica no git) |
| `cache/gama_drive_reduced_tomtom.gpkg`, `cache/tomtom_flow_results.jsonl` | Grafo de 86 arestas anterior ao de 30 nós e checkpoint do coletor antigo | Apagar |
| `scripts/graphml_to_geopackage.py` | Aponta para `gama_drive_reduced.graphml`, que não existe mais; o `expand_graph.py` já gera o `.gpkg` | Apagar |
| `scripts/graph_visual_check.py` | Caminho fixo de outra máquina; o `expand_graph.py` já gera a figura | Apagar |
| `scripts/osmnx-api.py`, `cache/gama_drive_projected.*`, `cache/limite_gama.geojson` | Grafo da RA inteira, cortado na divisa (sem a pista norte da EPCT). Substituído por `cache/gama_area_estudo_osm.graphml` | Apagar junto com a linha `GRAFO_COMPLETO` do `build_od_matrix.py`, que é só um fallback |
| `cache/gama_drive_sample_30.*`, `cache/gama_drive_sample_30_selection.json`, `cache/gama_drive_sample_30_tomtom.gpkg` | Grafo de 30 nós | Manter até trocar o coletor (Etapa 2B), depois apagar |
| `Tables/Speeds.csv` | Limites de radar; o plano prioriza `maxspeed` do OSM | Manter só se for usado como fallback de `V0` nas rodovias |
| `README.md`, seção "TomTom flow" | Cita `api-caller.py`, `gama_drive_reduced` e `tomtom_flow_results.jsonl`, que não existem ou mudaram | Reescrever |
| `scripts/__pycache__/` | Bytecode do Python commitado por engano | Apagar e adicionar `__pycache__/` ao `.gitignore` |

**Continuam necessários:** `flow.csv` (calibração), `Tables/trechos_com_coordenadas.csv` e `Tables/Roads.csv` (localização dos contadores), `scripts/mapping.py` (só se a tabela do DER mudar), `scripts/api_caller.py`, `scripts/expand_graph.py`, `scripts/build_od_matrix.py` e o workflow.

O `research/o_que_tem_que_fazer_pra_mudar_o_grafo.md` está cumprido e fica como registro histórico.
