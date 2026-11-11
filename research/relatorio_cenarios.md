# Cenários de intervenção e teste do paradoxo de Braess

*Gerado por `scripts/relatorio_cenarios.py` em 10/11/2026, a partir de `resultados/`. Todos os números abaixo são lidos dos arquivos de resultado; para atualizar, rode de novo os comandos da seção 1 e este script.*

Este documento registra a etapa de cenários prevista no artigo (`artigo/artigoFinal.tex`, "Alocação, cenários e indicadores") e no plano de pesquisa (passo 5: 15 a 30 grafos alterados): acréscimo de faixa, mudança de sentido e remoção de arestas, esta como teste do paradoxo de Braess, nos três níveis de demanda e com a sensibilidade a = 0,8 e b = 4,7.

## 1. Como foi rodado

```bash
python scripts/gerar_cenarios.py                       # gera cenarios/*.json a partir de critérios sobre o grafo
python scripts/frank_wolfe.py --todos                  # situação atual + todos os cenários (a = 0,15; b = 4)
python scripts/frank_wolfe.py --alpha 0.8 --beta 4.7 --todos
python scripts/frank_wolfe.py --varredura-remocao --varredura-faixa
python scripts/frank_wolfe.py --alpha 0.8 --beta 4.7 --varredura-remocao --varredura-faixa
python scripts/visualizar_resultados.py               # resultados/painel.html e resultados/figuras/
python scripts/relatorio_cenarios.py                  # este documento
```

**Configuração comum a todos os casos:**

- **Grafo:** `dados/grafo/gama_drive_expanded_atributos.graphml` (134 nós, 235 arestas de carro); **matriz OD:** `dados/tabelas/matriz_od_final.json` (1.031 pares).
- **Níveis de demanda (obrigatórios):** baixa (fator 8,82), adotada (12,21) e alta (21,96). A demanda de cada par é `veic_h × fator / 12,21`, e cada nível usa a capacidade efetiva calibrada para o seu fator.
- **Função de atraso:** BPR com a = 0,15 e b = 4 (base) e a = 0,8 e b = 4,7 (sensibilidade; a capacidade efetiva dos gargalos é recalculada e a faixa extra dos cenários é preservada).
- **Parada do Frank-Wolfe:** gap relativo < 10⁻⁴ ou 500 iterações. Todas as rodadas de cenário convergiram ao gap 10⁻⁴. Na sensibilidade com a = 0,8, a rede fica mais congestionada e o Frank-Wolfe converge mais devagar: R1_fechar_alca_acesso_df480_21_18_a0.8_b4.7 (alta: 668 iterações); S3_inverter_alca_acesso_df480_a0.8_b4.7 (alta: 719 iterações) precisaram de mais de 500 iterações e foram rodados com teto de 5.000 (`--iter-max 5000`), mantendo o critério de gap.
- **Regras das alterações** (`scripts/frank_wolfe.py`, `aplicar_cenario`):
  - **faixa:** nos 25 gargalos calibrados, capacidade efetiva × (faixas + 1) / faixas; nas demais arestas, + 1 × capacidade por faixa da classe (1.800 na EPCT, 1.200 na DF-480 e nas alças da rodovia, 900 nas terciárias, 600 nas alças terciárias e locais);
  - **remover:** a aresta sai do grafo;
  - **inverter:** u→v passa a v→u (falha se v→u já existir);
  - cenários que desconectariam algum par OD são recusados, porque a demanda é fixa.
- **Como os cenários foram escolhidos** (`scripts/gerar_cenarios.py`): por critérios sobre o grafo (gargalos por rodovia e sentido, alças com K observado < 0,25, as coletoras de maior fluxo, acessos que convergem nos gargalos). Quatro candidatos foram descartados por desconectarem pares OD e substituídos: inverter ou fechar o acesso 127→130→103→126 à EPCT norte (é a única saída da zona da CAUB/Chácara 95), fechar a alça 67→66 (16 pares) e tornar a Av. São Francisco mão única (52 pares).

## 2. Situação atual (referência de todas as comparações)

**Parâmetros-base (a = 0,15; b = 4)** (`resultados/base/`)

| Demanda | Fator | veíc/h | TSTT (veíc·h) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações | Gap final |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 8,82 | 6.002 | 343,4 | 0,7026 | 45,2 | 3,43 | 20 | 67 | 2 | < 1e-12 |
| adotada | 12,21 | 8.309 | 476,9 | 0,7001 | 45,0 | 3,44 | 20 | 67 | 4 | 3.1e-09 |
| alta | 21,96 | 14.944 | 884,4 | 0,6763 | 43,7 | 3,55 | 26 | 68 | 28 | 1.0e-04 |

**Sensibilidade (a = 0,8; b = 4,7)** (`resultados/base_a0.8_b4.7/`)

| Demanda | Fator | veíc/h | TSTT (veíc·h) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações | Gap final |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 8,82 | 6.002 | 344,1 | 0,7010 | 45,1 | 3,44 | 5 | 67 | 4 | < 1e-12 |
| adotada | 12,21 | 8.309 | 480,3 | 0,6953 | 44,7 | 3,47 | 5 | 67 | 6 | 9.5e-05 |
| alta | 21,96 | 14.944 | 1.166,6 | 0,5126 | 33,1 | 4,68 | 13 | 76 | 190 | 1.0e-04 |

## 3. Resumo dos cenários

ΔTSTT e ΔK da rede em relação à situação atual, na ordem **demanda baixa / adotada / alta**. A última coluna repete o ΔTSTT com a = 0,8 e b = 4,7.

| Caso | Alteração | ΔTSTT (%) | ΔK da rede | Classificação | ΔTSTT (%) com a = 0,8 |
|---|---|---|---|---|---|
| **C0** | +1 faixa nos 5 gargalos da EPCT sentido norte imediatamente antes do trevo (caso usado na V1 do artigo) | -8,59 / -8,57 / -8,32 | +0,0237 / +0,0237 / +0,0236 | melhora robusta | -9,10 / -9,07 / -7,65 |
| **F1** | +1 faixa em todos os gargalos da EPCT (DF-001) sentido norte | -9,19 / -9,22 / -9,19 | +0,0253 / +0,0256 / +0,0265 | melhora robusta | -9,76 / -9,86 / -9,14 |
| **F2** | +1 faixa em todos os gargalos da EPCT (DF-001) sentido sul | -1,40 / -1,47 / -1,50 | +0,0063 / +0,0064 / +0,0070 | melhora robusta | -1,58 / -1,57 / -1,91 |
| **F3** | +1 faixa em todos os gargalos da DF-480 (sentido sudoeste) e na alça de acesso | -3,58 / -3,57 / -3,87 | +0,0389 / +0,0390 / +0,0418 | melhora robusta | -3,87 / -3,91 / -14,58 |
| **F4** | +1 faixa nas alças do trevo com K observado < 0,25 | -0,03 / -0,11 / -0,16 | +0,0001 / +0,0004 / 0,0000 | melhora pequena (só na demanda adotada, alta) | -0,10 / -0,11 / -0,31 |
| **F5** | +1 faixa na Avenida São Francisco (coletora), nos dois sentidos | 0,00 / -0,01 / -0,06 | 0,0000 / 0,0000 / +0,0002 | melhora pequena (só na demanda alta) | 0,00 / -0,01 / -0,18 |
| **F6** | +1 faixa na Marginal DF-480, nos dois sentidos | 0,00 / 0,00 / 0,00 | 0,0000 / 0,0000 / 0,0000 | efeito desprezível | 0,00 / 0,00 / -0,02 |
| **S1** | Marginal DF-480 em mão única (binário): remove o sentido de menor fluxo | +2,27 / +2,29 / +2,62 | -0,0003 / -0,0006 / -0,0039 | piora robusta | +2,38 / +2,48 / +5,37 |
| **S2** | Inverte o acesso 30→7: a entrada na DF-480 vira saída da DF-480 | +8,87 / +8,86 / +8,89 | -0,0238 / -0,0238 / -0,0237 | piora robusta | +9,59 / +9,62 / +15,80 |
| **S3** | Inverte a alça 'Acesso DF-480' (26→21→18): a ligação EPCT sul → DF-480 passa a ser DF-480 → EPCT | +1,15 / +1,54 / +3,23 | +0,0021 / +0,0010 / -0,0033 | piora robusta; K × TSTT divergem (baixa, adotada) | +1,63 / +3,06 / +2,99 |
| **R1** | Fecha a alça 21→18 ('Acesso DF-480'), que converge no gargalo 18→4 | +1,12 / +1,53 / +2,92 | +0,0022 / +0,0010 / -0,0017 | piora robusta; K × TSTT divergem (baixa, adotada) | +1,59 / +2,74 / +2,96 |
| **R2** | Fecha o acesso 30→7 à DF-480 | +8,87 / +8,86 / +8,89 | -0,0238 / -0,0238 / -0,0237 | piora robusta | +9,59 / +9,62 / +15,80 |
| **R3** | Fecha a alça 11→63 (retorno EPCT sul → EPCT norte), de K observado 0,16 | +2,45 / +2,47 / +2,57 | -0,0036 / -0,0038 / -0,0047 | piora robusta | +2,70 / +2,72 / +2,52 |

Classificação: **melhora/piora robusta** = o TSTT muda no mesmo sentido nos três níveis; **dependente da demanda** = o sinal muda; **efeito desprezível** = |ΔTSTT| < 0,05% nos três. **K × TSTT divergem** = níveis em que o K da rede melhora enquanto o TSTT piora (ou o contrário), que é o critério de indício de Braess usado no artigo.

## 4. Cenários, um a um

### C0 — +1 faixa nos 5 gargalos da EPCT sentido norte imediatamente antes do trevo (caso usado na V1 do artigo)

- **Arquivo:** `cenarios/C0_faixa_epct_norte_trevo.json` · resultados em `resultados/C0_faixa_epct_norte_trevo/`
- **Família:** faixa
- **Critério de escolha:** os 5 gargalos da EPCT norte imediatamente antes do trevo (132→133→63→102→126→60); foi o primeiro cenário do projeto e é o caso de adição de faixa analisado no artigo

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 132→133 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.225 → 1.838 | sim | 2.022 | 0,30 |
| 133→63 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.147 → 1.720 | sim | 2.025 | 0,37 |
| 63→102 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.291 → 1.936 | sim | 2.154 | 0,35 |
| 102→126 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.480 → 2.220 | sim | 2.050 | 0,40 |
| 126→60 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.454 → 2.181 | sim | 2.347 | 0,35 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 313,9 | -1.770,3 | -8,59 | 0,7026 → 0,7263 | 45,2 → 49,5 | 3,43 → 3,14 | 20 → 19 | 67 → 62 | 1 (4.2e-05) |
| adotada | 476,9 | 436,1 | -2.452,4 | -8,57 | 0,7001 → 0,7238 | 45,0 → 49,3 | 3,44 → 3,15 | 20 → 19 | 67 → 62 | 2 (4.7e-05) |
| alta | 884,4 | 810,8 | -4.415,2 | -8,32 | 0,6763 → 0,6999 | 43,7 → 47,6 | 3,55 → 3,25 | 26 → 25 | 68 → 63 | 18 (9.8e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 132→133 | 2.022 → 2.026 | 1,65 → 1,10 | 0,30 → 0,52 | 18,2 → 31,4 |
| 133→63 | 2.025 → 2.028 | 1,77 → 1,18 | 0,37 → 0,70 | 22,0 → 41,9 |
| 63→102 | 2.154 → 2.155 | 1,67 → 1,11 | 0,35 → 0,62 | 21,2 → 37,2 |
| 102→126 | 2.050 → 2.052 | 1,39 → 0,92 | 0,40 → 0,56 | 24,1 → 33,7 |
| 126→60 | 2.347 → 2.349 | 1,61 → 1,08 | 0,35 → 0,59 | 21,1 → 35,5 |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 226 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 64→66 | Estrada Parque Contorno | 953 → 959 | +6,1 | 0,47 → 0,47 |
| 8→16 | primary | 728 → 733 | +5,0 | 0,85 → 0,85 |
| 16→106 | primary | 932 → 936 | +4,5 | 0,71 → 0,71 |
| 124→64 | Estrada Parque Contorno | 1.084 → 1.089 | +4,5 | 0,69 → 0,69 |
| 106→124 | trunk_link | 140 → 145 | +4,5 | 0,48 → 0,48 |
| 66→132 | Estrada Parque Contorno | 2.021 → 2.025 | +3,3 | 0,33 → 0,33 |
| 68→73 | trunk_link | 910 → 908 | -2,8 | 0,72 → 0,72 |
| 8→68 | trunk_link | 974 → 972 | -2,8 | 0,78 → 0,78 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT -9,10% / -9,07% / -7,65% e ΔK da rede +0,0262 / +0,0263 / +0,0273 (baixa / adotada / alta).

**Classificação:** melhora robusta.

### F1 — +1 faixa em todos os gargalos da EPCT (DF-001) sentido norte

- **Arquivo:** `cenarios/F1_faixa_epct_norte.json` · resultados em `resultados/F1_faixa_epct_norte/`
- **Família:** faixa
- **Critério de escolha:** arestas com gargalo = True, ref DF-001 e rumo noroeste (sentido norte da EPCT)

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 60→62 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.778 → 2.667 | sim | 2.160 | 0,41 |
| 63→102 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.291 → 1.936 | sim | 2.154 | 0,35 |
| 64→66 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.264 → 1.896 | sim | 953 | 0,30 |
| 66→132 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.439 → 2.158 | sim | 2.021 | 0,33 |
| 102→126 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.480 → 2.220 | sim | 2.050 | 0,40 |
| 124→64 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.639 → 2.458 | sim | 1.084 | 0,55 |
| 126→60 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.454 → 2.181 | sim | 2.347 | 0,35 |
| 132→133 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.225 → 1.838 | sim | 2.022 | 0,30 |
| 133→63 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.147 → 1.720 | sim | 2.025 | 0,37 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 311,8 | -1.892,2 | -9,19 | 0,7026 → 0,7279 | 45,2 → 49,8 | 3,43 → 3,12 | 20 → 17 | 67 → 61 | 1 (3.9e-05) |
| adotada | 476,9 | 432,9 | -2.639,3 | -9,22 | 0,7001 → 0,7257 | 45,0 → 49,6 | 3,44 → 3,13 | 20 → 17 | 67 → 61 | 2 (4.2e-05) |
| alta | 884,4 | 803,1 | -4.877,7 | -9,19 | 0,6763 → 0,7028 | 43,7 → 48,1 | 3,55 → 3,22 | 26 → 21 | 68 → 62 | 12 (1.0e-04) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 60→62 | 2.160 → 2.160 | 1,21 → 0,81 | 0,41 → 0,51 | 24,5 → 30,5 |
| 63→102 | 2.154 → 2.155 | 1,67 → 1,11 | 0,35 → 0,62 | 21,2 → 37,2 |
| 64→66 | 953 → 1.028 | 0,75 → 0,54 | 0,47 → 0,48 | 37,3 → 38,6 |
| 66→132 | 2.021 → 2.024 | 1,40 → 0,94 | 0,33 → 0,46 | 19,6 → 27,8 |
| 102→126 | 2.050 → 2.052 | 1,39 → 0,92 | 0,40 → 0,56 | 24,1 → 33,7 |
| 124→64 | 1.084 → 1.158 | 0,66 → 0,47 | 0,69 → 0,71 | 55,5 → 56,7 |
| 126→60 | 2.347 → 2.349 | 1,61 → 1,08 | 0,35 → 0,59 | 21,1 → 35,5 |
| 132→133 | 2.022 → 2.026 | 1,65 → 1,10 | 0,30 → 0,52 | 18,2 → 31,4 |
| 133→63 | 2.025 → 2.028 | 1,77 → 1,18 | 0,37 → 0,70 | 22,0 → 41,9 |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 836 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 8→16 | primary | 728 → 803 | +74,2 | 0,85 → 0,85 |
| 106→124 | trunk_link | 140 → 214 | +73,7 | 0,48 → 0,48 |
| 16→106 | primary | 932 → 1.005 | +73,7 | 0,71 → 0,71 |
| 8→68 | trunk_link | 974 → 902 | -72,2 | 0,78 → 0,80 |
| 67→66 | trunk_link | 1.041 → 969 | -72,2 | 0,42 → 0,42 |
| 68→73 | trunk_link | 910 → 838 | -72,2 | 0,72 → 0,73 |
| 73→67 | trunk_link | 874 → 802 | -72,2 | 0,67 → 0,68 |
| 6→7 | primary | 2.008 → 2.011 | +2,5 | 0,65 → 0,65 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT -9,76% / -9,86% / -9,14% e ΔK da rede +0,0282 / +0,0288 / +0,0318 (baixa / adotada / alta).

**Classificação:** melhora robusta.

### F2 — +1 faixa em todos os gargalos da EPCT (DF-001) sentido sul

- **Arquivo:** `cenarios/F2_faixa_epct_sul.json` · resultados em `resultados/F2_faixa_epct_sul/`
- **Família:** faixa
- **Critério de escolha:** arestas com gargalo = True, ref DF-001 e rumo sudeste (sentido sul da EPCT)

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 0→11 | Estrada Parque Contorno | trunk | +1 faixa | 3 → 4 | 1.763 → 2.351 | sim | 2.075 | 0,67 |
| 9→20 | Estrada Parque Contorno | trunk | +1 faixa | 3 → 4 | 1.526 → 2.035 | sim | 1.934 | 0,42 |
| 11→9 | Estrada Parque Contorno | trunk | +1 faixa | 3 → 4 | 1.244 → 1.659 | sim | 1.944 | 0,29 |
| 17→26 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 2.402 → 3.603 | sim | 1.957 | 0,47 |
| 20→17 | Estrada Parque Contorno | trunk | +1 faixa | 3 → 4 | 1.753 → 2.337 | sim | 1.918 | 0,42 |
| 25→0 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 2.211 → 3.316 | sim | 2.065 | 0,90 |
| 61→10 | Estrada Parque Contorno | trunk | +1 faixa | 2 → 3 | 1.446 → 2.169 | sim | 1.843 | 0,38 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 338,5 | -289,0 | -1,40 | 0,7026 → 0,7089 | 45,2 → 45,9 | 3,43 → 3,38 | 20 → 16 | 67 → 66 | 1 (9.9e-05) |
| adotada | 476,9 | 469,9 | -420,1 | -1,47 | 0,7001 → 0,7065 | 45,0 → 45,7 | 3,44 → 3,39 | 20 → 16 | 67 → 66 | 4 (< 1e-12) |
| alta | 884,4 | 871,1 | -793,7 | -1,50 | 0,6763 → 0,6833 | 43,7 → 44,3 | 3,55 → 3,50 | 26 → 21 | 68 → 67 | 22 (9.8e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 0→11 | 2.075 → 2.077 | 1,18 → 0,88 | 0,67 → 0,80 | 40,5 → 47,7 |
| 9→20 | 1.934 → 1.935 | 1,27 → 0,95 | 0,42 → 0,52 | 33,5 → 41,4 |
| 11→9 | 1.944 → 1.945 | 1,56 → 1,17 | 0,30 → 0,44 | 17,7 → 26,2 |
| 17→26 | 1.957 → 1.957 | 0,81 → 0,54 | 0,47 → 0,50 | 37,9 → 39,9 |
| 20→17 | 1.918 → 1.919 | 1,09 → 0,82 | 0,42 → 0,48 | 33,4 → 38,0 |
| 25→0 | 2.065 → 2.066 | 0,93 → 0,62 | 0,90 → 0,98 | 53,8 → 58,6 |
| 61→10 | 1.843 → 1.843 | 1,27 → 0,85 | 0,38 → 0,50 | 23,0 → 29,8 |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 72 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 133→63 | Estrada Parque Contorno | 2.025 → 2.024 | -1,1 | 0,37 → 0,37 |
| 18→4 | primary | 2.143 → 2.144 | +1,1 | 0,65 → 0,65 |
| 132→133 | Estrada Parque Contorno | 2.022 → 2.021 | -1,1 | 0,30 → 0,30 |
| 11→63 | trunk_link | 138 → 139 | +1,1 | 0,36 → 0,36 |
| 21→18 | Acesso DF-480 | 888 → 889 | +1,1 | 0,57 → 0,57 |
| 26→21 | Acesso DF-480 | 879 → 880 | +1,1 | 0,42 → 0,42 |
| 27→28 | DF-480 Km 5 1 Pan Bola na Rede | 33 → 34 | +1,1 | 0,79 → 0,79 |
| 72→19 | Avenida do Sol | 13 → 12 | -1,1 | 0,35 → 0,35 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT -1,58% / -1,57% / -1,91% e ΔK da rede +0,0069 / +0,0069 / +0,0122 (baixa / adotada / alta).

**Classificação:** melhora robusta.

### F3 — +1 faixa em todos os gargalos da DF-480 (sentido sudoeste) e na alça de acesso

- **Arquivo:** `cenarios/F3_faixa_df480.json` · resultados em `resultados/F3_faixa_df480/`
- **Família:** faixa
- **Critério de escolha:** arestas com gargalo = True que não são da EPCT (DF-480, classe primary, e a alça 'Acesso DF-480')

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 4→5 | sem nome | primary | +1 faixa | 3 → 4 | 1.809 → 2.412 | sim | 2.063 | 0,66 |
| 5→6 | sem nome | primary | +1 faixa | 3 → 4 | 1.924 → 2.565 | sim | 2.071 | 0,75 |
| 6→7 | sem nome | primary | +1 faixa | 3 → 4 | 1.774 → 2.365 | sim | 2.008 | 0,65 |
| 7→22 | sem nome | primary | +1 faixa | 3 → 4 | 2.056 → 2.741 | sim | 2.413 | 0,72 |
| 14→18 | sem nome | primary | +1 faixa | 3 → 4 | 1.072 → 1.429 | sim | 1.248 | 0,68 |
| 18→4 | sem nome | primary | +1 faixa | 3 → 4 | 1.883 → 2.511 | sim | 2.143 | 0,65 |
| 21→18 | Acesso DF-480 | trunk_link | +1 faixa | 1 → 2 | 894 → 1.788 | sim | 888 | 0,57 |
| 22→23 | sem nome | primary | +1 faixa | 3 → 4 | 2.256 → 3.008 | sim | 2.272 | 0,78 |
| 65→14 | sem nome | primary | +1 faixa | 3 → 4 | 1.188 → 1.584 | sim | 1.400 | 0,70 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 331,1 | -737,0 | -3,58 | 0,7026 → 0,7415 | 45,2 → 46,9 | 3,43 → 3,31 | 20 → 12 | 67 → 67 | 1 (8.6e-05) |
| adotada | 476,9 | 459,9 | -1.020,9 | -3,57 | 0,7001 → 0,7391 | 45,0 → 46,7 | 3,44 → 3,32 | 20 → 12 | 67 → 67 | 2 (9.0e-05) |
| alta | 884,4 | 850,1 | -2.054,0 | -3,87 | 0,6763 → 0,7181 | 43,7 → 45,5 | 3,55 → 3,41 | 26 → 17 | 68 → 67 | 16 (9.7e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 4→5 | 2.063 → 2.065 | 1,14 → 0,86 | 0,66 → 0,76 | 52,4 → 60,8 |
| 5→6 | 2.071 → 2.074 | 1,08 → 0,81 | 0,75 → 0,85 | 59,9 → 67,7 |
| 6→7 | 2.008 → 2.011 | 1,13 → 0,85 | 0,65 → 0,76 | 52,3 → 60,5 |
| 7→22 | 2.413 → 2.415 | 1,17 → 0,88 | 0,72 → 0,84 | 57,3 → 67,5 |
| 14→18 | 1.248 → 1.246 | 1,16 → 0,87 | 0,68 → 0,80 | 54,4 → 63,9 |
| 18→4 | 2.143 → 2.143 | 1,14 → 0,85 | 0,65 → 0,75 | 51,9 → 60,2 |
| 21→18 | 888 → 890 | 0,99 → 0,50 | 0,57 → 0,65 | 45,6 → 51,8 |
| 22→23 | 2.272 → 2.272 | 1,01 → 0,76 | 0,78 → 0,86 | 62,2 → 68,5 |
| 65→14 | 1.400 → 1.398 | 1,18 → 0,88 | 0,70 → 0,83 | 56,3 → 66,5 |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 259 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 64→66 | Estrada Parque Contorno | 953 → 963 | +9,8 | 0,47 → 0,47 |
| 8→16 | primary | 728 → 737 | +8,8 | 0,85 → 0,85 |
| 16→106 | primary | 932 → 940 | +8,2 | 0,71 → 0,71 |
| 124→64 | Estrada Parque Contorno | 1.084 → 1.093 | +8,2 | 0,69 → 0,69 |
| 106→124 | trunk_link | 140 → 149 | +8,2 | 0,48 → 0,48 |
| 68→73 | trunk_link | 910 → 904 | -6,6 | 0,72 → 0,72 |
| 8→68 | trunk_link | 974 → 968 | -6,6 | 0,78 → 0,79 |
| 73→67 | trunk_link | 874 → 867 | -6,6 | 0,67 → 0,67 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT -3,87% / -3,91% / -14,58% e ΔK da rede +0,0427 / +0,0429 / +0,0941 (baixa / adotada / alta).

**Classificação:** melhora robusta.

### F4 — +1 faixa nas alças do trevo com K observado < 0,25

- **Arquivo:** `cenarios/F4_faixa_alcas_k_baixo.json` · resultados em `resultados/F4_faixa_alcas_k_baixo/`
- **Família:** faixa
- **Critério de escolha:** classe trunk_link com k_inicial < 0.25 (as alças apontadas como gargalo crítico no diagnóstico do K)

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 11→63 | sem nome | trunk_link | +1 faixa | 1 → 2 | 1.200 → 2.400 | não | 138 | 0,16 |
| 19→17 | Acesso DF-480 | trunk_link | +1 faixa | 1 → 2 | 1.200 → 2.400 | não | 17 | 0,17 |
| 21→72 | sem nome | trunk_link | +1 faixa | 1 → 2 | 1.200 → 2.400 | não | 1 | 0,15 |
| 60→10 | sem nome | trunk_link | +1 faixa | 1 → 2 | 1.200 → 2.400 | não | 173 | 0,12 |
| 67→66 | sem nome | trunk_link | +1 faixa | 1 → 2 | 1.200 → 2.400 | não | 1.041 | 0,24 |
| 133→9 | sem nome | trunk_link | +1 faixa | 1 → 2 | 1.200 → 2.400 | não | 14 | 0,13 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 343,2 | -6,8 | -0,03 | 0,7026 → 0,7027 | 45,2 → 45,2 | 3,43 → 3,43 | 20 → 20 | 67 → 67 | 2 (< 1e-12) |
| adotada | 476,9 | 476,4 | -32,4 | -0,11 | 0,7001 → 0,7005 | 45,0 → 45,1 | 3,44 → 3,44 | 20 → 20 | 67 → 67 | 2 (3.2e-09) |
| alta | 884,4 | 882,9 | -84,9 | -0,16 | 0,6763 → 0,6763 | 43,7 → 43,8 | 3,55 → 3,54 | 26 → 25 | 68 → 68 | 16 (9.7e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 11→63 | 138 → 138 | 0,12 → 0,06 | 0,36 → 0,36 | 28,8 → 28,8 |
| 19→17 | 17 → 17 | 0,01 → 0,01 | 0,17 → 0,17 | 13,3 → 13,3 |
| 21→72 | 1 → 1 | 0,00 → 0,00 | 0,15 → 0,15 | 12,1 → 12,1 |
| 60→10 | 173 → 173 | 0,14 → 0,07 | 0,30 → 0,30 | 24,1 → 24,1 |
| 67→66 | 1.041 → 1.053 | 0,87 → 0,44 | 0,42 → 0,45 | 33,3 → 35,9 |
| 133→9 | 14 → 14 | 0,01 → 0,01 | 0,31 → 0,31 | 24,8 → 24,8 |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 108 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 73→67 | trunk_link | 874 → 886 | +11,9 | 0,67 → 0,67 |
| 106→124 | trunk_link | 140 → 128 | -11,9 | 0,48 → 0,48 |
| 16→106 | primary | 932 → 920 | -11,9 | 0,71 → 0,71 |
| 64→66 | Estrada Parque Contorno | 953 → 941 | -11,9 | 0,47 → 0,47 |
| 68→73 | trunk_link | 910 → 922 | +11,9 | 0,72 → 0,72 |
| 8→68 | trunk_link | 974 → 986 | +11,9 | 0,78 → 0,78 |
| 8→16 | primary | 728 → 716 | -11,9 | 0,85 → 0,85 |
| 124→64 | Estrada Parque Contorno | 1.084 → 1.072 | -11,9 | 0,69 → 0,69 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT -0,10% / -0,11% / -0,31% e ΔK da rede +0,0002 / -0,0001 / +0,0006 (baixa / adotada / alta).

**Classificação:** melhora pequena (só na demanda adotada, alta).

### F5 — +1 faixa na Avenida São Francisco (coletora), nos dois sentidos

- **Arquivo:** `cenarios/F5_faixa_av_sao_francisco.json` · resultados em `resultados/F5_faixa_av_sao_francisco/`
- **Família:** faixa
- **Critério de escolha:** arestas com name = 'Avenida São Francisco': a via coletora de maior fluxo do grafo

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 30→79 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 123 | 0,31 |
| 53→54 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 313 | 0,78 |
| 54→53 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 251 | 0,69 |
| 54→93 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 322 | 0,75 |
| 55→79 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 342 | 0,60 |
| 55→93 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 259 | 0,77 |
| 79→30 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 411 | 0,51 |
| 79→55 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 266 | 0,62 |
| 93→54 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 259 | 0,67 |
| 93→55 | Avenida São Francisco | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 325 | 0,85 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 343,4 | -0,3 | 0,00 | 0,7026 → 0,7026 | 45,2 → 45,2 | 3,43 → 3,43 | 20 → 20 | 67 → 67 | 2 (< 1e-12) |
| adotada | 476,9 | 476,9 | -1,6 | -0,01 | 0,7001 → 0,7001 | 45,0 → 45,0 | 3,44 → 3,44 | 20 → 20 | 67 → 67 | 4 (3.1e-09) |
| alta | 884,4 | 883,9 | -30,0 | -0,06 | 0,6763 → 0,6765 | 43,7 → 43,7 | 3,55 → 3,55 | 26 → 26 | 68 → 68 | 28 (1.0e-04) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 30→79 | 123 → 123 | 0,14 → 0,07 | 0,46 → 0,46 | 18,2 → 18,2 |
| 53→54 | 313 → 313 | 0,35 → 0,17 | 0,85 → 0,85 | 34,1 → 34,2 |
| 54→53 | 251 → 251 | 0,28 → 0,14 | 0,72 → 0,72 | 29,0 → 29,0 |
| 54→93 | 322 → 322 | 0,36 → 0,18 | 0,76 → 0,76 | 30,4 → 30,5 |
| 55→79 | 342 → 342 | 0,38 → 0,19 | 0,72 → 0,72 | 28,9 → 29,0 |
| 55→93 | 259 → 259 | 0,29 → 0,14 | 0,82 → 0,82 | 32,9 → 32,9 |
| 79→30 | 411 → 411 | 0,46 → 0,23 | 0,62 → 0,62 | 24,7 → 24,9 |
| 79→55 | 266 → 266 | 0,30 → 0,15 | 0,71 → 0,71 | 28,4 → 28,4 |
| 93→54 | 259 → 259 | 0,29 → 0,14 | 0,75 → 0,75 | 29,9 → 29,9 |
| 93→55 | 325 → 325 | 0,36 → 0,18 | 0,87 → 0,87 | 34,8 → 34,9 |

**Redistribuição:** nenhuma aresta fora das alteradas mudou mais de 0,5 veíc/h (soma de |Δfluxo|: 0,0 veíc/h).

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT 0,00% / -0,01% / -0,18% e ΔK da rede 0,0000 / +0,0001 / +0,0010 (baixa / adotada / alta).

**Classificação:** melhora pequena (só na demanda alta).

### F6 — +1 faixa na Marginal DF-480, nos dois sentidos

- **Arquivo:** `cenarios/F6_faixa_marginal_df480.json` · resultados em `resultados/F6_faixa_marginal_df480/`
- **Família:** faixa
- **Critério de escolha:** arestas com name = 'Marginal DF-480': coletora com K observado entre 0,26 e 0,6

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 56→87 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 71 | 0,44 |
| 56→91 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 137 | 0,52 |
| 77→105 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 116 | 0,60 |
| 78→86 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 130 | 0,49 |
| 78→105 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 71 | 0,46 |
| 79→91 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 78 | 0,42 |
| 86→78 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 72 | 0,41 |
| 86→87 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 132 | 0,60 |
| 87→56 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 132 | 0,49 |
| 87→86 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 72 | 0,54 |
| 91→56 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 76 | 0,61 |
| 91→79 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 138 | 0,26 |
| 105→77 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 72 | 0,52 |
| 105→78 | Marginal DF-480 | tertiary | +1 faixa | 1 → 2 | 900 → 1.800 | não | 128 | 0,51 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 343,4 | 0,0 | 0,00 | 0,7026 → 0,7026 | 45,2 → 45,2 | 3,43 → 3,43 | 20 → 20 | 67 → 67 | 2 (< 1e-12) |
| adotada | 476,9 | 476,9 | 0,0 | 0,00 | 0,7001 → 0,7001 | 45,0 → 45,0 | 3,44 → 3,44 | 20 → 20 | 67 → 67 | 4 (3.1e-09) |
| alta | 884,4 | 884,4 | -0,3 | 0,00 | 0,6763 → 0,6763 | 43,7 → 43,7 | 3,55 → 3,55 | 26 → 26 | 68 → 68 | 28 (1.0e-04) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 56→87 | 71 → 71 | 0,08 → 0,04 | 0,44 → 0,44 | 26,5 → 26,5 |
| 56→91 | 137 → 137 | 0,15 → 0,08 | 0,56 → 0,56 | 33,9 → 33,9 |
| 77→105 | 116 → 116 | 0,13 → 0,06 | 0,61 → 0,61 | 36,7 → 36,7 |
| 78→86 | 130 → 130 | 0,14 → 0,07 | 0,49 → 0,49 | 29,6 → 29,6 |
| 78→105 | 71 → 71 | 0,08 → 0,04 | 0,50 → 0,50 | 30,0 → 30,0 |
| 79→91 | 78 → 78 | 0,09 → 0,04 | 0,47 → 0,47 | 28,0 → 28,0 |
| 86→78 | 72 → 72 | 0,08 → 0,04 | 0,43 → 0,43 | 26,0 → 26,0 |
| 86→87 | 132 → 132 | 0,15 → 0,07 | 0,60 → 0,60 | 36,3 → 36,3 |
| 87→56 | 132 → 132 | 0,15 → 0,07 | 0,50 → 0,50 | 29,8 → 29,8 |
| 87→86 | 72 → 72 | 0,08 → 0,04 | 0,54 → 0,54 | 32,4 → 32,4 |
| 91→56 | 76 → 76 | 0,08 → 0,04 | 0,61 → 0,61 | 36,9 → 36,9 |
| 91→79 | 138 → 138 | 0,15 → 0,08 | 0,48 → 0,48 | 29,0 → 29,0 |
| 105→77 | 72 → 72 | 0,08 → 0,04 | 0,53 → 0,53 | 31,6 → 31,6 |
| 105→78 | 128 → 128 | 0,14 → 0,07 | 0,51 → 0,51 | 30,6 → 30,6 |

**Redistribuição:** nenhuma aresta fora das alteradas mudou mais de 0,5 veíc/h (soma de |Δfluxo|: 0,0 veíc/h).

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT 0,00% / 0,00% / -0,02% e ΔK da rede 0,0000 / 0,0000 / +0,0002 (baixa / adotada / alta).

**Classificação:** efeito desprezível.

### S1 — Marginal DF-480 em mão única (binário): remove o sentido de menor fluxo

- **Arquivo:** `cenarios/S1_binario_marginal_df480.json` · resultados em `resultados/S1_binario_marginal_df480/`
- **Família:** sentido
- **Critério de escolha:** mantém o sentido de maior fluxo na situação atual (914 veíc/h somados nas 7 arestas) e remove o oposto (513 veíc/h). A Av. São Francisco, primeira candidata, desconectaria 52 pares OD

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 56→87 | Marginal DF-480 | tertiary | remoção | 1 → — | 900 → — | não | 71 | 0,44 |
| 78→105 | Marginal DF-480 | tertiary | remoção | 1 → — | 900 → — | não | 71 | 0,46 |
| 79→91 | Marginal DF-480 | tertiary | remoção | 1 → — | 900 → — | não | 78 | 0,42 |
| 86→78 | Marginal DF-480 | tertiary | remoção | 1 → — | 900 → — | não | 72 | 0,41 |
| 87→86 | Marginal DF-480 | tertiary | remoção | 1 → — | 900 → — | não | 72 | 0,54 |
| 91→56 | Marginal DF-480 | tertiary | remoção | 1 → — | 900 → — | não | 76 | 0,61 |
| 105→77 | Marginal DF-480 | tertiary | remoção | 1 → — | 900 → — | não | 72 | 0,52 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 351,1 | +466,6 | +2,27 | 0,7026 → 0,7023 | 45,2 → 45,3 | 3,43 → 3,51 | 20 → 20 | 67 → 64 | 2 (< 1e-12) |
| adotada | 476,9 | 487,9 | +654,7 | +2,29 | 0,7001 → 0,6995 | 45,0 → 45,1 | 3,44 → 3,52 | 20 → 20 | 67 → 64 | 4 (< 1e-12) |
| alta | 884,4 | 907,5 | +1.388,4 | +2,62 | 0,6763 → 0,6724 | 43,7 → 43,6 | 3,55 → 3,64 | 26 → 27 | 68 → 65 | 32 (9.7e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 56→87 | 71 → fechada | 0,08 → — | 0,44 → — | 26,5 → — |
| 78→105 | 71 → fechada | 0,08 → — | 0,50 → — | 30,0 → — |
| 79→91 | 78 → fechada | 0,09 → — | 0,47 → — | 28,0 → — |
| 86→78 | 72 → fechada | 0,08 → — | 0,43 → — | 26,0 → — |
| 87→86 | 72 → fechada | 0,08 → — | 0,54 → — | 32,4 → — |
| 91→56 | 76 → fechada | 0,08 → — | 0,61 → — | 36,9 → — |
| 105→77 | 72 → fechada | 0,08 → — | 0,53 → — | 31,6 → — |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 3.339 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 7→22 | primary | 2.413 → 2.505 | +92,4 | 0,72 → 0,69 |
| 57→8 | primary | 1.612 → 1.704 | +92,4 | 0,87 → 0,87 |
| 101→80 | tertiary | 133 → 226 | +92,4 | 0,89 → 0,89 |
| 100→99 | tertiary_link | 98 → 191 | +92,4 | 0,96 → 0,96 |
| 80→100 | tertiary | 156 → 249 | +92,4 | 1,00 → 1,00 |
| 75→74 | tertiary | 65 → 157 | +92,4 | 1,00 → 1,00 |
| 22→101 | tertiary | 150 → 243 | +92,4 | 1,00 → 1,00 |
| 99→75 | tertiary | 161 → 254 | +92,4 | 1,00 → 1,00 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT +2,38% / +2,48% / +5,37% e ΔK da rede -0,0012 / -0,0023 / -0,0142 (baixa / adotada / alta).

**Classificação:** piora robusta.

### S2 — Inverte o acesso 30→7: a entrada na DF-480 vira saída da DF-480

- **Arquivo:** `cenarios/S2_inverter_acesso_df480_30_7.json` · resultados em `resultados/S2_inverter_acesso_df480_30_7/`
- **Família:** sentido
- **Critério de escolha:** 30→7 é a mão única que converge no gargalo 7→22 da DF-480 (415 veíc/h na situação atual)

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 30→7 | sem nome | tertiary | inversão de sentido | 1 | 900 → 900 | não | 415 | 0,80 |

Na inversão, a aresta nova (v→u) mantém comprimento, limite, faixas e velocidade livre; a calibração de gargalo e os dados observados (que valiam para o outro sentido) são descartados.

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 373,8 | +1.826,5 | +8,87 | 0,7026 → 0,6788 | 45,2 → 44,0 | 3,43 → 3,74 | 20 → 20 | 67 → 68 | 2 (< 1e-12) |
| adotada | 476,9 | 519,2 | +2.535,7 | +8,86 | 0,7001 → 0,6763 | 45,0 → 43,9 | 3,44 → 3,75 | 20 → 20 | 67 → 68 | 4 (< 1e-12) |
| alta | 884,4 | 963,0 | +4.719,2 | +8,89 | 0,6763 → 0,6526 | 43,7 → 42,5 | 3,55 → 3,87 | 26 → 26 | 68 → 70 | 26 (9.7e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 30→7 (agora 7→30) | 415 → 0 | 0,46 → 0,00 | 0,96 → 0,97 | 38,4 → 38,7 |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 8.017 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 119→71 | Avenida do Sol | 49 → 463 | +413,9 | 0,60 → 0,59 |
| 36→98 | Avenida do Sol | 45 → 458 | +413,9 | 0,72 → 0,71 |
| 76→119 | Avenida do Sol | 48 → 462 | +413,9 | 0,63 → 0,62 |
| 98→76 | Avenida do Sol | 45 → 459 | +413,8 | 0,77 → 0,76 |
| 79→30 | Avenida São Francisco | 411 → 0 | -411,1 | 0,62 → 0,62 |
| 6→7 | primary | 2.008 → 2.420 | +411,1 | 0,65 → 0,54 |
| 5→6 | primary | 2.071 → 2.482 | +410,5 | 0,75 → 0,64 |
| 71→47 | DF-480 Km 5 1 Pan Bola na Rede | 37 → 447 | +410,0 | 0,59 → 0,58 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT +9,59% / +9,62% / +15,80% e ΔK da rede -0,0286 / -0,0287 / -0,0342 (baixa / adotada / alta).

**Classificação:** piora robusta.

### S3 — Inverte a alça 'Acesso DF-480' (26→21→18): a ligação EPCT sul → DF-480 passa a ser DF-480 → EPCT

- **Arquivo:** `cenarios/S3_inverter_alca_acesso_df480.json` · resultados em `resultados/S3_inverter_alca_acesso_df480/`
- **Família:** sentido
- **Critério de escolha:** alça com 879–888 veíc/h que converge no gargalo 18→4 da DF-480; a inversão do acesso 127→130→103→126 (primeira candidata) desconectaria 54 pares OD

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 26→21 | Acesso DF-480 | trunk_link | inversão de sentido | 1 | 1.200 → 1.200 | não | 879 | 0,41 |
| 21→18 | Acesso DF-480 | trunk_link | inversão de sentido | 1 | 894 → 1.200 | sim | 888 | 0,57 |

Na inversão, a aresta nova (v→u) mantém comprimento, limite, faixas e velocidade livre; a calibração de gargalo e os dados observados (que valiam para o outro sentido) são descartados.

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 347,3 | +236,9 | +1,15 | 0,7026 → 0,7047 | 45,2 → 44,7 | 3,43 → 3,47 | 20 → 17 | 67 → 66 | 1 (9.7e-05) |
| adotada | 476,9 | 484,3 | +441,3 | +1,54 | 0,7001 → 0,7011 | 45,0 → 44,3 | 3,44 → 3,50 | 20 → 18 | 67 → 66 | 4 (< 1e-12) |
| alta | 884,4 | 912,9 | +1.713,0 | +3,23 | 0,6763 → 0,6730 | 43,7 → 42,7 | 3,55 → 3,67 | 26 → 26 | 68 → 69 | 118 (9.9e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 26→21 (agora 21→26) | 879 → 1 | 0,73 → 0,00 | 0,42 → 0,44 | 33,5 → 35,0 |
| 21→18 (agora 18→21) | 888 → 7 | 0,99 → 0,01 | 0,57 → 0,65 | 45,6 → 52,3 |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 9.805 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 18→4 | primary | 2.143 → 1.266 | -877,5 | 0,65 → 0,79 |
| 72→71 | Avenida do Sol | 32 → 901 | +869,7 | 0,41 → 0,36 |
| 17→26 | Estrada Parque Contorno | 1.957 → 1.095 | -861,4 | 0,47 → 0,50 |
| 20→17 | Estrada Parque Contorno | 1.918 → 1.057 | -861,4 | 0,42 → 0,50 |
| 19→72 | Avenida do Sol | 6 → 865 | +859,7 | 0,37 → 0,33 |
| 20→19 | Avenida do Sol | 4 → 864 | +859,7 | 0,61 → 0,54 |
| 4→5 | primary | 2.063 → 1.211 | -852,4 | 0,66 → 0,80 |
| 47→5 | tertiary | 38 → 890 | +851,9 | 0,86 → 0,75 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT +1,63% / +3,06% / +2,99% e ΔK da rede +0,0008 / -0,0023 / -0,0001 (baixa / adotada / alta).

**Classificação:** piora robusta; K e TSTT divergem na demanda baixa, adotada.

### R1 — Fecha a alça 21→18 ('Acesso DF-480'), que converge no gargalo 18→4

- **Arquivo:** `cenarios/R1_fechar_alca_acesso_df480_21_18.json` · resultados em `resultados/R1_fechar_alca_acesso_df480_21_18/`
- **Família:** remocao
- **Critério de escolha:** acesso de maior fluxo (888 veíc/h) que pode ser fechado sem desconectar pares OD e que alimenta um gargalo; o acesso 103→126 à EPCT norte, primeira candidata, desconectaria 47 pares OD

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 21→18 | Acesso DF-480 | trunk_link | remoção | 1 → — | 894 → — | sim | 888 | 0,57 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 347,2 | +230,2 | +1,12 | 0,7026 → 0,7048 | 45,2 → 44,7 | 3,43 → 3,47 | 20 → 17 | 67 → 66 | 1 (9.7e-05) |
| adotada | 476,9 | 484,2 | +437,0 | +1,53 | 0,7001 → 0,7011 | 45,0 → 44,3 | 3,44 → 3,50 | 20 → 20 | 67 → 66 | 4 (< 1e-12) |
| alta | 884,4 | 910,2 | +1.551,8 | +2,92 | 0,6763 → 0,6746 | 43,7 → 42,7 | 3,55 → 3,65 | 26 → 26 | 68 → 69 | 103 (9.9e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 21→18 | 888 → fechada | 0,99 → — | 0,57 → — | 45,6 → — |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 9.703 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 18→4 | primary | 2.143 → 1.260 | -883,7 | 0,65 → 0,79 |
| 72→71 | Avenida do Sol | 32 → 914 | +882,0 | 0,41 → 0,36 |
| 26→21 | Acesso DF-480 | 879 → 13 | -865,9 | 0,42 → 0,44 |
| 4→5 | primary | 2.063 → 1.198 | -864,7 | 0,66 → 0,80 |
| 47→5 | tertiary | 38 → 902 | +864,1 | 0,86 → 0,74 |
| 71→47 | DF-480 Km 5 1 Pan Bola na Rede | 37 → 901 | +864,1 | 0,59 → 0,51 |
| 20→17 | Estrada Parque Contorno | 1.918 → 1.057 | -861,4 | 0,42 → 0,50 |
| 17→26 | Estrada Parque Contorno | 1.957 → 1.095 | -861,4 | 0,47 → 0,50 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT +1,59% / +2,74% / +2,96% e ΔK da rede +0,0009 / -0,0009 / +0,0005 (baixa / adotada / alta).

**Classificação:** piora robusta; K e TSTT divergem na demanda baixa, adotada.

### R2 — Fecha o acesso 30→7 à DF-480

- **Arquivo:** `cenarios/R2_fechar_acesso_df480_30_7.json` · resultados em `resultados/R2_fechar_acesso_df480_30_7/`
- **Família:** remocao
- **Critério de escolha:** acesso (415 veíc/h) que converge no gargalo 7→22 da DF-480; teste de Braess por fechamento de acesso

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 30→7 | sem nome | tertiary | remoção | 1 → — | 900 → — | não | 415 | 0,80 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 373,8 | +1.826,5 | +8,87 | 0,7026 → 0,6788 | 45,2 → 44,0 | 3,43 → 3,74 | 20 → 20 | 67 → 68 | 2 (< 1e-12) |
| adotada | 476,9 | 519,2 | +2.535,7 | +8,86 | 0,7001 → 0,6763 | 45,0 → 43,9 | 3,44 → 3,75 | 20 → 20 | 67 → 68 | 4 (< 1e-12) |
| alta | 884,4 | 963,0 | +4.719,2 | +8,89 | 0,6763 → 0,6526 | 43,7 → 42,5 | 3,55 → 3,87 | 26 → 26 | 68 → 70 | 26 (9.7e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 30→7 | 415 → fechada | 0,46 → — | 0,96 → — | 38,4 → — |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 8.017 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 119→71 | Avenida do Sol | 49 → 463 | +413,9 | 0,60 → 0,59 |
| 36→98 | Avenida do Sol | 45 → 458 | +413,9 | 0,72 → 0,71 |
| 76→119 | Avenida do Sol | 48 → 462 | +413,9 | 0,63 → 0,62 |
| 98→76 | Avenida do Sol | 45 → 459 | +413,8 | 0,77 → 0,76 |
| 79→30 | Avenida São Francisco | 411 → 0 | -411,1 | 0,62 → 0,62 |
| 6→7 | primary | 2.008 → 2.420 | +411,1 | 0,65 → 0,54 |
| 5→6 | primary | 2.071 → 2.482 | +410,5 | 0,75 → 0,64 |
| 71→47 | DF-480 Km 5 1 Pan Bola na Rede | 37 → 447 | +410,0 | 0,59 → 0,58 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT +9,59% / +9,62% / +15,80% e ΔK da rede -0,0286 / -0,0287 / -0,0342 (baixa / adotada / alta).

**Classificação:** piora robusta.

### R3 — Fecha a alça 11→63 (retorno EPCT sul → EPCT norte), de K observado 0,16

- **Arquivo:** `cenarios/R3_fechar_alca_11_63.json` · resultados em `resultados/R3_fechar_alca_11_63/`
- **Família:** remocao
- **Critério de escolha:** alça com K observado baixo e 138 veíc/h que se junta à EPCT norte em 63, logo antes do gargalo 63→102; a alça 67→66, primeira candidata, desconectaria 16 pares OD

**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):

| Aresta | Via | Classe | Alteração | Faixas | Capacidade | Gargalo | Fluxo atual (veíc/h) | K observado |
|---|---|---|---|---|---|---|---|---|
| 11→63 | sem nome | trunk_link | remoção | 1 → — | 1.200 → — | não | 138 | 0,16 |

**Resultados por nível de demanda** (situação atual → cenário):

| Demanda | TSTT atual (veíc·h) | TSTT cenário (veíc·h) | ΔTSTT (veíc·min) | ΔTSTT (%) | K da rede | Vel. média (km/h) | Tempo médio (min) | Arestas V/C>1 | Arestas K<0,5 | Iterações (gap) |
|---|---|---|---|---|---|---|---|---|---|---|
| baixa | 343,4 | 351,8 | +504,3 | +2,45 | 0,7026 → 0,6990 | 45,2 → 44,6 | 3,43 → 3,52 | 20 → 20 | 67 → 66 | 1 (8.3e-05) |
| adotada | 476,9 | 488,7 | +706,0 | +2,47 | 0,7001 → 0,6963 | 45,0 → 44,5 | 3,44 → 3,53 | 20 → 20 | 67 → 66 | 1 (8.4e-05) |
| alta | 884,4 | 907,1 | +1.365,4 | +2,57 | 0,6763 → 0,6716 | 43,7 → 43,0 | 3,55 → 3,64 | 26 → 27 | 68 → 67 | 28 (9.7e-05) |

**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):

| Aresta | Fluxo (veíc/h) | V/C | K modelado | Velocidade (km/h) |
|---|---|---|---|---|
| 11→63 | 138 → fechada | 0,12 → — | 0,36 → — | 28,8 → — |

**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: 2.824 veíc/h):

| Aresta | Via | Fluxo atual → cenário (veíc/h) | Δ (veíc/h) | K modelado |
|---|---|---|---|---|
| 66→132 | Estrada Parque Contorno | 2.021 → 2.161 | +139,7 | 0,33 → 0,29 |
| 132→133 | Estrada Parque Contorno | 2.022 → 2.162 | +139,7 | 0,30 → 0,26 |
| 133→63 | Estrada Parque Contorno | 2.025 → 2.164 | +139,7 | 0,37 → 0,31 |
| 17→26 | Estrada Parque Contorno | 1.957 → 2.082 | +125,8 | 0,47 → 0,47 |
| 26→13 | Estrada Parque Contorno | 1.090 → 1.214 | +124,1 | 0,62 → 0,62 |
| 15→16 | trunk_link | 199 → 323 | +124,1 | 0,57 → 0,57 |
| 13→15 | Estrada Parque Contorno | 1.255 → 1.379 | +124,1 | 0,76 → 0,76 |
| 64→66 | Estrada Parque Contorno | 953 → 1.068 | +114,4 | 0,47 → 0,45 |

**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT +2,70% / +2,72% / +2,52% e ΔK da rede -0,0041 / -0,0045 / -0,0047 (baixa / adotada / alta).

**Classificação:** piora robusta.

## 5. Teste do paradoxo de Braess: varreduras aresta por aresta

Comando: `python scripts/frank_wolfe.py --varredura-remocao --varredura-faixa` (e o mesmo com `--alpha 0.8 --beta 4.7`).

- **Varredura de remoção:** fecha cada uma das 235 arestas de carro, uma por vez, e resolve o equilíbrio nos três níveis. **Braess = fechar reduz o TSTT.** Fechamentos que desconectariam algum par OD não podem ser avaliados (a demanda fixa ficaria sem rota) e são registrados à parte.
- **Varredura de faixa:** soma 1 faixa a cada aresta, uma por vez (mesma regra dos cenários F). **Braess = ampliar aumenta o TSTT** (paradoxo da capacidade).
- Todo candidato com gap 10⁻⁴ é refeito, junto com a situação atual, com gap 10⁻⁷ e até 20.000 iterações, para separar efeito real de erro de convergência.

| Varredura | Demanda | Alterações avaliadas | Desconectam pares OD | Candidatos (gap 10⁻⁴) | Braess confirmados | ΔTSTT mín. (%) | ΔTSTT mediano (%) | ΔTSTT máx. (%) |
|---|---|---|---|---|---|---|---|---|
| varredura_faixa | baixa | 235 | 0 | 0 | 0 | -4,700 | 0,000 | 0,00 |
| varredura_faixa | adotada | 235 | 0 | 0 | 0 | -4,694 | 0,000 | 0,00 |
| varredura_faixa | alta | 235 | 0 | 0 | 0 | -4,590 | 0,000 | 0,00 |
| varredura_remocao | baixa | 166 | 69 | 0 | 0 | 0,000 | +0,386 | +65,76 |
| varredura_remocao | adotada | 166 | 69 | 0 | 0 | 0,000 | +0,385 | +98,27 |
| varredura_remocao | alta | 166 | 69 | 0 | 0 | 0,000 | +0,376 | +678,43 |
| varredura_remocao_a0.8_b4.7 | baixa | 166 | 69 | 2 | 0 | 0,000 | +0,395 | +159,03 |
| varredura_remocao_a0.8_b4.7 | adotada | 166 | 69 | 2 | 0 | 0,000 | +0,401 | +603,93 |
| varredura_remocao_a0.8_b4.7 | alta | 166 | 69 | 2 | 2 | -0,724 | +0,338 | +6.623,56 |

**Convergência nas varreduras:** `varredura_remocao`: 5 de 498 equilíbrios pararam no teto de 500 iterações com gap acima de 10⁻⁴ (maior gap 2.1e-03); servem para ordenar o efeito, e qualquer candidato a Braess é refeito com gap 10⁻⁷. `varredura_remocao_a0.8_b4.7`: 15 de 498 equilíbrios pararam no teto de 500 iterações com gap acima de 10⁻⁴ (maior gap 5.4e-03); servem para ordenar o efeito, e qualquer candidato a Braess é refeito com gap 10⁻⁷.

**Casos de Braess confirmados em `varredura_remocao_a0.8_b4.7`:**

| Aresta | Via | Demanda | ΔTSTT confirmado (veíc·min) | ΔTSTT (%) |
|---|---|---|---|---|
| 6→30 | tertiary | alta | -507,700 | -0,7255 |
| 30→79 | Avenida São Francisco | alta | -503,700 | -0,7198 |

**Arestas cujo fechamento mais aumenta o TSTT** (`varredura_remocao`, demanda adotada):

| Aresta | Via | Classe | ΔTSTT (%) |
|---|---|---|---|
| 25→0 | Estrada Parque Contorno | trunk | +98,27 |
| 133→63 | Estrada Parque Contorno | trunk | +69,17 |
| 26→13 | Estrada Parque Contorno | trunk | +58,57 |
| 15→12 | Estrada Parque Contorno | trunk | +57,54 |
| 14→18 | — | primary | +46,73 |
| 11→9 | Estrada Parque Contorno | trunk | +32,19 |
| 8→16 | — | primary | +20,02 |
| 102→126 | Estrada Parque Contorno | trunk | +17,46 |
| 64→66 | Estrada Parque Contorno | trunk | +17,24 |
| 82→81 | — | tertiary_link | +11,03 |

**Arestas cujo faixa extra mais reduz o TSTT** (`varredura_faixa`, demanda adotada):

| Aresta | Via | Classe | ΔTSTT (%) |
|---|---|---|---|
| 63→102 | Estrada Parque Contorno | trunk | -4,69 |
| 126→60 | Estrada Parque Contorno | trunk | -1,59 |
| 132→133 | Estrada Parque Contorno | trunk | -1,57 |
| 5→6 | — | primary | -1,43 |
| 7→22 | — | primary | -1,18 |
| 60→62 | Estrada Parque Contorno | trunk | -0,34 |
| 61→10 | Estrada Parque Contorno | trunk | -0,32 |
| 133→63 | Estrada Parque Contorno | trunk | -0,30 |
| 20→17 | Estrada Parque Contorno | trunk | -0,29 |
| 102→126 | Estrada Parque Contorno | trunk | -0,28 |

## 6. Leitura dos resultados

1. **Ampliar os gargalos do corredor é o que mais reduz o tempo total.** A faixa extra em todos os gargalos da EPCT norte (F1) reduz o TSTT em 9,2% na demanda adotada; só os 5 trechos antes do trevo (C0, caso da V1) já reduzem 8,6%. Na DF-480 (F3) a redução é de 3,6% e na EPCT sul (F2), de 1,5%. Os ganhos variam pouco entre os níveis de demanda porque a capacidade efetiva dos gargalos escala com o fator de expansão (research/problemas_do_modelo.md, problema 3): a robustez nesses trechos é, em parte, construída pela calibração.
2. **K baixo não é sinônimo de falta de capacidade.** As alças com K observado < 0,25 (F4) e as coletoras Av. São Francisco (F5) e Marginal DF-480 (F6) quase não respondem a uma faixa extra (ΔTSTT de -0,11%, -0,01% e 0,00% na demanda adotada): a lentidão delas vem de geometria, conversões e cruzamentos (já embutidos no tempo de fluxo livre medido de madrugada), não do volume. Isso responde em parte à RQ2: o grafo enriquecido separa a lentidão causada por volume da lentidão estrutural.
3. **Fechar ou inverter acessos sempre piora o sistema neste recorte.** Fechar o acesso 30→7 à DF-480 (R2) aumenta o TSTT em 8,9%; inverter esse acesso (S2) dá exatamente o mesmo resultado, porque o sentido novo não tem demanda: a inversão equivale a um fechamento. Fechar a alça 11→63 (R3) custa 2,5% e o binário na Marginal DF-480 (S1), 2,3%.
4. **Há divergência entre K e TSTT, o indício de Braess definido no artigo.** Fechar a alça 21→18 (R1) ou invertê-la (S3) piora o TSTT (+1,53% e +1,54% na demanda adotada), mas o K da rede sobe (+0,0010 e +0,0010). Cerca de 864 veíc/h saem da alça e da DF-480 e passam a usar a Avenida do Sol e a ligação DF-480 Km 5 (19→72, 20→19, 47→5, 71→47, 72→71), vias de limite 40–60 km/h onde se anda a 20–32 km/h. A quilometragem total quase não muda (21.486 → 21.461 veíc·km), mas os trechos aliviados da DF-480 e da EPCT ganham muito K (18→4: 0,65 → 0,79; 20→17: 0,42 → 0,50), enquanto o desvio, por ter limite baixo, perde pouco K mesmo sendo lento em km/h. Como o K é normalizado pelo limite de cada via, ele favorece empurrar tráfego para vias de limite baixo; o TSTT, que mede tempo absoluto, registra a piora. Na demanda alta o sinal do ΔK se inverte. É uma evidência concreta de que uma métrica de fluidez normalizada pelo limite da via (K) pode apontar melhora enquanto o sistema perde tempo, que é a tese central do trabalho.
5. **Paradoxo de Braess: ausente com os parâmetros-base, presente em poucos casos sob a sensibilidade.** Com a = 0,15 e b = 4, nenhuma alteração de uma aresta reduziu o TSTT ao fechar ou o aumentou ao ampliar (166 fechamentos avaliados por nível; os 69 restantes desconectariam pares OD). Com a = 0,8 e b = 4,7 (`varredura_remocao_a0.8_b4.7`), houve 2 caso(s) confirmado(s): fechar 6→30 (tertiary) na demanda alta: -0,73% (gap da confirmação 2e-06); fechar 30→79 (Avenida São Francisco) na demanda alta: -0,72% (gap da confirmação 2e-06). Em 6→30 e 30→79 (o mesmo percurso DF-480 → Av. São Francisco), cerca de 200 veíc/h usam o gargalo 5→6 da DF-480 para chegar ao acesso; fechando-o, cerca de 180 veíc/h saem do 5→6 (≈3.700 → 3.500 veíc/h, tempo 2,84 → 2,57 min) e vão para a Av. do Sol e a Marginal DF-480. A economia dos que ficam no gargalo supera o tempo extra dos desviados: é a externalidade clássica do paradoxo. O efeito depende dos parâmetros e da demanda: nos níveis baixo e adotado, e em todos os níveis com os parâmetros-base, os mesmos fechamentos aumentam o TSTT. A raridade do paradoxo é coerente com o predomínio do tráfego de passagem (86% das viagens) e com a pouca escolha de rota (46,5% da demanda com alternativa). O algoritmo reproduz o paradoxo quando ele existe (rede de Braess de 1968 no `--teste`: o TSTT sobe de 498 para 552 ao abrir a ponte).
6. **Quais vias importam para o sistema.** A varredura de remoção funciona como um mapa de criticidade: fechar 25→0 (EPCT sul, antes do trevo), 133→63 (EPCT norte) ou 14→18 (DF-480) aumenta o TSTT em dezenas de por cento, enquanto a mediana dos fechamentos avaliáveis fica abaixo de 0,4%.

