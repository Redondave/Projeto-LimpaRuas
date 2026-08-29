# Artigos

## Sobre o K (speed performance index):

- **Nome:** Um Método de Avaliação de Congestionamento de Tráfego para Redes Viárias Urbanas Baseado no Índice de Desempenho de Velocidade [He et al. (2016)]
- **Link** [clique aqui](https://www.researchgate.net/publication/294139458_A_Traffic_Congestion_Assessment_Method_for_Urban_Road_Networks_Based_on_Speed_Performance_Index)
- **Notas:** podemos usar isso para basear as nossas métricas de congestionamento

---

## Sobre construção do grafo (OSMnx):

- **Nome:** OSMnx: Novos métodos para adquirir, construir, analisar e visualizar redes viárias complexas [Boeing (2017)]
- **Link:** [clique aqui](https://github.com/gboeing/osmnx)
- **Notas:** ferramenta em python que baixa dados do OSM (OpenStreetMap) e constrói grafos NetworkX com topologia já simplificada e corrigida — nós representam apenas interseções e fins de via. Resolve automaticamente o problema de "join nas vias" levantado (a não ser que optemos por fazer manualmente).

---

## Sobre função volume-atraso (VDF):

- **Nome:** A Influência da Função Volume-Atraso na Avaliação de Incerteza para um Modelo de Quatro Etapas [ResearchGate]
- **Link:** [clique aqui](https://www.researchgate.net/publication/286767378_The_Influence_of_the_Volume-Delay_Function_on_Uncertainty_Assessment_for_a_Four-Step_Model)
- **Notas:** mostra que a variação da capacidade tem impacto maior na incerteza final do que os parâmetros α e β da própria VDF. Ou seja, gastem esforço estimando capacidade corretamente, não calibrando parâmetros.

---

## Sobre calibração da VDF:

- **Nome:** Função Volume-Atraso Modificada Baseada no Diagrama Fundamental de Tráfego: Uma Estrutura Prática de Calibração [ResearchGate]
- **Link:** [clique aqui](https://www.researchgate.net/publication/375171137_Modified_Volume-Delay_Function_Based_on_Traffic_Fundamental_Diagram_A_Practical_Calibration_Framework_for_Estimating_Congested_and_Uncongested_Conditions)
- **Notas:** estudo em Bagdá calibrou α = 0,8 e β = 4,7 para arteriais urbanas — podem usar esses valores como referência inicial.

---

## Sobre alocação de tráfego e equilíbrio de Wardrop:

- **Nome:** Equilíbrio de Wardrop e Alocação de Tráfego [arXiv]
- **Link:** [clique aqui](https://arxiv.org/pdf/2402.02552)
- **Notas:** formaliza como motoristas otimizam rotas até atingir equilíbrio (ninguém reduz custo mudando sozinho). É o arcabouço correto para modelar como uma via afeta as adjacentes — não usem fluxo máximo.

---

## Sobre Paradoxo de Braess:

- **Nome:** O Paradoxo de Braess em Redes de Grande Escala [arXiv]
- **Link:** [clique aqui](https://arxiv.org/pdf/1207.3251)
- **Notas:** prova que em quase toda rede existe um conjunto de arestas cuja remoção melhora o tempo de viagem no equilíbrio. "Melhorar uma via necessariamente melhora o sistema?" — não.

---

## Sobre método prático para detectar Braess:

- **Nome:** Redes Eficientes Exigem Trabalho: Gerenciamento de Tráfego e o Paradoxo de Braess [SSTI]
- **Link:** [clique aqui](https://ssti.us/2018/01/16/efficient-networks-take-work-traffic-management-and-braess-paradox/)
- **Notas:** método da Southeast University: calculam o tempo total de viagem do sistema, removem uma ou duas arestas por vez e medem se o tempo sobe ou desce, testando diferentes níveis de demanda. É um experimento computacional viável e publicável.

---

## Sobre Problema de Projeto de Rede Discreto (DNDP):

- **Nome:** Problema de Projeto de Rede Discreto [PLOS ONE]
- **Link:** [clique aqui](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0192454)
- **Notas:** dado um conjunto de projetos candidatos com custos, escolher o melhor subconjunto sob orçamento limitado é um problema binível NP-difícil.

---

## Sobre DNDP multi-capacidade:

- **Nome:** Problema de Projeto de Rede com Múltiplas Capacidades [Wang, Meng & Yang (2013), Transportation Research Part B]
- **Link:** [clique aqui](https://www.sciencedirect.com/science/article/abs/pii/S0191261513000179)
- **Notas:** nível superior minimiza tempo total de viagem adicionando faixas a arestas candidatas; nível inferior é o equilíbrio de usuário de Wardrop.

---

## Sobre DNDP multiobjetivo com NSGA-II:

- **Nome:** Projeto de Rede Viária Multiobjetivo e Ambientalmente Sustentável Usando Otimização de Pareto [ResearchGate]
- **Link:** [clique aqui](https://www.researchgate.net/publication/319606906_Multiobjective_Environmentally_Sustainable_Road_Network_Design_Using_Pareto_Optimization)
- **Notas:** resolve o problema de converter vias de mão dupla para mão única usando NSGA-II, com equilíbrio de usuário resolvido por Frank-Wolfe no nível inferior. Exatamente a pergunta "sentido da via" da lista de vocês.

---

## Sobre centralidade como preditor de fluxo:

- **Nome:** Medidas de Centralidade para Identificar Congestionamento de Tráfego em Redes Viárias: Um Estudo de Caso do Sri Lanka [Academia.edu]
- **Link:** [clique aqui](https://www.academia.edu/33809387/Centrality_Measures_to_Identify_Traffic_Congestion_on_Road_Networks_A_Case_Study_of_Sri_Lanka)
- **Notas:** centralidade de intermediação não é bom preditor de fluxo urbano — a correlação com tráfego real desaparece em alta densidade. Usem métricas de grafo como descritor, não como preditor.

---

## Sobre centralidade e alta densidade:

- **Nome:** Sobre as Limitações das Medidas de Centralidade em Redes Urbanas [arXiv]
- **Link:** [clique aqui](https://arxiv.org/pdf/2312.02626)
- **Notas:** a medida assume custo fixo por aresta e agentes ilimitados independentemente da capacidade física, o que não reflete o regime de alta densidade. Bom achado para a discussão do trabalho.

---

## Sobre estimação de matriz OD:

- **Nome:** Estimação Compressiva da Matriz Origem-Destino [ResearchGate]
- **Link:** [clique aqui](https://www.researchgate.net/publication/261635930_Compressive_Origin-Destination_Matrix_Estimation)
- **Notas:** estimar OD a partir de contagens é um problema inverso subdeterminado com infinitas soluções (menos contagens que caminhos possíveis). Referência canônica: Van Zuylen & Willumsen (1980) e Abrahamsson (1998).

---

## Sobre simulação com SUMO:

- **Nome:** SUMO — Documentação do Eclipse SUMO [GitHub]
- **Link:** [clique aqui](https://github.com/eclipse-sumo/sumo/blob/main/docs/web/docs/Networks/Import/OpenStreetMap.md)
- **Notas:** osmWebWizard.py constrói cenário completo a partir do OSM rapidamente, mas a maioria dos métodos de importação gera deficiências de qualidade da rede (congestionamentos irreais e erros de teleporte de veículos).
