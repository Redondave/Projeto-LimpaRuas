# Viabilidade de Mudança de Região de Estudo

## Status (13/10/2026): grafo expandido em volta do trevo EPCT / EPIP / DF-480

Feito pelo `scripts/expand_graph.py` (reproduzível, ~10 s; só baixa do OSM na primeira vez).

| Item da tabela abaixo | Situação |
|---|---|
| 1. Polígono da região | Envoltória dos 30 nós atuais + 200 m (`--buffer`). Não depende mais do `limite_gama.geojson` |
| 2. Grafo OSMnx | Download só da área de estudo → `cache/gama_area_estudo_osm.graphml`. O `gama_drive_projected` não serve: foi recortado pelo limite da RA, e a EPCT corre a 2–12 m da divisa, então a pista sentido norte e a EPIP depois do trevo ficavam de fora |
| 3. Redução do grafo | Agora tem script e critério: vias terciárias para cima dentro do polígono, sem becos internos → `cache/gama_drive_expanded.graphml` (134 nós, 236 arestas) |
| 4. GeoPackage | `cache/gama_drive_expanded.gpkg`, mesmo esquema do `gama_drive_sample_30.gpkg` |
| 5. Coleta TomTom Flow | **Pendente.** Para coletar no grafo novo: trocar `INPUT_GEOPACKAGE`/`OUTPUT_GEOPACKAGE` no `api_caller.py` e o `git add` do workflow |
| 7. Análise O/D TomTom | **Pendente.** Caixas sugeridas em `cache/gama_drive_expanded_portoes.geojson` (24 portões principais, 66 acessos locais), cada uma com o nome `no <id>` |
| 8. Mapeamento zona → nó | Automático no `build_od_matrix.py --grafo cache/gama_drive_expanded.graphml` |

**Compatibilidade:** os 30 nós mantêm os ids `0`–`29` e as 37 arestas mantêm `u`, `v` e `id` (o script confere). A matriz `Tables/matriz_od_gama3.json`, o histórico `cache/tomtom_flow_history.jsonl` e o workflow continuam valendo. Os arquivos do grafo de 30 nós não foram alterados.

**Escolha de rota** (critério: rotas até 30% mais longas, com menos de 60% de arestas em comum, ponderado pela matriz OD atual): 0% da demanda no grafo de 30 nós → 40% no expandido. Com a pista oposta e as alças, os 34 pares que não tinham caminho passam a ter (100% da demanda alocável). Os 60% restantes são tráfego de passagem pelas rodovias, que não tem alternativa nem no mapa real.

**Atenção:** a aresta 23→24 (já no grafo de 30 nós) é `busway`, corredor de ônibus. Excluir `highway == "busway"` da alocação de carros.

## Veredicto Rápido

**É viável em poucas horas de trabalho técnico**, mas tem um **gargalo calendário** importante: a coleta TomTom Flow precisa ser repetida em 3–5 dias úteis diferentes no horário de pico. Isso não é difícil, é só demorado no calendário (uma semana de rodar o script 1x/dia).

---

## Inventário: O que é reutilizável vs. o que precisa ser refeito

### ✅ Reutilizável sem alteração (independente de região)

| Artefato | Por quê |
|----------|---------|
| [Roads.csv](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/Tables/Roads.csv) | Cobertura DF inteiro — serve para qualquer região |
| [Speeds.csv](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/Tables/Speeds.csv) | Idem — radares de todo o DF |
| [Flow.csv](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/Flow.csv) (134 MB) | Idem — fluxo de todos os trechos do DF |
| [mapping.py](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/scripts/mapping.py) | Script genérico, funciona para qualquer trecho DER |
| [graphml_to_geopackage.py](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/scripts/graphml_to_geopackage.py) | Conversor genérico |
| [api_caller.py](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/scripts/api_caller.py) | Funciona para qualquer GeoPackage de entrada |
| [build_od_matrix.py](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/scripts/build_od_matrix.py) | Estrutura genérica (o `ZONE_TO_NODES` já está vazio mesmo) |
| research_plan.md, articles.md | Metodologia e referências — independentes de região |

### 🔄 Precisa ser refeito (região-dependente)

| # | Artefato / Tarefa | Esforço | Detalhe |
|---|-------------------|---------|---------|
| 1 | **Polígono da região** (`limite_gama.geojson`) | ~15 min | Baixar novo GeoJSON do Geoportal DF ou desenhar no QGIS/geojson.io. Trocar path no `osmnx-api.py` |
| 2 | **Grafo completo OSMnx** (`gama_drive_projected.*`) | ~5 min | Rodar `osmnx-api.py` com novo polígono. Download do OSM é rápido para áreas pequenas |
| 3 | **Redução do grafo** (`gama_drive_reduced.*`) | ~30 min | **Não há script de redução no repositório** — o grafo reduzido foi gerado por seleção manual/ad-hoc ("30-node dense induced subgraph selected for metadata completeness"). Precisaria definir critérios e selecionar o subgrafo novamente. Pode ser scriptado desta vez |
| 4 | **GeoPackage reduzido** (`gama_drive_reduced.gpkg`) | ~2 min | Rodar `graphml_to_geopackage.py` sobre o novo grafo reduzido |
| 5 | **Coleta TomTom Flow** (`tomtom_flow_history.jsonl`) | ⏱️ **~3 min/execução, mas 3–5 dias de calendário** | `api_caller.py` leva ~22 seg para 86 arestas. Mas o research_plan exige **3–5 coletas em dias úteis distintos no horário de pico** para mediana confiável |
| 6 | **GeoPackage TomTom** (`gama_drive_reduced_tomtom.gpkg`) | ~2 min | Gerado automaticamente pelo `api_caller.py` na última execução |
| 7 | **Análise O/D TomTom Move** (`matriz_od_tomtom.json` + `resultado_trips_tomtom.json`) | ~30–60 min | Requer acesso ao **portal TomTom Move**: criar nova análise, desenhar os portões (gates) na nova região, aguardar processamento (~2 min), baixar resultados. Parte manual no portal web |
| 8 | **Mapeamento zona → nó** (em `build_od_matrix.py`) | ~30 min | Identificar quais `osmid` correspondem a cada portão TomTom na nova região. Trabalho manual de inspeção no QGIS/mapa |

---

## Timeline Realista

```
Dia 0 (hoje, ~3h de trabalho):
├── [15 min]  Escolher nova região e baixar polígono
├── [5 min]   Rodar osmnx-api.py → grafo completo
├── [30 min]  Selecionar subgrafo reduzido (definir critérios)
├── [2 min]   Converter para GeoPackage
├── [3 min]   Primeira coleta TomTom Flow (pico da tarde)
├── [45 min]  Criar análise O/D no TomTom Move + baixar
└── [30 min]  Mapear zonas TomTom → nós do grafo

Dias 1–4 (5 min/dia):
├── Rodar api_caller.py 1x/dia no horário de pico
└── (pode ser automatizado com o GitHub Actions que já existe no repo!)

Dia 5 (~1h de trabalho):
├── Agregar coletas TomTom (mediana por aresta)
└── Enriquecer grafo com todos os atributos (lanes, capacity, t0, K)
```

---

## Os 3 Gargalos Reais

### 1. 📅 Coleta TomTom multi-dia (gargalo de calendário)

As coletas atuais do Gama foram feitas em 4 dias úteis (07–10/out), entre 18h–22h BRT — bom. Mas se trocar de região, **recomeça do zero**. O research_plan pede 3–5 dias. Já existe um [workflow GitHub Actions](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/.github/workflows/traffic.yml) que pode automatizar isso.

> [!TIP]
> Se você rodar a primeira coleta **hoje** e configurar o GitHub Actions para as próximas, em 5 dias úteis (sexta que vem) os dados estariam prontos sem esforço adicional.

### 2. 🗺️ Análise O/D no TomTom Move (gargalo de acesso)

A análise O/D do Gama já está feita. Para uma nova região, precisa:
- Ter acesso ao portal TomTom Move (vocês já têm, pelo que vi)
- Desenhar novos portões/regiões manualmente no portal
- Aguardar processamento (~2 min)

Não é difícil, mas é manual e requer o login no portal.

### 3. 🔍 Seleção do subgrafo reduzido (gargalo de decisão)

Não existe script para isso — a seleção dos 30 nós do Gama foi feita ad-hoc. Para a nova região, vocês precisam decidir:
- Quais interseções incluir (priorizar diversidade de `highway` types)
- Garantir que as bordas coincidam com pontos que tenham dados de fluxo
- Garantir conectividade do subgrafo

> [!IMPORTANT]
> Este é o ponto onde a escolha da região importa mais. Se escolherem uma região onde as bordas são rodovias com radares (ex: EPTG ↔ Águas Claras, fechando na EPVP), a matriz OD fica muito mais fácil de calibrar. O Gama tem o problema de ser muito residencial e interno.

---

## Recomendação

| Cenário | Recomendação |
|---------|-------------|
| **Trocar agora** | Viável. ~3h hoje + 5 min/dia por 4 dias. Custo principal é o calendário da coleta TomTom |
| **Ficar no Gama** | Mais rápido, mas o grafo 100% `residential` é uma limitação séria para o modelo — pouca variação de capacidade, $K$ e comportamento VDF. O artigo ficaria mais fraco |
| **Meio-termo** | Expandir o polígono do Gama para incluir as vias arteriais de acesso (BR-040, DF-480) — menor retrabalho que trocar de região inteira, mas ganha diversidade viária |
