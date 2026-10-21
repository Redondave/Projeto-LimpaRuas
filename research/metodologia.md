# Metodologia — estudo do trevo EPCT / EPIP / DF-480 (Gama, DF)

*Versão de 15/10/2026. Documento-base para a seção de metodologia do artigo.*

**Escopo e status.** Descreve o que já foi feito, com os números exatos dos arquivos do repositório, o que ainda falta fazer e o que será calculado. Cada seção indica seu status: **[feito]**, **[a fazer]** ou **[decisão pendente]**. Os problemas do modelo e as decisões tomadas sobre eles estão em `problemas_do_modelo.md`. Os detalhes operacionais estão em `o_que_falta_fazer_pre_frank_wolfe.md`; a fundamentação teórica e as referências, em `research_plan.md` e `articles.md`.

---

## 1. Visão geral

**Pergunta de pesquisa.** Quais intervenções na infraestrutura aumentam o índice de desempenho de velocidade (K = SPI = V_med / V_max) de uma via crítica? E como essas intervenções afetam o tempo total de viagem do sistema (TSTT) e a redistribuição do tráfego na rede (propagação e Paradoxo de Braess)?

**Abordagem.** Alocação estática de tráfego com equilíbrio do usuário (Wardrop, 1952), resolvida pelo algoritmo de Frank-Wolfe (LeBlanc et al., 1975). O tempo de cada aresta segue a função volume-atraso do BPR (1964). A rede, a demanda e os atributos de via vêm de dados observados:

| Componente | Fonte |
|---|---|
| Rede viária | OpenStreetMap, via OSMnx |
| Demanda | TomTom O/D Analysis, calibrada com contadores do DETRAN-DF |
| Velocidades observadas | TomTom Traffic Stats |
| Faixas e limites de velocidade | OpenStreetMap, completado pelo Código de Trânsito Brasileiro |

Os cenários de intervenção são aplicados manualmente ao grafo (nível superior do DNDP); cada um é reequilibrado e comparado com a situação atual.

**Fluxo de trabalho:**

```
OSM ──► grafo (134 nós, 236 arestas) ──┬──► faixas e limite (OSM + CTB) ──► capacidade
                                       │
TomTom O/D ──► matriz OD (amostra) ──► ×fator (DETRAN) ──► matriz OD em veíc/h
                                       │
TomTom Traffic Stats (pico, madrugada) ┴──► v_pico, v_madrugada ──► K inicial, v0, t0
                                                      │
                     grafo atribuído (t0, capacidade) + matriz OD
                                                      │
              Frank-Wolfe (situação atual) ──► validação ──► cenários ──► ΔTSTT, ΔK
```

**Período de referência.** Pico da tarde de dia útil, **18:00–19:00, julho de 2026**. A matriz OD e as velocidades de pico usam essa mesma janela e esse mesmo mês.

---

## 2. Área de estudo e grafo viário [feito]

### 2.1 Escolha da área

A área é o entorno do trevo entre a EPCT (DF-001, Estrada Parque Contorno), a EPIP e a DF-480, no limite do Gama com a Ponte Alta Norte. O ponto de partida foi um grafo de 30 nós e 37 arestas (`cache/gama_drive_sample_30.graphml`). Ele foi extraído do grafo da RA Gama, baixado do OSM com o polígono oficial da RA (Geoportal-DF) e projetado em SIRGAS 2000 / UTM 23S (EPSG:31983). Os 30 nós foram escolhidos à mão, priorizando trechos com atributos completos no OSM.

**Por que o grafo foi expandido:**
- 25 das 37 arestas eram de mão única e havia só uma pista de cada rodovia;
- **nenhum par OD tinha duas rotas distintas**, então o equilíbrio de Wardrop seria igual a uma alocação tudo-ou-nada;
- o polígono da RA cortava a área: a EPCT corre a 2–12 m da divisa, de modo que a pista sentido norte e a EPIP depois do trevo ficavam fora do grafo.

### 2.2 Expansão (`scripts/expand_graph.py`, determinística)

1. **Download.** Rede `drive` do OSM, só da área de estudo (OSMnx 2.1.1, NetworkX 3.5; download de 13/10/2026, salvo em `cache/gama_area_estudo_osm.graphml`). Os 30 nós originais foram forçados como extremidades de aresta na simplificação, o que reproduz as 37 arestas originais sem alteração (o script confere).
2. **Polígono.** Envoltória convexa dos 30 nós originais, com 200 m de folga.
3. **Seleção.** Entram as arestas com as duas extremidades dentro do polígono e classe OSM `tertiary` ou superior (`motorway`, `trunk`, `primary`, `secondary`, `tertiary`, as alças `*_link` e `unclassified`). Os 30 nós originais entram sempre.
4. **Poda.** Remoção iterativa dos nós sem saída (grau 1) a mais de 60 m da borda do polígono, que são becos internos. Os nós perto da borda ficam, porque funcionam como entradas e saídas.
5. **Conectividade.** Fica a componente fracamente conexa que contém os 30 nós.

**Resultado** (`cache/gama_drive_expanded.graphml`): DiGraph com **134 nós e 236 arestas**. Os nós 0–29 mantêm os ids originais.

| Classe OSM | Arestas |
|---|---|
| tertiary | 168 |
| trunk (EPCT) | 20 |
| trunk_link | 17 |
| unclassified | 14 |
| primary (DF-480) | 12 |
| tertiary_link | 4 |
| busway | 1 |

A aresta de busway (23→24) é corredor de ônibus e é excluída da alocação.

**Diagnóstico de rotas** (critério: rota até 30% mais longa que a mais curta, com menos de 60% de arestas em comum, ponderado pela demanda):

| | Grafo de 30 nós | Grafo expandido |
|---|---|---|
| Demanda com pelo menos 2 rotas (matriz final) | — | **46,5%** |
| Demanda com pelo menos 2 rotas (matriz "Gama 3", 30 caixas) | 0% | 40,2% |
| Demanda com algum caminho (matriz "Gama 3") | 97,9% | 100% |

O diagnóstico que motivou a expansão usou a matriz preliminar "Gama 3", que só tinha caixas nos 30 nós. Com a matriz final (1.031 pares, recalculado em 21/10/2026), **46,5% da demanda** tem pelo menos duas rotas competitivas. O grafo de 30 nós não pode ser avaliado com a matriz final, porque a maioria dos nós dela não existe nele.

---

## 3. Coleta de dados [feito]

### 3.1 Inventário

| Dado | Fonte / produto | Período e janela | Arquivo |
|---|---|---|---|
| Rede viária, faixas, limites | OpenStreetMap (OSMnx) | download de 13/10/2026 | `cache/gama_area_estudo_osm.graphml` |
| Viagens origem-destino | TomTom O/D Analysis, *flow matrix*, análise "Gama Final" (id 6604531297533426895), mapa OPEN_DSEG 2026.09 | 01–30/07/2026, dias úteis (22), 18:00–19:00 | `Tables/od_tomtom_gama_final_bruto.json` |
| Velocidade no pico | TomTom Traffic Stats, *Area Analysis*, job 10086419, todas as fontes de sondagem | 02–31/07/2026, dias úteis, 18:00–19:00 | `Tables/traffic_stats_gama_julho.json` |
| Velocidade de madrugada | TomTom Traffic Stats, job 10086478, mesmo polígono | 02–31/07/2026, dias úteis, 00:00–04:00 | `Tables/traffic_stats_gama_madrugada.json` |
| Contagens volumétricas | DER-DF, "Dados de Fluxo Veicular" por trecho rodoviário em janelas de 15 min (portal de dados abertos do DF, licença CC-BY); arquivo baixado em 15/10/2026 | julho/2026 | `flow.csv` (146 MB, fora do git) |
| Geometria dos trechos rodoviários | DER-DF, camada "Rodovias no Distrito Federal" (ArcGIS Hub) | — | `Tables/trechos_com_coordenadas.csv` (gerado por `scripts/mapping.py` a partir de `Tables/Roads.csv`) |
| Limites legais | CTB, Lei 9.503/1997, arts. 60 e 61 | — | regra codificada em `scripts/faixas_limite.py` |

### 3.2 Matriz origem-destino (`scripts/build_od_matrix.py`)

**Desenho da análise.** No portal TomTom O/D Analysis foi desenhada **uma região, uma caixa pequena, sobre cada um dos 134 nós**. Em viagens que começam ou terminam fora das regiões, a TomTom atribui como origem a primeira região em que a viagem entrou e como destino a última de onde saiu. Assim, a visão OD do resultado já é a matriz de entrada e saída do subgrafo.

**Recuperação das contagens.** O resultado vem em percentuais. Todos são múltiplos inteiros de 100/N, sendo N o número de viagens da amostra, o que permite recuperar a contagem absoluta de viagens por par. O script verifica essa propriedade e aborta se ela falhar.

Amostra: **N = 15.429 viagens** em 22 dias úteis.

| Tipo de viagem | Viagens | % |
|---|---|---|
| Passagem (começa e termina fora) | 13.275 | 86,0 |
| Começa fora | 1.038 | 6,7 |
| Termina fora | 946 | 6,1 |
| Ambas as pontas dentro | 170 | 1,1 |

**Região → nó, regras em ordem:**
1. a caixa contém um nó, com tolerância de 5 m: esse nó (129 regiões);
2. a caixa cai no meio de uma aresta (5 regiões):
   - mão única u→v: o nó v;
   - mão dupla: a extremidade mais próxima;
3. caixa fora da rede: o nó mais próximo, até 50 m (nenhum caso).

Quatro nós ficaram sem região (24, 32, 41, 129), e quatro nós receberam duas regiões cada (as contagens são somadas).

**Descartes:**
- 229 viagens com origem e destino no mesmo nó;
- 240 viagens (1,6%) entre pares sem caminho no grafo sem o corredor de ônibus.

Restam **14.960 viagens alocáveis em 1.031 pares OD**.

**Expansão para veículos reais.** A amostra TomTom é uma fração da frota. O fator de expansão é calibrado com os contadores do DETRAN:
- **Pontos de calibração (automáticos).** Caixas sobre um nó de uma pista de rodovia com contador, com uma aresta de entrada e outra de saída da mesma rodovia (tag `ref` do OSM) alinhadas. A caixa não pode tocar outra via, e o nó fica a até 60 m do trecho do DER. O sentido (crescente ou decrescente) sai do rumo da pista comparado ao rumo local do trecho. Resultado: 25 caixas limpas em 4 pistas.
- **Volume DETRAN.** Mediana, nos dias úteis de julho/2026 (o mesmo mês da TomTom), do volume total das 18h. Só entram os dias com as 96 janelas de 15 min e total diário ≥ 100 veículos.
- **Fator da pista** = volume DETRAN ÷ mediana das viagens TomTom por hora nas caixas da pista:

| Pista DETRAN | Sentido | DETRAN julho (veíc/h) | Dias úteis válidos | TomTom (viagens/h) | Fator |
|---|---|---|---|---|---|
| DF-001 001EDF0250 | decrescente | 2.265 | 23 | 103,1 (1 caixa) | 21,96 |
| DF-001 001EDF0270 | crescente | 1.626 | 1 | 184,4 (8 caixas) | 8,82 |
| DF-480 480EDF0030 | crescente | 1.421 | 21 | 140,9 (3 caixas) | 10,08 |
| DF-480 480EDF0030 | decrescente | 2.530 | 21 | 176,3 (7 caixas) | 14,35 |

**Fator adotado: 12,21** (mediana das 4 pistas). Os fatores mínimo (8,82) e máximo (21,96) definem as rodadas de demanda baixa e alta, obrigatórias em todas as simulações (seção 6.5 e `problemas_do_modelo.md`, problema 3).

A primeira versão foi calibrada com as contagens de abril/2026. Com as de julho, os volumes mudaram entre −6% e +8% e o fator adotado não mudou.

**Demanda:** `q_od = (viagens do par na amostra / 22 dias) × fator`. Com o fator adotado, o total é de **8.309 veíc/h** em 1.031 pares (`Tables/matriz_od_final.json`).

O arquivo também guarda, para validação, a passagem observada em cada caixa (`regioes[].passagens_veic_h`; 126 caixas com 100 ou mais passagens na amostra) e as 4 observações do DETRAN.

### 3.3 Velocidades observadas (`scripts/velocidades_traffic_stats.py`)

A TomTom Traffic Stats devolve os 1.473 trechos da rede TomTom dentro do polígono. Cada trecho vem com a geometria no sentido de circulação e, para a janela pedida, as velocidades média, mediana e harmônica, os percentis e a amostra normalizada.

| Janela | Trechos com velocidade |
|---|---|
| Pico | 886 |
| Madrugada | 811 |

**Casamento trecho → aresta.** O trecho precisa correr a até 8 m da aresta por pelo menos 5 m, com o cosseno entre os rumos locais ≥ 0,7 (no máximo ~45°). O critério de sentido separa as duas mãos de uma via de mão dupla e descarta a pista paralela e as transversais. Trechos fora do grafo não encostam em nenhuma aresta. No pico, 431 trechos foram usados.

**Velocidade da aresta.** Média harmônica das velocidades harmônicas dos trechos, ponderada pelo comprimento sobreposto:

  v = Σ Lᵢ / Σ (Lᵢ / vᵢ)

É a velocidade que reproduz o tempo de percurso somado dos trechos.
- **Aresta "ok":** pelo menos 50% do comprimento coberto por trechos com dado.
- **Amostra baixa:** amostra normalizada < 0,01.

**Resultado no pico:**

| Status | Arestas |
|---|---|
| ok | 233 |
| parcial | 1 |
| sem trecho | 1 |
| corredor de ônibus | 1 |

Na madrugada, 234 das 235 arestas de carro ficaram com dado.

| Classe | v_pico mediana | v_madrugada mediana |
|---|---|---|
| EPCT (trunk) | 29 km/h | 42 km/h |
| DF-480 (primary) | 57 km/h | 68 km/h |
| alças (trunk_link) | 36 km/h | 39 km/h |
| terciárias | 25 km/h | 28 km/h |

### 3.4 Faixas e limite de velocidade (`scripts/faixas_limite.py`)

**Prioridade, para cada atributo:**
1. tag do próprio trecho no OSM (`lanes`, `maxspeed`);
2. mesma via no OSM: trechos com o mesmo nome e a mesma classe, desde que todos concordem;
3. regra:
   - **limite** pelo art. 61, § 1º, I do CTB, com a categoria da via (art. 60) deduzida da classe OSM conforme a página "Classificação de vias" do OSM Brasil:

     | Classe OSM | Categoria (art. 60) | Limite |
     |---|---|---|
     | motorway, trunk e alças | trânsito rápido | 80 km/h |
     | primary, secondary e alças | arterial | 60 km/h |
     | tertiary e alças | coletora | 40 km/h |
     | unclassified, residential | local | 30 km/h |

   - **faixas** pelo padrão das próprias vias da área com a tag: 2 por sentido nas rodovias, 1 nas demais;
4. correção manual, a partir da conferência no Google Maps (`Tables/faixas_limite_correcoes.csv`).

**Conversões:**
- `lanes` do OSM conta as duas mãos, então em via de mão dupla faixas por sentido = ⌊lanes/2⌋, com mínimo de 1;
- tag em lista (trechos fundidos): o menor valor, que é o gargalo.

**Cobertura:**

| Atributo | OSM | Mesma via | Regra |
|---|---|---|---|
| Faixas | 113 | 30 | 93 |
| Limite | 71 | 18 | 146 |

A TomTom Snap to Roads também foi testada como fonte e descartada: o limite só concordou com o OSM em 14 de 71 arestas e veio 100 km/h em 31 ruas locais.

---

## 4. Atributos das arestas para a alocação [feito; refazer após a conferência manual]

Script: `scripts/enrich_graph.py`. Saída: `cache/gama_drive_expanded_atributos.graphml`, que deve ser lido com `nx.read_graphml`.

### 4.1 Capacidade

  c = faixas por sentido × capacidade por faixa (veíc/h, por sentido)

Capacidade por faixa, dentro das faixas da literatura brasileira citadas no plano (expressas ~1.800–2.000; arteriais principais ~1.000–1.200; secundárias e locais ~500–900):

| Classe | veíc/h/faixa | c resultante (veíc/h) |
|---|---|---|
| trunk | 1.800 | 3.600 ou 5.400 |
| trunk_link | 1.200 | 1.200 |
| primary | 1.200 | 3.600 |
| tertiary | 900 | 900 ou 1.800 |
| tertiary_link, unclassified | 600 | 600 |

**Sanidade da capacidade nominal.** Nas 4 pistas com contador (julho/2026), V/C = 0,63, 0,45, 0,39 e 0,70, todos abaixo do limite de alerta de 1,2.

### 4.1.1 Capacidade efetiva nos gargalos do trevo [decidido e feito em 15/10]

Junto ao trevo, a EPCT e a DF-480 ficam lentas no pico com só ~60% da capacidade nominal ocupada. A lentidão vem da fila e do entrelaçamento no trevo, que a função BPR por aresta não representa (`problemas_do_modelo.md`, problema 1). Nesses trechos, a capacidade foi substituída pela **capacidade efetiva**: a que faz a BPR reproduzir o tempo observado no pico.

1. **Fluxo atual por aresta:** a matriz OD alocada tudo-ou-nada pelos caminhos mínimos com os tempos observados no pico. Conferência com as passagens das caixas TomTom: correlação de 0,95 em 40 arestas; o estimado fica, na mediana, 7% abaixo.
2. **Gargalo:** aresta de rodovia (trunk, primary, motorway e alças) que cumpre todas as condições:
   - velocidade observada ok;
   - fluxo ≥ 30% da capacidade nominal;
   - t_obs/t0 − 1 maior que o atraso previsto pela BPR em mais de 0,05.
3. **Capacidade efetiva:** c_ef = x / ((t_obs/t0 − 1) / α)^(1/β), limitada à nominal.

**Resultado:** 25 arestas (6,1 km):
- EPCT nos dois sentidos junto ao trevo e DF-480 no sentido sudoeste;
- capacidade efetiva entre 23% e 74% da nominal (de 894 a 2.402 veíc/h por sentido).

**Dependência dos parâmetros:**
- **Fator de expansão:** o conjunto de gargalos é fixo (definido com o fator adotado), e a capacidade efetiva escala com o fator, gravada para os três fatores.
- **Outros α e β:** recalcular a capacidade efetiva com a função `capacidade_efetiva` do script.


### 4.2 Velocidade livre e tempo em fluxo livre

  v0 = min(limite, max(v_madrugada, v_pico));  t0 = L / v0

Sem dado de madrugada, v0 = limite.
- **Por que madrugada.** Com v0 igual ao limite, o tempo observado no pico dava, na mediana, 1,67 vez o t0, com V/C ≤ 0,67, faixa em que a BPR só produz 1–3% de atraso. A diferença vinha de curva, trevo, conversão e semáforo, que existem também com a via vazia. A velocidade de madrugada incorpora essas perdas e deixa para a VDF só o atraso causado pelo volume.
- **Teto no limite:** excesso de velocidade não é referência.
- **Piso na velocidade de pico:** em ruas com pouco tráfego de madrugada, a média saiu mais lenta que no pico (amostra pequena, veículos lentos). A velocidade livre não pode ser menor que a de pico.

| Fonte do v0 | Arestas |
|---|---|
| madrugada | 142 |
| pico (madrugada mais lenta) | 76 |
| limite (madrugada acima dele) | 16 |
| limite (sem dado de madrugada) | 1 |

O t0 somado da rede é 55,7 min.

### 4.3 Campos de cada aresta

- `length`, `classe`, `permite_carro`;
- `lanes_sentido`, `capacidade_por_faixa`, `capacidade_nominal_veic_h`;
- `capacidade_veic_h` (a usada na alocação: efetiva nos gargalos, nominal nas demais), `capacidade_veic_h_fator_min` e `capacidade_veic_h_fator_max`;
- `gargalo`, `fluxo_atual_estimado_veic_h`, `razao_t_obs_t0`;
- `limite_kmh`, `v_madrugada_kmh`, `v0_kmh`, `t0_min`;
- para diagnóstico e validação: `vmed_kmh`, `t_obs_min`, `k_inicial`, `status_velocidade`;
- a fonte de cada valor: `fonte_lanes`, `fonte_limite`, `fonte_v0`.

**Checagens automáticas (todas ok):**
- t0 > 0 e c > 0 em toda aresta de carro;
- 10 ≤ v0 ≤ 120 km/h;
- os 1.031 pares têm caminho;
- todos os nós da matriz existem no grafo.

---

## 5. Indicadores de desempenho

### 5.1 Índice de desempenho de velocidade (K) [feito para a situação observada]

  K = v_pico / limite

É o SPI de He et al. (2016), com o limite de velocidade como denominador, como no `research_plan.md`. O limite fica no K, e a velocidade de madrugada só no t0, para que o K continue comparável com a literatura e entre cenários.

**K observado no pico** (233 arestas): mediana 0,60, quartis 0,44 e 0,74.

| Classe | K mediano |
|---|---|
| EPCT | 0,41 (0,29–0,40 junto ao trevo) |
| alças | 0,44 |
| terciárias | 0,59 |
| DF-480 | 0,71 |

### 5.2 Tempo observado sobre t0 (aderência da situação atual)

  r = t_obs / t0 = v0 / v_pico

É o atraso que o modelo precisa reproduzir na situação atual.

| Recorte | r |
|---|---|
| mediana de todas as arestas | 1,04 |
| rede toda (Σ t_obs / Σ t0) | 1,12 |
| EPCT | 1,36 |
| DF-480 | 1,22 |
| alças | 1,08 |
| terciárias | 1,03 |
| locais | 1,00 |

---

## 6. Etapas a realizar [a fazer]

### 6.1 Conferência manual de faixas e limites

Conferir no Google Maps (satélite e Street View, com links na tabela) principalmente:
- as 10 arestas com K > 1 (provável limite subestimado);
- as terciárias a 40 km/h sem tag;
- as alças a 80 km/h pela regra.

Depois, registrar as correções e rodar, em ordem: `faixas_limite.py` → `velocidades_traffic_stats.py` → `enrich_graph.py`.

### 6.2 Seleção das vias críticas (Passo 1 do plano)

Arestas com K baixo no pico (ex.: K < 0,7) e com demanda OD passando por elas. Saem daqui as vias-alvo e as intervenções candidatas, cada uma justificada.

### 6.3 Implementação do Frank-Wolfe

**Problema de equilíbrio** (Beckmann et al., 1956):

  min Z(x) = Σₐ ∫₀^{xₐ} tₐ(w) dw,  com  tₐ(x) = t0ₐ [1 + α (x / cₐ)^β]

sujeito à conservação de fluxo por par OD, demanda fixa q_od e fluxos não negativos. As arestas com `permite_carro = False` ficam fora.

**Algoritmo:**
1. **Inicialização:** alocação tudo-ou-nada com os custos t0.
2. **Direção:** custos atualizados por tₐ(xₐ), caminhos mínimos (Dijkstra) e alocação tudo-ou-nada auxiliar y.
3. **Passo:** busca linear de λ ∈ [0, 1] que minimiza Z(x + λ(y − x)), por bisseção na derivada.
4. **Atualização:** x ← x + λ(y − x).
5. **Parada:** gap relativo = (Σ xₐ tₐ − Σ_od q_od · custo mínimo_od) / Σ xₐ tₐ < 10⁻⁴, ou 500 iterações.

**Implementação [feito em 21/10]:** `scripts/frank_wolfe.py`.
- **Caminhos mínimos:** Dijkstra do SciPy, de cada uma das 121 origens.
- **Carga tudo-ou-nada:** a demanda é empurrada pela árvore de caminhos mínimos, das folhas para a raiz, em ordem de profundidade na árvore (a ordem por distância falha quando há arestas de custo zero).
- **Busca linear:** bisseção com 60 passos na derivada de Z, que é crescente em λ.
- **Escopo:** cada rodada resolve os três níveis de demanda; as arestas com `permite_carro = False` ficam fora.

**Validação do algoritmo [feito]** (`python scripts/frank_wolfe.py --teste`), em redes com solução conhecida:

| Teste | Esperado | Obtido |
|---|---|---|
| Rede de Braess (1968), 6 veículos, sem a ponte | 3 veículos em cada rota, custo 83 | 3,0 / 3,0, custo 83,000 |
| Rede de Braess, com a ponte | fluxos [4, 2, 2, 4, 2], custo 92 (TSTT sobe de 498 para 552) | [4,0, 2,0, 2,0, 4,0, 2,0], custo 92,000 |
| Duas rotas paralelas com BPR | igualdade de custos resolvida por bisseção: 1.426,9 veíc/h na rota 1 | 1.426,9 |
| Gama, demanda alta | Z de Beckmann não cresce entre iterações | ok (28 iterações) |
| Gama, demanda alta | conservação de fluxo em todos os nós | desvio máximo 4 × 10⁻¹² veíc/h |

**Benchmark de Sioux Falls [pendente].** O comando `--sioux-falls PASTA` lê `SiouxFalls_net.tntp`, `_trips.tntp` e `_flow.tntp` (repositório *TransportationNetworks*) e compara o TSTT e os fluxos com a solução de referência. Os arquivos ainda não foram baixados.

**Convergência na rede do Gama** (situação atual): gap < 10⁻⁴ em 2 iterações (demanda baixa), 4 (adotada) e 28 (alta), em até 2 s. Na demanda alta aparece o zigue-zague típico do Frank-Wolfe perto do ótimo.

### 6.4 Situação atual e conferência do modelo

Rodar a alocação com a rede atual e a matriz OD, nos três níveis de demanda. Conferências previstas:
- **fluxo modelado × passagem observada** nas caixas da TomTom (`regioes[].passagens_veic_h`). Testa a escolha de rota, não a demanda total, porque a matriz vem das mesmas viagens;
- **tempo modelado × tempo observado,** por classe. Só é independente fora dos 25 gargalos (calibrados pelo tempo) e dos 76 trechos com tempo livre tirado do pico;
- **fluxo modelado × contagens do DETRAN.** Não é validação, porque as 4 pistas calibram o fator.

Métricas: GEH, RMSE relativo e R² dos fluxos; razão entre o tempo modelado e o observado.

**Resultado da situação atual [feito em 21/10]** (`resultados/base/resumo.json`, campo `conferencias`, demanda adotada):

| Comparação | O que testa | Resultado |
|---|---|---|
| Fluxo × passagens TomTom (40 arestas medidas isoladamente) | escolha de rota | correlação 0,93; modelo/observado 0,94 (mediana); GEH mediano 3,5; 60% com GEH < 5; RMSE relativo 0,32 |
| Tempo × observado, 130 arestas não calibradas | VDF e t0 | modelo/observado 0,91 (mediana); 53% dentro de ±10%. O modelo fica mais rápido sobretudo nas terciárias (0,90), onde o atraso de cruzamento não depende do volume |
| Tempo × observado, 104 arestas calibradas (gargalos e t0 do pico) | nada (calibradas) | 1,00 |
| Tempo total ponderado pelo fluxo | aderência global | modelo/observado 0,972 |
| Movimento nos nós dos 4 contadores DETRAN | nada (calibram o fator) | o modelo reproduz o que o fator único implica (por exemplo, 1.259 contra 1.259 esperados em 001EDF0250); a diferença para a contagem é a variação do fator entre as pistas |

**Indicadores da situação atual:**

| Demanda | veíc/h | TSTT (veíc·h) | K da rede | Velocidade média | Arestas com V/C > 1 |
|---|---|---|---|---|---|
| baixa (8,82) | 6.002 | 343,4 | 0,703 | 45,2 km/h | 20 |
| adotada (12,21) | 8.309 | 476,9 | 0,700 | 45,1 km/h | 20 |
| alta (21,96) | 14.944 | 884,4 | 0,676 | 43,7 km/h | 26 |

As 20 arestas com V/C > 1 são os gargalos calibrados, cuja capacidade efetiva escala com o fator.

**Decisão (15/10): não haverá validação com dados retidos,** por falta de tempo. O artigo declara o que foi usado para calibrar e o que foi usado para conferir. As alternativas ficam como trabalho futuro em `problemas_do_modelo.md`, problema 2: deixar um contador de fora, validar pelo tempo nos trechos não calibrados, dados de outro mês e contagens manuais.

### 6.5 Cenários de intervenção (nível superior do DNDP, manual)

Cópias do grafo, cada uma com uma alteração discreta:
- **faixa adicional:** lanes + 1, logo c aumenta;
- **mudança de sentido / mão única:** inverter ou remover a aresta oposta;
- **remoção ou fechamento de aresta:** teste de Braess (método da Southeast University: remover uma ou duas arestas por vez e medir o TSTT em vários níveis de demanda);
**Faixa adicional num trecho de gargalo:** capacidade nova = capacidade efetiva × (faixas + 1) / faixas. Não se soma a capacidade nominal de uma faixa. A regra é otimista se a fila nascer mais à frente, e isso deve ser declarado.

Cada cenário é reequilibrado com o Frank-Wolfe. A meta é de 15 a 30 cenários. A automação com NSGA-II é opcional e futura.

**Como rodar [ferramenta pronta em 21/10].** Cada cenário é um JSON em `cenarios/`, rodado com `python scripts/frank_wolfe.py --cenario cenarios/<arquivo>.json`. Tipos de alteração:

| Tipo | Efeito |
|---|---|
| `faixa` | +n faixas, com a regra do gargalo acima |
| `remover` | fechamento da aresta |
| `inverter` | mão única invertida |
| `capacidade` | multiplica a capacidade da aresta |

O script recusa um cenário que desconecte algum par OD. A comparação com a situação atual sai nível a nível em `resultados/<cenario>/resumo.json`: ΔTSTT, ΔK da rede e as maiores mudanças de fluxo. `cenarios/exemplo_faixa_epct_norte.json` é só um exemplo de sintaxe (+1 faixa nos 5 gargalos da EPCT sentido norte): TSTT −8,6% nos três níveis e quase nenhuma mudança de rota.

**Consequência da calibração para os três níveis.** Nos 25 gargalos, a capacidade efetiva escala com o fator, então a razão V/C desses trechos é a mesma nos três níveis. Cada nível é um "mundo" coerente que reproduz os tempos observados com aquela demanda. Por isso:
- intervenções nos gargalos tendem a dar a mesma variação percentual nos três níveis (no exemplo, −8,59%, −8,57% e −8,32%);
- a diferença entre os níveis aparece nas arestas não calibradas, onde a capacidade é a nominal.

Uma conclusão "robusta" sobre um gargalo é, em parte, robusta por construção, e isso deve ser dito no artigo.

> ⚠️ **Obrigatório: toda simulação (situação atual e cada cenário) roda com os três fatores de expansão.**
>
> | Rodada | Fator | Demanda total | Capacidade |
> |---|---|---|---|
> | demanda baixa | 8,82 | ~6.000 veíc/h | `capacidade_veic_h_fator_min` |
> | demanda adotada | 12,21 | 8.309 veíc/h | `capacidade_veic_h` |
> | demanda alta | 21,96 | ~14.940 veíc/h | `capacidade_veic_h_fator_max` |
>
> A demanda de cada par é `veic_h × (fator / 12,21)`.
>
> **Por quê:** o fator varia 2,5 vezes entre as 4 pistas de calibração, e nada nos dados indica qual é o verdadeiro. Como a BPR é muito não linear (dobrar o volume multiplica o atraso por 16), o nível de demanda muda o comportamento da rede, não só os números. O efeito de uma intervenção, e a ocorrência de Braess, pode existir num nível e não em outro. Por isso, cada conclusão é classificada como:
> - **robusta:** vale nos três níveis;
> - **dependente da demanda:** o artigo diz em quais níveis vale;
> - **não sustentada:** muda de sinal entre os níveis.
>
> Rodar só com 12,21 esconderia a principal incerteza do modelo.

### 6.6 Análise de sensibilidade

- α, β = 0,15 / 4 (referência) e 0,8 / 4,7. Ao trocar α e β, recalcular a capacidade efetiva dos gargalos com a função `capacidade_efetiva`, para que a situação atual continue reproduzindo o tempo observado;
  - **feito para a situação atual (21/10):** `python scripts/frank_wolfe.py --alpha 0.8 --beta 4.7` → `resultados/base_a0.8_b4.7`. Nas demandas baixa e adotada, o resultado quase não muda (TSTT +0,2% e +0,7%). Na demanda alta, a rede fica bem mais congestionada (TSTT 1.166,6 contra 884,4 veíc·h, +32%; K da rede 0,51 contra 0,68) e o Frank-Wolfe precisa de 190 iterações. Então α e β pesam justamente nos cenários de demanda alta;
- o fator de expansão não é sensibilidade opcional: entra em todas as rodadas (6.5);
- matriz sem os pares com menos de 5 viagens na amostra;
- capacidade por faixa nos extremos das faixas da literatura.

---

## 7. O que será calculado

| Grandeza | Definição | Uso |
|---|---|---|
| Fluxo de equilíbrio | xₐ, saída do Frank-Wolfe | redistribuição do tráfego |
| Tempo da aresta | tₐ = t0ₐ [1 + α (xₐ/cₐ)^β] | — |
| Grau de saturação | xₐ / cₐ | gargalos |
| Velocidade modelada | vₐ = Lₐ / tₐ | — |
| K modelado | Kₐ = vₐ / limiteₐ | via-alvo e vizinhas, antes e depois |
| TSTT | Σₐ xₐ tₐ(xₐ), em veíc·min | eficiência sistêmica |
| Variações | ΔTSTT = TSTT_cenário − TSTT_base; ΔKₐ; Δxₐ | efeito da intervenção |
| K de rede | média dos Kₐ ponderada por veículo·km (Σ xₐLₐKₐ / Σ xₐLₐ) | desempenho agregado |
| Braess | ΔK_alvo > 0 com ΔTSTT > 0, ou ΔTSTT < 0 ao remover uma aresta | tese central |

**Tese a testar.** Aumentar o K de uma via isolada pode piorar o TSTT da rede, por propagação ou Paradoxo de Braess. Se isso acontecer, intervenções pautadas só por métricas locais não bastam.

---

## 8. Reprodutibilidade

```bash
python scripts/expand_graph.py               # grafo (offline, a partir do cache do OSM)
python scripts/build_od_matrix.py --offline  # matriz OD (precisa do flow.csv do DETRAN)
python scripts/faixas_limite.py              # faixas e limite
python scripts/velocidades_traffic_stats.py  # velocidades de pico e madrugada, K inicial
python scripts/enrich_graph.py               # grafo atribuído + checagens
python scripts/frank_wolfe.py --teste        # valida o algoritmo (Braess, duas rotas, propriedades)
python scripts/frank_wolfe.py                # situação atual, três níveis de demanda
python scripts/frank_wolfe.py --cenario cenarios/<arquivo>.json   # cenário + comparação
python scripts/visualizar_resultados.py      # resultados/painel.html e resultados/figuras/*.png
```

Os resultados brutos das APIs ficam no repositório sem chaves nem identificadores de conta.

---

## 9. Problemas a superar no estado atual

*Os problemas 1 a 4 estão detalhados, com gravidade e decisão, em `problemas_do_modelo.md`.*

1. **Atraso no trevo — resolvido por calibração.** A EPCT e a DF-480 tinham 36% e 22% de atraso no pico que a BPR não reproduzia (fila e entrelaçamento no trevo). Decisão: capacidade efetiva em 25 arestas de gargalo (seção 4.1.1). Fica a limitação de que a BPR continua sem propagar a fila se um cenário mudar muito o fluxo que chega ao trevo.
2. **Validação pouco independente — aceito.** As 4 pistas do DETRAN calibram o fator de expansão, então não validam o volume total. A passagem nas caixas vem da mesma amostra TomTom que gerou a matriz, então só testa a escolha de rota. O tempo observado agora também calibra os gargalos. Decisão: sem validação com dados retidos, por falta de tempo; alternativas documentadas como trabalho futuro.
3. **Fator de expansão incerto — contornado rodando os três fatores.** As contagens de julho/2026 foram baixadas, o que elimina a defasagem de meses (que era pequena: −6% a +8% nos volumes). Mas o fator ainda varia de 8,82 a 21,96 entre as pistas: uma tem uma só caixa, outra um só dia de contagem, e o mesmo fator vale para todos os pares. **Todos os cenários rodam com os três fatores** (seção 6.5).
4. **Tráfego de passagem dominante — aceito como característica da área.** 86% das viagens atravessam a área, e só 40% da demanda tem rota alternativa. Os cenários priorizam a malha interna, os fechamentos e a demanda alta para aproveitar quem tem escolha.
5. **Atributos inferidos.**
   - 146 dos 235 limites e 93 das faixas vêm de regra (CTB e padrão por classe), pendentes de conferência manual.
   - 10 arestas têm K > 1, sinal de limite subestimado.
   - Como o limite é o denominador do K e o teto do v0, um erro de limite muda K e t0.
6. **Capacidade da literatura, não medida.** Os valores por faixa vêm de faixas genéricas (expressas, arteriais, locais), sem ajuste por largura, rampas, semáforos ou entrelaçamento. A literatura indica que a capacidade pesa mais na incerteza do modelo do que α e β. Nos 25 gargalos, a capacidade foi calibrada pelo tempo observado (item 1); nas demais arestas, segue a nominal.
7. **Amostra baixa em parte das arestas.** 14 arestas no pico e 52 na madrugada (terciárias e locais). Nelas, 76 arestas usam a velocidade de pico como v0 por precaução.
8. **Limites do modelo.**
   - Alocação estática e determinística de uma hora: sem fila que se propaga entre arestas, sem semáforo explícito, demanda fixa (sem mudança de modo ou horário).
   - O grafo exclui as vias residenciais, então atalhos por ruas locais não são simulados.
9. **Cobertura da matriz.**
    - Quatro nós sem região (24, 32, 41, 129).
    - 1,6% da demanda descartada por falta de caminho; parte dela recuperável com caixas nos nós 32 e 41 e as ligações até o nó 127.
    - Nenhum ponto de calibração na EPIP.
10. **Detalhes a declarar.**
    - As janelas de datas diferem um dia: O/D de 01 a 30/07, Traffic Stats de 02 a 31/07.
    - As versões de mapa da TomTom diferem entre os produtos (O/D: 2026.09; Traffic Stats: 2025.12).
    - O grafo de 30 nós original foi selecionado à mão.
11. **Frank-Wolfe implementado e validado em redes com solução conhecida** (seção 6.3). Falta o benchmark de Sioux Falls (arquivos não baixados). As vias críticas e os cenários ainda não foram definidos (seções 6.2 e 6.5).
