# Grafo viário de Brasília com OSMnx

Módulo que baixa a malha viária do OpenStreetMap e entrega um grafo **NetworkX**
pronto para roteamento e análise de tráfego.

## Instalação

```bash
pip install osmnx
```

Isso puxa junto `networkx`, `geopandas`, `shapely`, `pyproj`, `requests` e `matplotlib`.
Versões usadas aqui: OSMnx 2.1.1, NetworkX 3.5, Python 3.13.

## Uso

```bash
python grafo_brasilia/build_graph.py --lugar "Brasilia, Brazil" --nome brasilia_df_drive --via-bbox
python grafo_brasilia/build_graph.py --lugar "Plano Piloto, Brasilia, Distrito Federal, Brazil" --nome plano_piloto_drive
python grafo_brasilia/exemplos_networkx.py --grafo plano_piloto_drive
```

Opções úteis do `build_graph.py`:

| flag | efeito |
|---|---|
| `--tipo drive\|drive_service\|all\|bike\|walk` | filtro de vias (padrão `drive`) |
| `--consolidar 15` | funde interseções num raio de 15 m (pista dupla vira 1 nó) |
| `--via-bbox` | baixa pelo retângulo envolvente e recorta depois — **use para o DF inteiro** |
| `--max-area 900` | tamanho (km²) de cada requisição ao Overpass |
| `--timeout 180` | segundos de espera por resposta antes de tentar de novo (inteiro) |
| `--overpass URL` | forçar um servidor Overpass (base, sem `/interpreter`) |
| `--sem-rate-limit` | não consultar `/status` antes de cada requisição |
| `--sem-plot` | pula a renderização do PNG |

### Quando o download falha

O Overpass é um serviço público e cai com frequência. O script já trata os
principais modos de falha:

- **`ResponseStatusCodeError: 400 Bad Request`, reclamando do atributo `timeout`** —
  o OSMnx injeta `settings.requests_timeout` dentro da própria consulta
  (`[out:json][timeout:180]`). Se você atribuir um **float**, sai
  `[timeout:180.0]` e o Overpass rejeita. Sempre `int`.
- **Área grande demora minutos por consulta ou estoura o timeout** — o
  `graph_from_place` manda o contorno administrativo inteiro no filtro
  `(poly:"...")`, e o do DF tem centenas de vértices. Use `--via-bbox`: baixa o
  retângulo envolvente (4 vértices, responde em segundos) e recorta o polígono
  localmente com `truncate_graph_polygon`. Mesmo resultado, ordens de grandeza
  mais rápido.
- **Parece travado sem mensagem nenhuma** — antes de cada requisição o OSMnx
  consulta `/status` para respeitar a fila do servidor. Espelhos que não
  implementam esse endpoint fazem ele dormir a cada consulta. `--sem-rate-limit`
  desliga isso; use **apenas** em espelho e com poucas requisições.

- **`ConnectionError` / conexão derrubada** — a consulta era grande demais.
  Diminua `--max-area`.
- **`ConnectTimeout` repetido no mesmo processo** — o OSMnx fixa o IP do servidor
  (para respeitar o controle de fila do Overpass), e o round-robin do
  `overpass-api.de` às vezes entrega um IP fora do ar. Insistir no mesmo processo
  não adianta; o script troca de espelho depois de 2 tentativas. Para forçar:
  `--overpass https://maps.mail.ru/osm/tools/overpass/api`.

Trocar de servidor **invalida o cache** do servidor anterior (a chave do cache é a
URL completa), então só troque quando o principal estiver realmente fora.

## O que sai em `saida/`

| arquivo | conteúdo |
|---|---|
| `*.graphml` | o grafo inteiro; recarregue com `ox.load_graphml(...)` |
| `*.gpkg` | nós e arestas como camadas GIS (abre direto no QGIS) |
| `*_arestas.csv` | tabela de trechos: `u, v, name, ref, highway, lanes, maxspeed, length, speed_kph, travel_time` |
| `*.png` | figura da rede |
| `*_stats.json` | estatísticas descritivas (`ox.stats.basic_stats` + conectividade) |

O cache do Overpass fica em `cache_osm/`. Rodar o mesmo comando de novo é
instantâneo e não bate no servidor. Ambas as pastas estão no `.gitignore`.

## Modelo de dados

Um `MultiDiGraph`:

- **nó** = interseção ou fim de via. O `id` do nó **é** o `osmid` do OpenStreetMap.
  Atributos: `x` (longitude), `y` (latitude), `street_count`.
- **aresta** = trecho de via entre duas interseções, com direção.
  Atributos: `osmid`, `name`, `ref`, `highway`, `oneway`, `lanes`, `maxspeed`,
  `length` (metros), `geometry` (a curva real), e — adicionados por este script —
  `speed_kph` e `travel_time` (segundos em fluxo livre).
- **Di** porque mão única importa: `G[u][v]` existir não implica `G[v][u]`.
- **Multi** porque duas vias distintas podem ligar o mesmo par de nós; por isso
  arestas têm chave tripla `(u, v, key)`.

Vias curvas **não** viram vários nós: a curvatura fica na `geometry` da aresta.
É o que o `simplify=True` faz, e é o motivo de o grafo ser utilizável.

## Armadilhas

1. **Conectividade.** ~4% dos nós ficam fora do maior componente fortemente
   conexo (mão única mal mapeada). Antes de rotear em massa:
   `G = ox.truncate.largest_component(G, strongly=True)`.
2. **`lanes` e `maxspeed` faltam** na maioria das vias locais. `add_edge_speeds`
   imputa a média por classe de via — bom o bastante para tempo livre, fraco para
   capacidade. Estime capacidade por `highway` + `lanes` quando existir.
3. **Distância em graus.** O grafo vem em WGS84 (EPSG:4326). Para qualquer conta
   em metros/área, projete antes: `ox.projection.project_graph(G)`.
4. **`consolidate_intersections` troca os IDs dos nós** — eles deixam de ser `osmid`.
   Só use se for medir topologia; para casar com dados externos, mantenha os osmid.
5. **Overpass derruba consultas grandes.** Daí o fatiamento (`--max-area`) e o
   retry automático no `build_graph.py`.

## Visualizar o grafo em outra ferramenta

O `.graphml` que o OSMnx grava serve para **recarregar no OSMnx**, não para
desenhar no Gephi/yEd/Cytoscape. Quatro motivos, todos verificáveis no arquivo:

| Problema | Medido no `plano_piloto_drive.graphml` |
|---|---|
| Todas as arestas com o mesmo `id` (a chave do MultiDiGraph) | 14.285 arestas, **2 valores distintos de id**: `0` (14.215×) e `1` (70×) |
| Nenhum atributo declarado numérico | **0 de 28** chaves são `double`/`long`; `x` e `y` saem como `string` |
| Coordenadas em graus, não em metros | o Plano Piloto inteiro cabe em 0,13 × 0,16 unidades |
| `geometry` (WKT da curva) infla o arquivo sem servir para desenho | 1,6 MB de 9,0 MB (18%); no DF, 15,2 MB de 109,6 MB |

O XSD oficial do GraphML declara `<xs:unique name="edge_id_unique">`, então o id
repetido é violação de esquema: importadores tolerantes (networkx, igraph) ignoram,
importadores estritos rejeitam ou deduplicam.

**Os ids dos nós estão corretos** — são os osmid reais (`34557099`…), 7.747 valores
distintos para 7.747 nós. O `0` que aparece é o id da *aresta*.

```bash
python grafo_brasilia/exportar_para_render.py --grafo plano_piloto_drive
```

| Saída | Para |
|---|---|
| `*_render.graphml` | Gephi, yEd, Cytoscape — ids válidos, `x`/`y` numéricos **em metros** |
| `*_arestas.geojson` | QGIS, kepler.gl — geometria real das vias |
| `*_mapa.html` | qualquer navegador — canvas interativo, sem dependências |

No DF inteiro use `--so-arteriais` (o grafo completo gera 77 MB de GraphML, demais
para o heap padrão do Gephi) ou `--simplificar 12` para aliviar a geometria.

O mapa HTML desenha as 200.339 vias do DF em **94 ms por quadro** — um único
`<canvas>` com um `Path2D` por classe de via, em vez de um elemento por aresta.
É por aí que ferramentas de grafo genéricas falham: elas fazem layout de força em
14 mil arestas quando as posições já são conhecidas.

## Ligação com o resto do projeto

A tag `ref` das arestas traz o código da rodovia (`DF-003`, `BR-060`). O
`Roads.csv` do DETRAN usa códigos no formato `001EDF0010`, cujos 3 primeiros
dígitos são o número da DF. Normalizando os dois lados dá para pendurar o TMD
e o fluxo do `flow.csv` direto na aresta do grafo — veja as seções 10 e 11 de
`exemplos_networkx.py`.
