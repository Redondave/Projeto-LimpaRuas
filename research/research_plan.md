# Plano de Pesquisa — Otimização do Coeficiente de Congestionamento na Malha Viária de Brasília

## Pergunta de Pesquisa (RQ)

Dado um conjunto de vias representado como grafo, quais intervenções na infraestrutura conseguem aumentar o índice de desempenho de velocidade ($K = \text{SPI} = V_{med}/V_{max}$) em uma determinada via crítica, e como essas intervenções afetam o Tempo Total de Viagem (TSTT) e a redistribuição de tráfego na rede sistêmica (efeito Braess/propagação)?

## Objetivos de pesquisa

### Objetivo geral

1. Desenvolver um modelo de otimização baseado em grafos para identificar intervenções capazes de aumentar o índice de desempenho (K) de vias críticas de uma região de Brasília-DF, minimizando simultaneamente o Tempo Total de Viagem (TSTT) sobre as demais vias da rede e avaliando o trade-off entre a métrica local e a eficiência sistêmica.

### Objetivos específicos

1. Identificar os principais fatores físicos, operacionais e topológicos que influenciam o desempenho das vias e o SPI.
2. Avaliar a adequação do índice de desempenho de velocidade ($K = V_{med}/V_{max}$) como métrica de fluidez de vias e sua relação com outras métricas de tráfego sistêmicas.
3. Modelar a região de estudo em Brasília como um grafo, adotando o OpenStreetMap (OSMnx) como fonte topológica primária e integrando atributos de fluxo e capacidade via junção espacial (spatial join) com os dados do DER-DF.
4. Analisar os efeitos de intervenções realizadas em uma via sobre as demais vias da rede, considerando redistribuição de fluxo e possíveis efeitos de propagação do congestionamento (avaliação do Paradoxo de Braess).

### Fatores de influência na via que podemos (ou não) considerar

- Vmax
- Vmed
- Fluxo
- N° de faixas
- N° de vias em cada
- largura das faixas
- comprimento da via
- comprimento dos segmentos
- largura da pista
- número de entradas/saídas

## Termos

*Vou listar aqui para servir de referência rápida para revisão de literatura e posterior pesquisa.*

- **DNDP**: Discrete Network Design Problem/Problema de Projeto de Rede Discreto, é o problema principal do nosso projeto! (Modelagem e Análise de sensibilidade do SPI a alterações topológicas discretas — KRL título pika)
  - **NSGA-II**: Non-dominated Sorting Genetic Algorithm II/Algoritmo Genético de Ordenação Não Dominada II
  - **Frank-Wolfe**: algoritmo que vai simular os motoristas até o equilíbrio de Wardrop dada uma mudança na via
- **VDF**: Volume-Delay Function/Função Volume-Atraso, formulada pelo Bureau of Public Roads, BPR
- **OSMnx**: gera grafo OSMnx/NetworkX a partir do OpenStreetMap (OSM)
- **Equilíbrio do Usuário de Wardrop**: conceito da teoria dos jogos, o equilíbrio é atingido quando nenhum motorista (usuário) consegue reduzir seu tempo de viagem mudando de rota por conta própria
- **TSTT**: Total System Travel Time/Tempo Total de Viagem do Sistema, representa a soma do tempo de viagem de todos os utilizadores numa rede ou grafo
- **Matriz Origem-Destino**: linhas são os vértices de origem e colunas os de destino, os valores das células são a quantidade de veículos fazendo aquele trajeto

## Explicações mais aprofundadas dos termos

### DNDP

Modelo matemático de otimização utilizado no planejamento de transportes para decidir quais alterações estruturais devem ser feitas em uma malha viária para melhorar o fluxo, respeitando um orçamento limitado (exatamente nosso problema, tirando o orçamento).

A palavra "discreto" significa que as escolhas são inteiras ou binárias: você adiciona uma faixa inteira ou não adiciona (não existe "meia faixa"); você converte a via para mão única ou a mantém dupla.

Ele tem uma estrutura binível, isto é: existem dois tomadores de decisão agindo simultaneamente, com objetivos diferentes e interdependentes:

- **Nível Superior** (o planejador da via) - objetivo: minimizar o custo total do sistema, o tempo total de viagem de todos os carros.
- **Nível Inferior** (o usuário/motorista) - objetivo: reagir às mudanças de forma a otimizar seu próprio tempo de viagem.

O planejador tenta melhorar o trânsito, mas quem de fato dita o trânsito são os motoristas. Isso dá a nossa metodologia (alteração → simulação até equilíbrio → mensurar impacto → alteração → ...).

Ele também é NP-Difícil no nível superior, mas não no inferior. Teríamos que manter o grafo reduzido se não fosse por:

- **No Nível Superior (NSGA-II)**: Como é impossível calcular todas as trilhões de combinações viárias, você usa um Algoritmo Genético (o NSGA-II é o mais famoso para múltiplos objetivos). Ele cria uma "população" inicial aleatória de projetos viários. As configurações que dão o melhor resultado sobrevivem e "cruzam" entre si, gerando novas configurações viárias cada vez melhores, sem precisar testar todas as possibilidades. **Entretanto, podemos ser nós mesmos os planejadores, sem necessidade disso.**
- **No Nível Inferior (Frank-Wolfe)**: O algoritmo genético é cego; não sabe calcular trânsito. Para cada "mutação" que o NSGA-II (ou que a gente) sugere no Nível Superior (ex: "e se a W3 virar mão única?"), ele passa esse novo grafo para o algoritmo de Frank-Wolfe. O Frank-Wolfe é um método determinístico de otimização convexa que resolve matematicamente o Equilíbrio de Wardrop. Ele simula como os motoristas se comportariam naquela malha específica, calcula o Tempo Total de Viagem e devolve a "nota" desse cenário de volta para o NSGA-II evoluir.

### VDF

```
t = t0 [1 + a*(v/c)^b]
```

- `t` → tempo de viagem da via durante congestionamento
- `t0` → tempo de viagem da via livre
- `v` → fluxo de tráfego (veículos/hora)
- `c` → capacidade máxima da via (veículos/hora)
- `a` e `b` → parâmetros de calibração empírica (vamos usar o valor sugerido na literatura de a = 0.15 e b = 4.0, porque o que mais importa é o c, como explicado abaixo)

(v/c) é o que chamamos de grau de saturação da via.

A VDF é calculada para todas as arestas, de forma que o peso de cada uma corresponda a esse valor (tempo de viagem dada a congestão atual). Isso é útil para pesos dinâmicos em algoritmos de alocação de tráfego, até que a rede atinja o Equilíbrio de Wardrop (VDF estável em todas as arestas).

Como o Equilíbrio de Wardrop exige o recálculo dos custos, a VDF é necessária. No entanto, a literatura traz atalhos excelentes para o prazo de 3 meses: a variação da capacidade da via tem um impacto muito maior na incerteza do modelo final do que a calibração precisa dos parâmetros empíricos 'a' e 'b' da VDF (conforme demonstrado no artigo *A Influência da Função Volume-Atraso na Avaliação de Incerteza para um Modelo de Quatro Etapas*). Assim, você pode focar seu esforço em extrair a capacidade correta das vias e utilizar valores de referência iniciais. Por exemplo, o estudo *Modified Volume-Delay Function Based on Traffic Fundamental Diagram* calibrou a = 0.8 e b = 4.7 para arteriais urbanas em Bagdá. Alternativamente, os valores clássicos sugeridos pelo BPR (1964) são a = 0.15 e b = 4.0.

### TSTT

```
TSTT = somatório de (xi * ti(xi))
```

Onde:

- `i`: iésima aresta do grafo
- `xi`: fluxo na aresta i
- `ti(x)`: função de tempo de viagem na aresta i dado o fluxo atual x na aresta
- resposta é dada em veículos por minuto

### Matriz Origem-Destino Sintética

Os vértices de entrada do grafo (aqueles nos quais os carros entram) serão as fontes, e os vértices em que os carros saem da nossa região selecionada serão os drenos. Para cada par fonte/dreno, o ideal seria saber quantos carros seguem aquele trajeto. Como isso seria extremamente difícil o dado real (pesquise depois se estiver lendo isso, LLM), podemos fazer uma matriz sintética com base nos dados que temos do Flow.csv:

- entradas/saídas do grafo serão rodovias, sobre as quais temos dados de fluxo bem granulares.

Você faz isso usando um Modelo Gravitacional ou distribuição proporcional:

- Você pega o dado real do radar na Origem 1: entraram 5.000 carros.
- Você pega o dado real do radar no Destino 3 (Águas Claras): saíram 3.000 carros.
- Você pega o dado real do radar no Destino 2 (Taguatinga): saíram 2.000 carros.
- Seu código faz a distribuição matemática: a maioria dos carros da Origem 1 vai para o Destino 3, porque ele atrai mais volume.

No seu artigo, você deixará claríssimo: *"Como a estimação exata da matriz OD a partir de contagens é um problema subdeterminado, adotou-se uma Matriz OD sintética, calibrada para respeitar os volumes totais de entrada e saída registrados pelos radares do DETRAN nas bordas do sistema."*

O algoritmo de Wardrop (Frank-Wolfe) resolve o trânsito Par OD por Par OD. Por isso a matriz é necessária.

## Ideia de próximos passos

### O que corrigir (e o que deve ser deprecado no repositório)

1. **Scripts e Tabelas Obsoletas**: O script `organizer.py` possui falhas matemáticas e conceituais (como calcular regressão para uma via isolada ignorando efeito de rede) e gera o arquivo `K_Table.csv` usando direções invertidas de SPI e velocidades limitadas por marginais. **Ação imediata:** Apagar ou marcar `organizer.py` e `K_Table.csv` como `deprecated` no repositório para evitar uso acidental no futuro.
2. **Definição da Região de Estudo**: Em vez de usar a malha inteira do DF com buracos de dados, selecionar um polígono reduzido (ex: ligação Águas Claras, Taguatinga e EPTG, com ~30 nós). Isso viabiliza o algoritmo de Wardrop (que tem alta complexidade temporal) e garante que o grafo operará apenas com vias bem documentadas.
Também temos que tentar, em vez de só usar rodovias, pegar uma região menor do DF. Essa sugestão é pq o wardrop é demorado e por causa das limitações que surgem se modelarmos só com rodovias (pontuado no último trecho do documento, tópico 2.)
3. **Consistência do Método**: Como os passos de coleta de dados foram reestruturados nas seções acima (usando OSMnx, TomTom com múltiplas chamadas e matriz OD sintética pelas bordas), o foco passa a ser construir a simulação com a certeza de que a matriz OD é viável e de que a fórmula do coeficiente $K$ ($V_{max}/V_{med}$) é constante em toda a pesquisa.

### Quais dados coletar (e de onde coletar)

Para que o modelo rode perfeitamente, você precisará construir um "dicionário de atributos" para cada via (aresta) e calibrar a rede.

**1. Dados Topológicos e Físicos (Fontes: OSMnx e DER-DF)**

Para a topologia definitiva do grafo, usaremos o **OSMnx** como, garantindo maior rigor. Após extrair a malha de interesse via OSMnx, faremos um **join espacial (nearest-edge matching)** para injetar as informações do DER-DF nas arestas do OpenStreetMap correspondentes.

Os atributos de cada aresta devem incluir:
- Comprimento ($L$): O tamanho físico do segmento (atributo `length` do OSMnx).
- Velocidade de Fluxo Livre ($V_0$): O limite de velocidade da via. Será priorizado o atributo `maxspeed` do OSMnx, já que a base `Speeds.csv` do DER-DF fornece a velocidade no radar (incluindo marginais lentas a 40 km/h), o que distorceria o K para baixo indevidamente.
- Tempo de Fluxo Livre ($t_0$): Custo básico da aresta sem trânsito ($L / V_0$).
- Tipo de Via (`highway`): Classificação hierárquica (ex: motorway, primary, residential).
- Número de Faixas (`lanes`): Quantas pistas a rua tem.
- Heurística de limpeza: O OSM frequentemente não tem o atributo `lanes` para vias menores. Você precisará de uma regra (ex: se `primary` e NaN, assuma 2; se `residential`, assuma 1). **Auditoria obrigatória:** verificar qual a cobertura real do OSM no DF antes de aplicar a regra e relatar essa dependência no artigo como uma limitação quantificada.

*Nota de Proveniência para Artigo:* A origem de `Roads.csv` e `Speeds.csv` deve ser formalizada no artigo com agência, nome do dataset, link de acesso e licença, tal qual feito com o Flow.csv.

**2. Dados de Capacidade Teórica (Fonte: Manual de Capacidade do DNIT)**

A capacidade deve ser calculada: Capacidade Total ($c$) = Número de Faixas $\times$ Capacidade por Faixa.
Em vez do manual americano, usaremos valores típicos da literatura brasileira (Manuais do DNIT ou extinto GEIPOT) para as faixas:
- Vias Expressas: ~1.800 a 2.000 veículos/hora/faixa.
- Arteriais Principais: ~1.000 a 1.200 veículos/hora/faixa.
- Secundárias e Locais: ~500 a 900 veículos/hora/faixa.

**3. Dados de Velocidade Real (Fonte: API da TomTom)**

- Velocidade Média Empírica ($V_{med}$): Velocidade real por GPS no horário de pico.
- **Correção da Coleta:** A coleta no feriado de 7/9 mediu ruas vazias. Faremos um polling repetido em **3 a 5 dias úteis no horário de pico**, usando a mediana/IC das leituras, ou, alternativamente, usaremos o produto **Traffic Stats** da TomTom, caso o grupo tenha acesso, para obter o histórico médio daquele horário.
- Tratamento explícito de compartilhamento: A metodologia descreverá a métrica de `tomtom_compartilhado` explicitamente (segmentos longos no zoom 10 cobrindo múltiplos trechos DER) como limitação da agregação, não sendo apenas uma flag no CSV.
- $K$ Inicial: Índice de desempenho calculado pela fórmula **$K = V_{med} / V_0$** ($V_{med}/V_{max}$). Ele será usado no Passo 1 como mapa de calor para achar os doentes (gargalos onde o K é criticamente baixo).

**4. Volumes de Tráfego Empíricos e o Desafio da Matriz OD**

As bases `Flow.csv` e `Roads.csv` contemplam exclusivamente as rodovias distritais/federais. Ao reduzir o grafo para uma sub-região (ex. Águas Claras - Taguatinga - EPTG), muitos nós de **borda** (entradas e saídas de bairro) serão vias arteriais, coletoras ou locais, nas quais não existem radares do DETRAN e, logo, não terão dados nessas planilhas.
Como o Wardrop precisa de fluxo OD entrando/saindo por esses nós de borda, adotaremos ou combinaremos as seguintes abordagens rigorosas para estimativa e obtenção de dados:

- **Solução 1: Restrição Topológica.** Selecionaremos intencionalmente a sub-região de modo que todas as suas fronteiras coincidam com os postos de radar em rodovias do DETRAN (ex: fechando o polígono na EPTG e EPVP). A limitação a ser assumida é a perda de fluxos residuais de ruas locais marginais.
- **Solução 2: Estimativa Baseada no Plano Diretor de Transporte Urbano (PDTU/DF).** Essa é uma alternativa cientificamente rigorosa de estimativa de demanda. O PDTU-DF contém a matriz OD macroscópica oficial baseada em pesquisas domiciliares e dados de mobilidade celular. Podemos extrair a sub-matriz específica para as Zonas de Tráfego (ZTs) da nossa região de estudo e associá-las aos nós de borda, servindo de fundação validada empiricamente para o nosso modelo gravitacional ou substituição direta.
- **Solução 3: Aquisição de Dados Reais de Terceiros (Contagens O/D).** Para obter os fluxos reais nas ruas menores e vias locais que faltam no DER, existem fontes alternativas empiricamente rigorosas e citáveis:
  - *TomTom O/D Analysis & Junction Analytics:* Como o grupo já utiliza a API da TomTom, pode-se solicitar acesso de pesquisa ao portal *TomTom Move*. Ele fornece matrizes OD e *probe counts* baseados em bilhões de trilhas de GPS e celulares, abrangendo ruas de qualquer hierarquia, não apenas rodovias.
  - *StreetLight Data / Google Maps Mobility:* Plataformas especializadas em métricas de trânsito baseadas em LBS (Location-Based Services), que extraem matrizes OD em microescala (vias de bairro).
  - *Waze for Cities Data:* Programa parceiro gratuito para órgãos de trânsito e universidades que expõe volumes de veículos e relatórios de fluxo em vias locais.

No artigo, formalizaremos que: *"Devido à cobertura das contagens de radar concentrar-se nas rodovias, adotou-se uma Matriz OD sintética, calibrada rigorosamente via dados macroscópicos (PDTU) ou dados empíricos de LBS (Location-Based Services) para suprir as demandas das vias coletoras de borda."*

### O que evoluir (lista de afazeres + ideia do fluxo completo do projeto)

Aqui está o encadeamento de como as entradas se transformam em saídas até responder à sua pergunta de pesquisa.

**Passo 1: Escolha da Região de Estudo baseada no $K$ (Diagnóstico Macro)**

- Input: Dados brutos da TomTom e limites de velocidade gerais do DF.
- Ação: Antes de baixar o grafo final, faça uma análise macro e calcule o $K$ empírico de grandes corredores. Localize uma mancha onde o $K$ é criticamente baixo (muito engarrafamento).
- Output: Definição de um polígono contendo de 10 a 30 interseções ao redor desse gargalo (ex: a transição entre EPTG e a entrada de Águas Claras).

**Passo 2: Construção da Rede e Preparação (O "Mundo Real")**

- Input: O polígono definido no Passo 1.
- Ação: Use o OSMnx para baixar o grafo viário de locomoção padrão (drive), garantindo que ruas secundárias venham junto. Aplique a limpeza de dados e injete os atributos da Parte 1 ($L$, $V_0$, $t_0$, $c$) em todas as arestas.
- Output: Um grafo (MultiDiGraph) perfeitamente ponderado, quase pronto para a simulação, onde sabemos exatamente onde estão as vias críticas iniciais.

**Passo 3: Geração da Matriz Origem-Destino Sintética (Fontes e Drenos)**

Conceito: O algoritmo não sabe para onde os carros querem ir. Você precisa dizer a ele. Para isso, você escolhe nós nas bordas da sua sub-rede para servirem de "Fontes" e "Drenos".

- Fonte (Source): Um nó de borda onde os veículos entram na simulação.
- Dreno (Sink): Um nó de borda onde os veículos saem da simulação.

- Ação: Usando as soluções estipuladas na seção anterior (Contagens diretas, proxy de TMD ou modelo gravitacional), você define a Matriz OD. Exemplo: "Injetar 4.000 carros saindo do nó da EPTG (Fonte A) com destino ao nó de entrada de Águas Claras (Dreno B)".
- Output: A matriz matemática de demanda na qual faremos mudanças topológicas que alimentarão o simulador.

**Passo 4: Simulação da Linha de Base (Wardrop + VDF)**

- Input: O Grafo alterado (Passo 2) + A Matriz OD (Passo 3).
- Ação: Você roda o algoritmo de alocação de Frank-Wolfe. Ele pega os carros da Matriz OD e tenta achar o caminho mais rápido para eles. Conforme os carros entram nas arestas, o volume simulado ($v$) sobe. O algoritmo usa a Função BPR (com o $c$ e $t_0$ da aresta) para aumentar o peso da via dinamicamente. Os próximos carros são forçados a desviar pelas ruas secundárias. O algoritmo roda até o Equilíbrio de Wardrop (nenhum carro consegue um caminho melhor).
- Output 1: O volume simulado ($v$) e o tempo final simulado ($t$) de cada rua.
- Output 2: O Tempo Total de Viagem do sistema (a soma do tempo de todos os veículos).

**Passo 5: Intervenção Estrutural (Otimização Topológica)**

- Input: A lista de vias com $K$ ruim mapeadas no Passo 1.
- Ação: Você atua como o planejador urbano. Crie cópias do seu grafo e faça alterações manuais (podendo no futuro serem automatizadas por NSGA-II).
  - Cenário A: Adicionar 1 faixa numa via secundária (você vai no código e aumenta o atributo $c$ dela).
  - Cenário B: Alterar o sentido de uma rua (você inverte a direção da aresta no NetworkX).
- Output: Uma bateria de 15 a 30 grafos com infraestruturas diferentes. Você repete o Passo 4 (Frank-Wolfe) para cada um deles e anota o novo Tempo Total de Viagem de cada cenário.

**Passo 6: Avaliação e Resposta às Perguntas de Pesquisa**

- Input: O volume ($v$) e o tempo ($t$) gerados pelos cenários do Passo 5.
- Ação: Com o novo tempo $t$ estabilizado na Função BPR, você sabe o novo tempo de viagem da via. Dividindo o comprimento $L$ pelo tempo $t$, você obtém a nova Velocidade Média teórica.
- Output final (Recalculando os Ks): Você calcula o novo índice de desempenho de velocidade ($K = V_{med}/V_{max}$) da via alterada e das vias vizinhas.

**Observação final (a grande tese do trabalho)**

O papel do $K$ é servir como sua bússola clínica. Você usa o $K$ empírico inicial para mapear a área e escolher onde aplicar a intervenção. Após simular o equilíbrio de Wardrop com a intervenção, você recalcula todos os $K$s teóricos da rede. A conclusão central é provar ou investigar que, em certos cenários, aumentar o $K$ (fluidez) de uma rua específica pode deflagrar um Paradoxo de Braess ou efeito de propagação, piorando o Tempo Total de Viagem (TSTT) da malha sistêmica, evidenciando que intervenções viárias pautadas apenas por métricas locais falham se não considerarem o efeito em rede.

**Validação do algoritmo**

> Uma sugestão adicional na mesma linha: antes de rodar Frank-Wolfe nos dados reais do DF, validem a implementação de vocês contra a rede de Sioux Falls — que já está nos dados de um dos 4 artigos do corpus de vocês (o de centralidade + demanda). É um benchmark padrão da literatura de alocação de tráfego, tem solução de equilíbrio conhecida publicada, e dá a vocês uma seção de "validação do simulador" praticamente de graça — o tipo de coisa que separa "fizemos um script" de "fizemos um experimento computacional".

### Como isso responde às perguntas de pesquisa

1. **Fatores que influenciam o desempenho (Obj. 1)**: Isso é resolvido pela Função Volume-Atraso (VDF). Ao modelar a via, você imputa atributos físicos (número de faixas, que define a capacidade $c$) e operacionais (velocidade máxima regulamentada). O modelo provará matematicamente como a capacidade física estrangula o fluxo e gera o atraso.
2. **Avaliação da métrica K (Obj. 2)**: A sua simulação com Wardrop vai calcular um novo volume $v$ para cada aresta após uma intervenção. Injetando esse $v$ na VDF, você obtém o novo tempo de viagem $t$. Dividindo o tamanho da aresta por $t$, você descobre a nova $V_{med}$ teórica. Assim, você consegue calcular o novo coeficiente $K$ da via. Você responderá à pergunta de pesquisa analisando se otimizar o $K$ de uma via isolada melhora ou piora os outros Ks ou o *Tempo Total de Viagem* (outra métrica de tráfego) do sistema inteiro.
3. **Modelagem em Grafo (Obj. 3)**: Resolvido com OSMnx e NetworkX. Os pesos das arestas não serão estáticos, mas sim dinâmicos, definidos pela VDF baseada no fluxo da iteração atual do algoritmo.
4. **Efeitos de propagação e redistribuição (Obj. 4)**: Essa é a definição exata do Equilíbrio de Wardrop. Se você alargar uma via, a resistência dela cai. O algoritmo recalcula as rotas, os "motoristas virtuais" mudam de caminho para aproveitar a via melhorada, o volume dela sobe, o das vias adjacentes desce, e o congestionamento se redistribui até atingir um novo equilíbrio.

### Justificativas para o artigo a ser escrito

1. Podemos justificar o uso do SPI pela literatura, e o não uso de métricas de centralidade como opção de otimização também.
2. Devemos justificar porque só o grafo rodoviário (porque não temos dados suficientes para maiores análises) e reconhecer as limitações do modelo (ex: carros do modelo nunca saem de rodovias para vias menores, não simula comportamento real de motorista que corta caminho por ruas menores, difícil de modelar sumidouro e fonte para Wardrop, etc.).
3. Devemos fornecer as fontes de dados que usamos (garantir reprodutibilidade), em uma listagem de tudo que usamos (csvs, apis etc.), bem como documentar de onde tiramos.

---

## Fontes citadas neste documento

*Referências completas para os trabalhos mencionados apenas pelo nome ao longo do texto acima. Algumas já estavam informalmente no `articles.md` do grupo (link e notas, sem citação completa); outras são adicionadas aqui porque fundamentam diretamente um método citado no texto e ainda não tinham entrada própria em lugar nenhum. Confiram e completem no Mendeley do grupo.*

- **BPR / Função Volume-Atraso**: U.S. Bureau of Public Roads (1964). *Traffic Assignment Manual*. U.S. Department of Commerce, Urban Planning Division, Washington, D.C.
- **Equilíbrio do Usuário de Wardrop (conceito original)**: Wardrop, J.G. (1952). "Some Theoretical Aspects of Road Traffic Research." *Proceedings of the Institution of Civil Engineers*, Part II, 1(3), 325–378.
- **Primeira formalização matemática rigorosa do equilíbrio de Wardrop**: Beckmann, M.J., McGuire, C.B., & Winsten, C.B. (1956). *Studies in the Economics of Transportation*. Yale University Press, New Haven.
- **Algoritmo de Frank-Wolfe (origem)**: Frank, M., & Wolfe, P. (1956). "An Algorithm for Quadratic Programming." *Naval Research Logistics Quarterly*, 3(1–2), 95–110.
- **Frank-Wolfe aplicado à alocação de tráfego/equilíbrio de Wardrop**: LeBlanc, L.J., Morlok, E.K., & Pierskalla, W.P. (1975). "An Efficient Approach to Solving the Road Network Equilibrium Traffic Assignment Problem." *Transportation Research*, 9(5), 309–318.
- **DNDP (formulação original do problema)**: LeBlanc, L.J. (1975). "An Algorithm for the Discrete Network Design Problem." *Transportation Science*, 9(3), 183–199.
- **NSGA-II (origem)**: Deb, K., Pratap, A., Agarwal, S., & Meyarivan, T. (2002). "A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II." *IEEE Transactions on Evolutionary Computation*, 6(2), 182–197.
- **Matriz OD sintética / estimação a partir de contagens**: Van Zuylen, H.J., & Willumsen, L.G. (1980). "The Most Likely Trip Matrix Estimated from Traffic Counts." *Transportation Research Part B: Methodological*, 14(3), 281–293.
- **Matriz OD sintética / levantamento da literatura**: Abrahamsson, T. (1998). *Estimation of Origin-Destination Matrices Using Traffic Counts — A Literature Survey*. IIASA Interim Report IR-98-021, Laxenburg, Áustria.
- **Paradoxo de Braess (artigo original, em alemão)**: Braess, D. (1968). "Über ein Paradoxon aus der Verkehrsplanung." *Unternehmensforschung*, 12, 258–268.
- **Paradoxo de Braess (tradução para o inglês)**: Braess, D., Nagurney, A., & Wakolbinger, T. (2005). "On a Paradox of Traffic Planning." *Transportation Science*, 39(4), 446–450.
- **Highway Capacity Manual**: Transportation Research Board (2016). *Highway Capacity Manual: A Guide for Multimodal Mobility Analysis*, 6ª edição. National Academies of Sciences, Engineering, and Medicine, Washington, D.C.
- **SPI (Speed Performance Index)**: He, F., Yan, X., Liu, Y., & Ma, L. (2016). "A Traffic Congestion Assessment Method for Urban Road Networks Based on Speed Performance Index." *Procedia Engineering*, 137, 425–433.
- **VDF calibrada para arteriais urbanas em Bagdá (a = 0,8 / b = 4,7)**: "Modified Volume-Delay Function Based on Traffic Fundamental Diagram: A Practical Calibration Framework for Estimating Congested and Uncongested Conditions." *Journal of Transportation Engineering, Part A: Systems*, 149(11), 2023. (Autoria não confirmada nesta busca — completar no Mendeley do grupo.)
- **Influência da VDF na incerteza de modelos de quatro etapas**: "A Influência da Função Volume-Atraso na Avaliação de Incerteza para um Modelo de Quatro Etapas" (link já presente no `articles.md` do grupo; autoria não confirmada nesta busca — completar no Mendeley do grupo.)