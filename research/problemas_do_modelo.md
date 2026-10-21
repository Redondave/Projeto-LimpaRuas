# Problemas do modelo e decisões tomadas

*Versão de 15/10/2026. Documenta os quatro problemas encontrados ao preparar o modelo antes do Frank-Wolfe: o que cada um é, quão grave é, o que foi decidido e o que foi feito. A metodologia completa está em `metodologia.md`.*

| # | Problema | Gravidade | Decisão | Situação |
|---|---|---|---|---|
| 1 | Atraso no trevo que a fórmula de atraso não reproduz | Alta | Reduzir a capacidade dos trechos que formam o gargalo | ✅ feito |
| 2 | Validação pouco independente | Média | Não validar com dados retidos (falta de tempo); alternativas documentadas | ⏸ não será feito |
| 3 | Fator de expansão incerto | Média para alta | Contagens de julho/2026 baixadas; **todos os cenários rodam com os três fatores** | ✅ dados atualizados; regra obrigatória para os cenários |
| 4 | Predomínio do tráfego de passagem | Média (risco para a tese) | Aceito como característica da área e declarado como limitação | — |

---

## Problema 1 — Atraso no trevo que a fórmula de atraso não reproduz

### O que é

O modelo calcula o tempo de cada trecho com a fórmula do Bureau of Public Roads (BPR, 1964):

> tempo no pico = tempo com a via vazia × (1 + 0,15 × (volume ÷ capacidade)⁴)

O atraso depende só de quão cheio está o próprio trecho. Por causa da quarta potência, ele quase não aparece até o trecho chegar perto da capacidade:

| Ocupação (volume ÷ capacidade) | 60% | 80% | 100% | 120% |
|---|---|---|---|---|
| Atraso gerado pela fórmula | 2% | 6% | 15% | 31% |

Na EPCT e na DF-480, perto do trevo, os contadores do DETRAN mostram cerca de 60% de ocupação no pico. A fórmula prevê então uns 2% de atraso. Mas a TomTom mediu, em relação ao tempo de madrugada:
- **EPCT:** 36% a mais na mediana dos trechos, até 145% no trecho mais lento;
- **DF-480:** 22% a mais.

Num trecho que leva 1 minuto vazio, o modelo diria 1 minuto e 1 segundo no pico; a realidade é cerca de 1 minuto e 22 segundos.

### Por que acontece

A lentidão perto do trevo vem da fila: os carros disputam espaço na junção, trocam de faixa para entrar e sair (entrelaçamento) e esperam brecha. A fila começa no trevo e se estende para trás pela rodovia. Os trechos antes do trevo não estão cheios; estão parados porque a saída deles está travada. A fórmula olha cada trecho isoladamente e não representa uma fila que vem do trecho seguinte.

### Gravidade: alta

A EPCT é a via com o pior índice de desempenho de velocidade da área (K de 0,29 a 0,40 junto ao trevo), portanto a candidata natural a via crítica. Sem correção:
- o modelo acharia a EPCT quase livre;
- uma intervenção nela mostraria pouca melhora;
- quase nenhum motorista desviaria por rotas alternativas.

Isso esconderia justamente a redistribuição de tráfego e o Paradoxo de Braess que a pesquisa quer estudar.

### Decisão

Reduzir a capacidade dos trechos que formam o gargalo até a fórmula reproduzir o tempo observado no pico. A capacidade passa a ser a **capacidade efetiva**: a vazão que o trecho de fato escoa com o trevo travando a saída, e não a capacidade teórica de suas faixas. É uma calibração da situação atual, prática comum em modelos de alocação.

### O que foi feito exatamente (`scripts/enrich_graph.py`)

**1. Fluxo atual de cada trecho.** Só há contagem em 4 pistas, então o fluxo dos demais trechos foi estimado alocando a matriz origem-destino (fator de expansão adotado, 12,21) pelo caminho mais rápido de cada par. O "mais rápido" usa os tempos observados no pico (alocação tudo-ou-nada). A justificativa: se os tempos observados são os de equilíbrio, cada viagem está usando o caminho mais rápido sob esses tempos.

Conferência: em 40 trechos onde a caixa da TomTom mede só aquele trecho, o fluxo estimado tem correlação de 0,95 com a passagem observada e fica, na mediana, 7% abaixo dela.

**2. Critério de gargalo.** Um trecho é gargalo quando cumpre todas as condições:
- é da rodovia (classes OSM trunk, trunk_link, primary, motorway e suas alças);
- tem velocidade observada confiável (pelo menos 50% do trecho coberto por dados da TomTom);
- tem fluxo de pelo menos 30% da capacidade nominal. Abaixo disso, o atraso não vem do volume, e sim de cruzamentos e conversões; calibrar ali daria capacidades absurdas (por exemplo, 80 veículos por hora numa alça);
- o atraso observado (tempo no pico ÷ tempo de madrugada − 1) supera o atraso da fórmula em mais de 5 pontos percentuais.

As ruas internas (terciárias) ficaram de fora de propósito. Algumas têm atraso no pico, mas com pouco volume, o que indica atraso de cruzamento e não de capacidade.

**3. Capacidade efetiva.** É a capacidade que faz a fórmula devolver exatamente o tempo observado:

> capacidade efetiva = fluxo ÷ ((tempo no pico ÷ tempo de madrugada − 1) ÷ 0,15)^(1/4)

Ela nunca passa da capacidade nominal (só reduz). O script confere que, com a capacidade efetiva e o fluxo estimado, a fórmula reproduz o tempo observado em todos os gargalos.

**4. Resultado.** São 25 trechos, somando 6,1 km:
- EPCT nos dois sentidos, junto ao trevo: 14 trechos;
- DF-480 no sentido sudoeste, rumo ao trevo: 10 trechos;
- 1 alça de acesso à DF-480.

| Trecho | Rodovia, sentido | Comprimento | Fluxo estimado | Pico ÷ madrugada | Capacidade nominal → efetiva |
|---|---|---|---|---|---|
| 133→63 | EPCT, norte | 32 m | 2.024 | 2,45 | 3.600 → 1.147 (32%) |
| 63→102 | EPCT, norte | 516 m | 2.154 | 2,16 | 3.600 → 1.291 (36%) |
| 132→133 | EPCT, norte | 165 m | 2.021 | 2,11 | 3.600 → 1.225 (34%) |
| 126→60 | EPCT, norte | 175 m | 2.347 | 2,02 | 3.600 → 1.454 (40%) |
| 11→9 | EPCT, sul | 34 m | 1.946 | 1,90 | 5.400 → 1.244 (23%) |
| 64→66 | EPCT, norte | 282 m | 1.819 | 1,64 | 3.600 → 1.264 (35%) |
| 66→132 | EPCT, norte | 29 m | 2.020 | 1,58 | 3.600 → 1.439 (40%) |
| 102→126 | EPCT, norte | 54 m | 2.050 | 1,55 | 3.600 → 1.480 (41%) |
| 61→10 | EPCT, sul | 83 m | 1.843 | 1,40 | 3.600 → 1.446 (40%) |
| 9→20 | EPCT, sul | 100 m | 1.935 | 1,39 | 5.400 → 1.526 (28%) |
| 60→62 | EPCT, norte | 93 m | 2.160 | 1,33 | 3.600 → 1.778 (49%) |
| 124→64 | EPCT, norte | 86 m | 1.950 | 1,30 | 3.600 → 1.639 (46%) |
| 0→11 | EPCT, sul | 123 m | 2.078 | 1,29 | 5.400 → 1.763 (33%) |
| 65→14 | DF-480, sudoeste | 120 m | 1.400 | 1,29 | 3.600 → 1.188 (33%) |
| 7→22 | DF-480, sudoeste | 928 m | 2.413 | 1,28 | 3.600 → 2.056 (57%) |
| 14→18 | DF-480, sudoeste | 268 m | 1.248 | 1,28 | 3.600 → 1.072 (30%) |
| 4→5 | DF-480, sudoeste | 41 m | 2.064 | 1,25 | 3.600 → 1.809 (50%) |
| 6→7 | DF-480, sudoeste | 66 m | 2.009 | 1,25 | 3.600 → 1.774 (49%) |
| 18→4 | DF-480, sudoeste | 130 m | 2.144 | 1,25 | 3.600 → 1.883 (52%) |
| 20→17 | EPCT, sul | 202 m | 1.919 | 1,22 | 5.400 → 1.753 (32%) |
| 5→6 | DF-480, sudoeste | 1.795 m | 2.072 | 1,20 | 3.600 → 1.924 (53%) |
| 21→18 | Acesso DF-480 (alça) | 119 m | 889 | 1,15 | 1.200 → 894 (74%) |
| 22→23 | DF-480, sudoeste | 392 m | 2.272 | 1,15 | 3.600 → 2.256 (63%) |
| 25→0 | EPCT, sul | 208 m | 2.062 | 1,11 | 3.600 → 2.211 (61%) |
| 17→26 | EPCT, sul | 70 m | 1.956 | 1,07 | 3.600 → 2.402 (67%) |

Fluxos e capacidades em veículos por hora, por sentido. A lista completa, com os valores para os três fatores de expansão, está em `cache/gama_drive_expanded_atributos_relatorio.json`, campo `gargalos`.

**5. Campos no grafo:**

| Campo | Conteúdo |
|---|---|
| `capacidade_nominal_veic_h` | faixas × capacidade por faixa, sem calibração |
| `capacidade_veic_h` | a que o Frank-Wolfe usa: efetiva nos gargalos, nominal nos demais |
| `capacidade_veic_h_fator_min`, `capacidade_veic_h_fator_max` | idem, para os outros fatores de expansão (ver problema 3) |
| `gargalo` | verdadeiro nos 25 trechos |
| `fluxo_atual_estimado_veic_h`, `razao_t_obs_t0` | os dados usados na calibração |

**6. Dependência dos parâmetros.** A capacidade efetiva depende de α e β da fórmula e do fator de expansão:
- **Fator de expansão:** o conjunto de gargalos é fixo (definido com o fator adotado, porque é uma característica física medida pelo tempo observado). A capacidade efetiva escala na mesma proporção do fator, porque o fluxo escala. Os valores já estão gravados nos campos `_fator_min` e `_fator_max`.
- **Outros valores de α e β** (sensibilidade com 0,8 e 4,7): a capacidade efetiva precisa ser recalculada com a função `capacidade_efetiva` do `enrich_graph.py`, que recebe α e β.

### Regra para os cenários de intervenção

Ao adicionar uma faixa num trecho de gargalo, a capacidade efetiva cresce na proporção das faixas:

> capacidade nova = capacidade efetiva × (faixas + 1) ÷ faixas

Não se soma a capacidade nominal de uma faixa. A hipótese é que a faixa nova escoa na mesma proporção que as existentes. Se a fila nasce num trecho mais à frente, a faixa extra antes dele ajuda menos do que isso: a regra é otimista e isso deve ser declarado.

### Limitações que ficam

- O fluxo dos trechos sem contagem é estimado. A estimativa vem da própria matriz, conferida contra as passagens da TomTom.
- A capacidade efetiva absorve todo o atraso do trevo: fila, entrelaçamento, conversões. A fórmula continua sem representar a fila se propagando. Se um cenário mudar muito o fluxo que chega ao trevo, o modelo pode errar a extensão da fila.
- Os trechos curtos (menos de 50 m) têm tempo medido mais ruidoso. O peso deles no tempo total é pequeno.

---

## Problema 2 — Validação pouco independente

### O que é

- **Calibrar** é ajustar o modelo usando dados reais.
- **Validar** é conferir se o modelo acerta dados reais que **não** usou no ajuste.

Se a conferência usa os mesmos dados do ajuste, ela passa por construção.

### Onde acontece

| Dado | Uso na montagem do modelo | O que uma comparação com ele prova |
|---|---|---|
| Contagens do DETRAN (4 pistas) | calculam o fator de expansão | quase nada: o volume nessas pistas bate por construção |
| Passagens nas caixas da TomTom | são as mesmas viagens que formam a matriz | que o modelo escolhe as rotas que os motoristas escolheram; não testa a quantidade total de carros |
| Tempo de pico da TomTom | define a capacidade efetiva dos 25 gargalos (problema 1) e o tempo livre de 76 trechos (onde a madrugada saiu mais lenta que o pico) | só é independente nos demais trechos |

### Gravidade: média

Não quebra o modelo, mas limita o que se pode afirmar. O artigo não pode dizer que o modelo foi "validado" de forma ampla.

### Decisão: não será feito (falta de tempo)

Nenhuma validação com dados retidos será feita. O artigo deve declarar o que foi usado para calibrar e o que foi usado para conferir, e tratar a comparação com as passagens como teste de escolha de rota, não de demanda.

### Alternativas documentadas, para trabalhos futuros

1. **Deixar um contador de fora:** calibrar o fator com 3 pistas e conferir o volume na quarta, repetindo para cada uma (validação cruzada).
2. **Validar pelo tempo nos trechos não calibrados:** comparar o tempo do modelo com o tempo observado só nos trechos que não são gargalo nem tiveram o tempo livre tirado do pico.
3. **Dados de outro mês:** calibrar com julho e conferir os volumes e tempos de outro mês (por exemplo, agosto/2026, com uma nova consulta à TomTom).
4. **Contagens manuais** em cruzamentos da malha interna, onde não há contador.

---

## Problema 3 — Fator de expansão incerto

### O que é

A TomTom só enxerga os carros com aparelhos ou aplicativos que enviam dados para ela: uma amostra. O fator de expansão converte viagens da amostra em carros reais, comparando a amostra com os contadores do DETRAN no mesmo ponto e horário.

### O que foi feito

As contagens de **julho de 2026**, o mesmo mês da TomTom, estão publicadas no portal de dados abertos do DF: conjunto "Dados de Fluxo Veicular", do DER-DF, atualizado em 03/09/2026. O arquivo foi baixado em 15/10/2026 e substituiu o de abril. O de abril ficou guardado como `flow_abril_2026.csv`, fora do git. A matriz foi recalculada:

| Pista | Sentido | DETRAN julho (veíc/h, 18h) | Dias úteis válidos | TomTom (viagens/h) | Fator | Fator com abril |
|---|---|---|---|---|---|---|
| DF-001 001EDF0250 | decrescente | 2.265 | 23 | 103,1 (1 caixa) | 21,96 | 20,81 |
| DF-001 001EDF0270 | crescente | 1.626 | **1** | 184,4 (8 caixas) | 8,82 | 8,18 |
| DF-480 480EDF0030 | crescente | 1.421 | 21 | 140,9 (3 caixas) | 10,08 | 10,68 |
| DF-480 480EDF0030 | decrescente | 2.530 | 21 | 176,3 (7 caixas) | 14,35 | 13,75 |

- **Fator adotado:** 12,21, a mediana das 4 pistas (era 12,21 com abril).
- **Demanda total:** 8.309 veículos por hora em 1.031 pares.
- **Defasagem:** os volumes de julho ficaram entre 6% abaixo e 8% acima dos de abril, então a defasagem de meses não era a fonte principal da incerteza.
- **Ressalva:** a pista 001EDF0270 crescente tem só 1 dia útil completo em julho (eram 10 em abril).

### O que continua incerto

Mesmo com o mês certo, **o fator varia 2,5 vezes entre as pistas: de 8,82 a 21,96**:
- uma das pistas tem uma única caixa, e outra um único dia de contagem;
- a penetração da TomTom muda de lugar para lugar, conforme o tipo de veículo e de viagem;
- um único fator é aplicado a todos os pares de origem e destino.

Não há como saber qual valor é o certo para a área inteira.

### Gravidade: média para alta

O fator multiplica toda a demanda:

| Fator | Demanda em relação à adotada |
|---|---|
| 8,82 | 28% menor |
| 21,96 | 80% maior |

Por causa da quarta potência da fórmula de atraso, dobrar o volume multiplica o atraso por 16. O nível de demanda muda o comportamento da rede, não só os números:
- com demanda baixa, quase nada congestiona e ninguém desvia;
- com demanda alta, aparecem desvios e, possivelmente, o Paradoxo de Braess.

Uma conclusão tirada com um único fator pode simplesmente não valer se a demanda real for outra.

### ⚠️ Decisão obrigatória: todos os cenários rodam com os três fatores

**Toda simulação, a situação atual e cada cenário de intervenção, deve ser rodada três vezes:**

| Rodada | Fator de expansão | Demanda (veíc/h) | Capacidade a usar |
|---|---|---|---|
| Demanda baixa | 8,82 | 6.000 | `capacidade_veic_h_fator_min` |
| **Demanda adotada** | **12,21** | **8.309** | `capacidade_veic_h` |
| Demanda alta | 21,96 | 14.940 | `capacidade_veic_h_fator_max` |

A demanda de cada rodada é `veic_h × (fator ÷ 12,21)` de cada par da matriz.

**Por que é obrigatório:**
1. Não sabemos qual fator é o verdadeiro. Os três são igualmente defensáveis pelos dados.
2. O efeito de uma intervenção depende do nível de demanda: a mesma faixa extra pode ser inútil com pouca demanda e decisiva com muita; o Paradoxo de Braess costuma aparecer só em certas faixas de demanda.
3. Assim, cada conclusão do artigo vem acompanhada do seu grau de robustez:
   - **robusta:** vale nos três níveis;
   - **dependente da demanda:** vale só em parte deles, e o artigo diz em quais;
   - **não sustentada:** muda de sinal entre os níveis.
4. Cada rodada usa a capacidade efetiva calibrada para aquele fator (problema 1). Cada uma representa uma hipótese coerente sobre o mundo real, que reproduz os tempos observados com aquela demanda.

Rodar só com 12,21 e apresentar o resultado como certo seria esconder a principal incerteza do modelo.

**Observação depois das primeiras rodadas (21/10).** Como a capacidade efetiva dos gargalos escala com o fator, os três níveis têm a mesma razão V/C nos 25 gargalos. Intervenções nesses trechos tendem a dar quase a mesma variação percentual nos três níveis; no cenário de exemplo, o TSTT caiu 8,59%, 8,57% e 8,32%. A incerteza do fator pesa de verdade nas arestas não calibradas. Uma conclusão "robusta" sobre um gargalo é, em parte, robusta por construção, e o artigo deve dizer isso.

---

## Problema 4 — Predomínio do tráfego de passagem

### O que é

Das 15.429 viagens registradas pela TomTom, **86% só atravessam a área**: entram por uma ponta da rodovia e saem pela outra, sem começar nem terminar ali dentro. Para elas, normalmente há um único caminho razoável, que é seguir na rodovia. Só **46,5% da demanda** tem uma rota alternativa de verdade: outro caminho até 30% mais longo, sem compartilhar a maior parte dos trechos. A primeira versão deste documento dizia 40%, valor calculado com a matriz preliminar "Gama 3"; foi recalculado com a matriz final em 21/10/2026.

### Por que importa

A pesquisa quer observar redistribuição: mexer numa via e ver os motoristas mudarem de caminho, às vezes piorando o sistema (Paradoxo de Braess). Para isso eles precisam ter para onde ir. Com a maioria sem alternativa, uma intervenção pode mudar pouco o resto da rede.

### Gravidade: média, para a pergunta de pesquisa

Não é um erro do modelo; é uma característica da área. O risco é o resultado ser "quase nada muda". Isso também é um resultado legítimo e publicável: em áreas dominadas por tráfego de passagem, intervenções locais geram pouca redistribuição.

### Decisão

Aceito como característica da área e declarado como limitação no artigo. Para aproveitar ao máximo a parte da demanda que tem escolha, os cenários devem incluir:
- intervenções na malha interna (Ponte Alta Norte e alças), onde está a parte da demanda com alternativa;
- fechamentos ou restrições de trechos, que forçam desvio;
- a rodada de demanda alta (fator 21,96, obrigatória pelo problema 3), onde desvios ficam mais atraentes.
