# Avaliação: O que falta antes do Frank-Wolfe

## Contexto
O [research_plan.md](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/research/research_plan.md) define **4 categorias de dados** que cada aresta do grafo precisa ter para o algoritmo de Frank-Wolfe funcionar. Abaixo, cruzo cada requisito contra o que o repositório já tem.

---

## O Grafo Atual

O grafo reduzido ([gama_drive_reduced.graphml](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/cache/gama_drive_reduced.graphml)) tem:

| Métrica | Valor |
|---------|-------|
| Nós | **30** |
| Arestas | **86** |
| CRS | EPSG:31983 (SIRGAS 2000 / UTM 23S) |
| Região | Gama (DF) |

### Atributos **presentes** em cada aresta do GraphML

| Atributo | Cobertura | Notas |
|----------|-----------|-------|
| `osmid` | ✅ 86/86 | ID do OSM |
| `highway` | ✅ 86/86 | Todas `residential` (veja alerta abaixo) |
| `oneway` | ✅ 86/86 | Booleano |
| `reversed` | ✅ 86/86 | Booleano |
| `length` | ✅ 86/86 | Em **metros** (projetado UTM) |
| `name` | parcial | Algumas arestas têm nome de rua |
| `maxspeed` | ⚠️ **16/86** (~19%) | Apenas arestas de vias nomeadas |
| `lanes` | ❌ **0/86** | Completamente ausente |
| `geometry` | parcial | Nem todas têm geometria explícita |

> [!WARNING]
> Todas as 86 arestas são classificadas como `residential`. Isso significa que o subgrafo selecionado **não contém vias arteriais, coletoras ou expressas** — o que é um problema sério para o modelo de capacidade e para a variação da VDF, já que vias residenciais têm comportamento de tráfego muito diferente de arteriais/expressas.

---

## Checklist: Requisitos do research_plan vs. Estado Atual

### 1. Dados Topológicos e Físicos (OSMnx + DER-DF)

| Atributo Exigido | Status | O que falta |
|-------------------|--------|-------------|
| Comprimento ($L$) | ✅ Pronto | `length` em metros, presente em todas as arestas |
| Velocidade de Fluxo Livre ($V_0$) via `maxspeed` | ⚠️ **81% sem dados** | Apenas 16/86 arestas têm `maxspeed`. **Falta**: heurística de preenchimento por `highway` type (ex: `residential` → 30 km/h) |
| Tempo de Fluxo Livre ($t_0 = L / V_0$) | ❌ Não calculado | Depende de $V_0$ estar completo primeiro |
| Tipo de Via (`highway`) | ✅ Presente, mas **homogêneo** | 100% `residential` — precisaria incluir arteriais/coletoras no grafo |
| Nº de Faixas (`lanes`) | ❌ **Zero cobertura** | **Nenhuma** aresta tem `lanes`. Precisa de heurística ou enriquecimento via DER |

### 2. Capacidade Teórica ($c$)

| Atributo Exigido | Status | O que falta |
|-------------------|--------|-------------|
| Capacidade por faixa (DNIT) | ❌ Não implementado | Precisa de tabela de mapeamento `highway` → capacidade/faixa |
| Capacidade Total ($c$ = `lanes` × cap/faixa) | ❌ Não calculado | Depende de `lanes` e da tabela acima |

### 3. Velocidade Real (TomTom)

| Atributo Exigido | Status | O que falta |
|-------------------|--------|-------------|
| $V_{med}$ (velocidade empírica de pico) | ⚠️ **Parcialmente coletado** | O [api_caller.py](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/scripts/api_caller.py) coletou dados para as 86 arestas do grafo reduzido. São **430 registros** em [tomtom_flow_history.jsonl](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/cache/tomtom_flow_history.jsonl) (~5 coletas/aresta). **Mas**: a coleta precisa ser feita em **dias úteis no horário de pico** — verificar timestamps |
| `freeFlowSpeed` (TomTom) | ✅ Presente nos registros | Alternativa a `maxspeed` do OSM, já coletado |
| `currentSpeed` | ✅ Presente nos registros | Velocidade instantânea no momento da chamada |
| $K$ inicial ($V_{med}/V_0$) | ❌ Não calculado | Precisa agregar as coletas TomTom (mediana por aresta) e dividir por $V_0$ |

> [!IMPORTANT]
> O `freeFlowSpeed` do TomTom (52 km/h na amostra vista) pode ser uma alternativa mais confiável que o `maxspeed` do OSM para estimar $V_0$, **especialmente** nas 70 arestas sem `maxspeed`. O research_plan menciona priorizar `maxspeed` do OSM, mas reconhece que o TomTom é alternativa válida.

### 4. Matriz Origem-Destino

| Atributo Exigido | Status | O que falta |
|-------------------|--------|-------------|
| Dados TomTom O/D Analysis | ✅ Coletado | [matriz_od_tomtom.json](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/Tables/matriz_od_tomtom.json) e [resultado_trips_tomtom.json](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/Tables/resultado_trips_tomtom.json) — análise do Gama, dias úteis, jul/2026, horário de pico (7h–9h) |
| Mapeamento zona TomTom → nó do grafo | ❌ **Não preenchido** | O script [build_od_matrix.py](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/scripts/build_od_matrix.py) está pronto, mas `ZONE_TO_NODES` está com **listas vazias** (`[]`). Precisa mapear os 7 portões TomTom para os `osmid` dos nós de borda do grafo |
| Fator de expansão calibrado | ⚠️ Placeholder | Está em `FATOR_EXPANSAO = 20.0` — valor arbitrário que precisa ser justificado ou calibrado |
| Matriz OD final em formato nó-a-nó | ❌ Não gerada | Depende do mapeamento acima |

---

## Resumo: O que falta fazer (em ordem de prioridade)

### 🔴 Bloqueantes para o Frank-Wolfe

1. **Enriquecer o grafo com `lanes`** — Zero cobertura. Aplicar heurística por `highway` type ou enriquecer via dados do DER/spatial join.

2. **Completar `maxspeed` / $V_0$** — 81% das arestas sem dados. Opções:
   - Usar `freeFlowSpeed` da TomTom como proxy (já coletado)
   - Heurística por `highway` type (30 km/h para `residential`)
   - Ambos combinados

3. **Calcular capacidade ($c$)** — Implementar tabela `highway` → capacidade/faixa (Manual DNIT) e calcular $c = \text{lanes} \times \text{cap\_faixa}$.

4. **Calcular $t_0$** — Trivial: $t_0 = L / V_0$, mas depende dos itens 2 e 3.

5. **Mapear zonas TomTom → nós do grafo** — Preencher `ZONE_TO_NODES` no [build_od_matrix.py](file:///d:/Projetos_UnB/Semestre_6/Projeto-LimpaRuas/scripts/build_od_matrix.py) e gerar a matriz OD final.

### 🟡 Importantes mas não bloqueantes

6. **Agregar coletas TomTom** — Calcular mediana de `currentSpeed` por aresta (filtrada por dia útil + horário de pico) para obter $V_{med}$ confiável.

7. **Calcular $K$ inicial** — $K = V_{med} / V_0$ para cada aresta → mapa de calor diagnóstico.

8. **Revisar a região de estudo** — O grafo atual é 100% `residential` no Gama. O research_plan sugere uma região com arteriais + coletoras (ex: Águas Claras / EPTG) para ter variação interessante de $K$ e capacidade. Considerar se o Gama é a região definitiva ou se precisa mudar.

### 🟢 Prontos / Parcialmente prontos

9. ✅ Grafo OSMnx com topologia e `length` corretos
10. ✅ Pipeline TomTom Flow API funcional com histórico de 5 coletas
11. ✅ Dados de O/D da TomTom coletados (falta só mapear para nós)
12. ✅ Scripts de conversão GraphML → GeoPackage
13. ✅ Dados do DER-DF (Roads.csv, Speeds.csv, Flow.csv) disponíveis

---

## Proposta do que implementar no "próximo prompt"

Conforme você mencionou, o plano é **enriquecer cada aresta do grafo** com todos os atributos necessários. Isso significaria criar um script que:

1. Carrega o grafo reduzido
2. Preenche `maxspeed` faltante (via heurística ou TomTom `freeFlowSpeed`)
3. Preenche `lanes` faltante (via heurística por `highway` type)
4. Calcula `capacity` ($c$) por aresta
5. Calcula `t0` ($t_0 = L/V_0$) por aresta
6. Agrega dados TomTom para obter `v_med` por aresta
7. Calcula `K` ($K = V_{med}/V_0$) por aresta
8. Salva o grafo enriquecido

> [!NOTE]
> Só com os itens 1–5 completos o Frank-Wolfe já pode rodar (junto com a matriz OD). Os itens 6–7 são para o diagnóstico inicial, mas não são input direto do algoritmo.
