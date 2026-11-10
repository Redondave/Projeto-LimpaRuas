# Projeto LimpaRuas

Otimização de intervenções viárias no trevo entre a EPCT (DF-001), a EPIP e a
DF-480, no Gama (DF), com base no índice de desempenho de velocidade (K) e nos
efeitos sistêmicos sobre a rede. A malha é modelada como um grafo direcionado
(OpenStreetMap), a demanda vem de trajetórias reais (TomTom O/D Analysis,
expandida com contagens do DER-DF), as velocidades vêm do TomTom Traffic Stats,
e o equilíbrio de Wardrop é calculado pelo algoritmo de Frank-Wolfe.

O artigo está em [`artigo/artigoFinal.tex`](artigo/artigoFinal.tex) e a
documentação, em [`research/`](research/README.md).

## Principais resultados

Variação do tempo total de viagem do sistema (TSTT) na demanda adotada, em
relação à situação atual (detalhes em
[`research/relatorio_cenarios.md`](research/relatorio_cenarios.md)):

| Cenário | Intervenção | ΔTSTT |
|---|---|---|
| C0 | +1 faixa em 5 trechos saturados da EPCT norte | −8,6% |
| R3 | fechamento da alça de retorno 11→63 | +2,5% |
| S3 | inversão da alça de acesso à DF-480 | +1,5% (com o K da rede subindo) |

Com os parâmetros de referência da função de atraso, nenhuma via fechada ou
ampliada produziu o paradoxo de Braess; ele aparece em dois fechamentos apenas
sob os parâmetros da análise de sensibilidade e demanda alta. O painel
interativo com todos os 13 cenários está em
[`resultados/painel.html`](resultados/painel.html) (abrir no navegador).

## Estrutura

```
artigo/        artigo final (LaTeX) e a figura que ele usa
dados/
  osm/         download do OpenStreetMap da área de estudo
  tomtom/      respostas da TomTom: O/D Analysis e Traffic Stats (pico e madrugada)
  der/         trechos rodoviários do DER-DF e contagens de tráfego (flow.csv, fora do git)
  grafo/       grafos de estudo; o *_atributos.graphml é o que o Frank-Wolfe usa
  tabelas/     matriz OD, faixas e limites, velocidades e K por aresta
cenarios/      cenários de intervenção em JSON (C0, F1–F6, S1–S3, R1–R3)
resultados/    saídas do Frank-Wolfe por rodada, varreduras de Braess, figuras e painel
research/      metodologia, relatório de cenários, problemas do modelo e histórico
scripts/       pipeline em Python
```

## Como reproduzir

Da raiz do repositório, na ordem:

```bash
python scripts/expand_graph.py               # grafo de estudo (offline, a partir de dados/osm/)
python scripts/build_od_matrix.py --offline  # matriz OD (usa dados/der/flow.csv)
python scripts/faixas_limite.py              # faixas e limite de velocidade por aresta
python scripts/velocidades_traffic_stats.py  # velocidades de pico e madrugada, K por aresta
python scripts/enrich_graph.py               # grafo atribuído: capacidade, t0 e checagens
python scripts/frank_wolfe.py --teste        # valida o algoritmo em redes com solução conhecida
python scripts/gerar_cenarios.py             # gera cenarios/*.json a partir de critérios sobre o grafo
python scripts/frank_wolfe.py --todos        # situação atual + todos os cenários, nos 3 níveis de demanda
python scripts/frank_wolfe.py --alpha 0.8 --beta 4.7 --todos          # sensibilidade da função de atraso
python scripts/frank_wolfe.py --varredura-remocao --varredura-faixa   # teste de Braess, aresta por aresta (demorado)
python scripts/visualizar_resultados.py      # resultados/painel.html e resultados/figuras/
python scripts/relatorio_cenarios.py         # research/relatorio_cenarios.md
```

`python scripts/mapping.py` só precisa ser rodado se a planilha de trechos do
DER-DF (`dados/der/Roads.csv`) mudar. O `build_od_matrix.py` sem `--offline`
baixa a análise da TomTom de novo e lê a chave da variável `TOMTOM_API_KEY`.

Dependências (Python 3.13): `osmnx networkx geopandas shapely pyproj pandas numpy scipy matplotlib requests`.

## Contagens de tráfego do DER-DF

As contagens calibram o fator de expansão da matriz OD. O arquivo tem cerca de
146 MB e não fica no git:

1. Baixar o CSV de **julho/2026** (o mesmo mês da TomTom) em [Dados de Fluxo Veicular](https://www.dados.df.gov.br/pt/dataset#/volume-diario-de-trafego-trechos-rodoviarios), no portal de dados abertos do DF.
2. Salvar como `dados/der/flow.csv`.

A versão de abril/2026, usada na primeira calibração, pode ficar ao lado como
`dados/der/flow_abril_2026.csv` (também ignorada pelo git).

## 👥 Autores

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/Redondave">
        <img src="https://github.com/Redondave.png?size=100" width="100px;" alt="Photo of Davi Brasileiro"/>
        <br />
        <sub>
          <b>Davi Brasileiro</b>
        </sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/daviggalvao">
        <img src="https://github.com/daviggalvao.png?size=100" width="100px;" alt="Photo of Davi Galvão"/>
        <br />
        <sub>
          <b>Davi Galvão</b>
        </sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Leo3107">
        <img src="https://github.com/Leo3107.png?size=100" width="100px;" alt="Photo of Leonardo Mileo"/>
        <br />
        <sub>
          <b>Leonardo Mileo</b>
        </sub>
      </a>
    </td>
     <td align="center">
      <a href="https://github.com/Liferoijrm">
        <img src="https://github.com/Liferoijrm.png?size=100" width="100px;" alt="Photo of Pedro Marcinoni"/>
        <br />
        <sub>
          <b>Pedro Marcinoni</b>
        </sub>
      </a>
    </td>
  </tr>
</table>
