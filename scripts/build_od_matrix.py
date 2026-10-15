"""
Constroi a matriz OD no-a-no do grafo do Gama a partir da analise "flow matrix"
do TomTom O/D Analysis, pronta para o Frank-Wolfe (Passo 3 do research_plan.md).

Desenho da analise no portal: uma regiao (caixa pequena) sobre cada no do grafo.
Para viagens que comecam ou terminam fora das regioes, a TomTom atribui como
origem a PRIMEIRA regiao em que a viagem entrou e como destino a ULTIMA da qual
saiu. Ou seja: a "visao OD" do resultado ja e a matriz de entrada -> saida do
subgrafo, que e exatamente o que a alocacao precisa.

Formato do resultado (analysisVersion 2), cada link e:
    [origem, destino, via, externalEndsCode, contagem_normalizada]
    externalEndsCode: 0 ambas as pontas dentro das regioes | 1 comecou fora
                      2 terminou fora | 3 comecou e terminou fora (passagem)
    links com via == destino formam a visao OD e somam 100;
    os demais detalham por quais regioes (via) as viagens passaram.

Os valores sao percentuais, mas todos sao multiplos inteiros de 100/N, onde N e
o numero de viagens da amostra. Isso permite recuperar a contagem absoluta de
viagens TomTom por par. Para virar veiculos/hora reais, a amostra e expandida
por um fator calibrado contra os contadores do DETRAN (flow.csv) no mesmo
horario. Os pontos de calibracao sao encontrados automaticamente (ver
pontos_de_calibracao), entao o script funciona para qualquer analise nova.

Uso (da raiz do repositorio):
    set TOMTOM_API_KEY=...                      (Windows)  /  export TOMTOM_API_KEY=...
    python scripts/build_od_matrix.py           # baixa a analise "Gama Final" e gera tudo
    python scripts/build_od_matrix.py --offline # reusa o bruto salvo, sem API
    python scripts/build_od_matrix.py --fator 15  # forca o fator de expansao

Saidas (padrao):
    Tables/od_tomtom_gama_final_bruto.json   resposta da TomTom (metadados, regioes, links)
    Tables/matriz_od_final.json              matriz no-a-no em veic/h + calibracao + validacao
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import requests
from shapely import wkt
from shapely.geometry import LineString, Point, shape

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]

# ---------------- CONFIGURACAO ----------------
ANALISE_ID = "6604531297533426895"          # "Gama Final" no portal TomTom O/D (134 regioes)
GRAFO = RAIZ / "cache/gama_drive_expanded.graphml"
AREA_OSM = RAIZ / "cache/gama_area_estudo_osm.graphml"          # geometria real das arestas
CRS = "EPSG:31983"                           # SIRGAS 2000 / UTM 23S, o mesmo do grafo
FLOW = RAIZ / "flow.csv"
TRECHOS = RAIZ / "Tables/trechos_com_coordenadas.csv"
BRUTO = RAIZ / "Tables/od_tomtom_gama_final_bruto.json"
MATRIZ = RAIZ / "Tables/matriz_od_final.json"

API = "https://api.tomtom.com/origindestination/1/analysis/flowmatrix"
DIST_MAX_NO_M = 50     # caixa fora da rede: aceita o no mais proximo ate esta distancia
TOL_NO_M = 5           # no a menos disso da caixa conta como "dentro" (caixa desenhada a mao)
SEM_CARRO = {"busway"}  # classes de via que carro nao usa: fora do teste de caminho

# calibracao automatica
DIST_TRECHO_M = 60     # caixa ate esta distancia da linha do trecho do DER
COS_SENTIDO = 0.7      # |cos| minimo entre o rumo da pista e o do trecho para definir o sentido


# ---------------------------------------------------------------------------
# 1. Download (ou leitura do bruto salvo)
# ---------------------------------------------------------------------------
def baixar(analise_id: str, destino: Path) -> dict:
    chave = os.environ.get("TOMTOM_API_KEY")
    if not chave:
        sys.exit("Defina TOMTOM_API_KEY, ou rode com --offline para usar o bruto salvo.")

    def get(url):
        sep = "&" if "?" in url else "?"
        r = requests.get(f"{url}{sep}key={chave}", timeout=180)
        r.raise_for_status()
        return r.json()

    meta = get(f"{API}/{analise_id}")
    if meta["analysisInfo"]["status"] != "ACCEPTED":
        sys.exit(f"Analise ainda nao terminou: status {meta['analysisInfo']['status']}")
    regioes = get(meta["regionsLink"])
    viagens = get(meta["results"][0]["tripsWholeResultLink"])

    info = dict(meta["analysisInfo"])
    for campo in ("owner", "developerId"):       # identificadores da conta TomTom
        info.pop(campo, None)
    bruto = {"analysisInfo": info, "results": meta["results"],
             "regions": regioes, "links": viagens["links"]}
    destino.write_text(json.dumps(bruto, ensure_ascii=False), encoding="utf-8")
    print(f"Bruto salvo em {destino}")
    return bruto


# ---------------------------------------------------------------------------
# 2. Geometria: arestas do grafo e caixas da TomTom
# ---------------------------------------------------------------------------
def geometria_arestas(G: nx.DiGraph, F: nx.MultiDiGraph) -> dict:
    fpos = {n: (float(d["x"]), float(d["y"])) for n, d in F.nodes(data=True)}
    geoms = {}
    for u, v, d in G.edges(data=True):
        ou, ov = d["original_u"], d["original_v"]
        geom = None
        for fd in (F[ou][ov].values() if F.has_edge(ou, ov) else []):
            if "geometry" in fd:
                geom = wkt.loads(fd["geometry"])
                break
        geoms[(u, v)] = geom or LineString([fpos[ou], fpos[ov]])
    return geoms


def caixas_tomtom(regioes: list) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        [{"indice": i, "nome": f["properties"]["name"], "geometry": shape(f["geometry"])}
         for i, f in enumerate(regioes)], crs=4326).to_crs(CRS)


# ---------------------------------------------------------------------------
# 3. Regiao TomTom -> no do grafo
# ---------------------------------------------------------------------------
def mapear_regioes(G: nx.DiGraph, caixas: gpd.GeoDataFrame, geoms: dict) -> pd.DataFrame:
    """
    Regra, em ordem:
      1. a caixa contem um no do grafo (com folga de TOL_NO_M) -> esse no;
      2. a caixa cai no meio de uma aresta:
         - mao unica u->v: v. Nao ha cruzamento no meio, entao quem passa pela
           caixa chega em v;
         - mao dupla (a caixa pega u->v e v->u): a ponta mais proxima;
      3. caixa fora da rede -> no mais proximo, ate DIST_MAX_NO_M.
    """
    pos = {n: Point(float(d["x"]), float(d["y"])) for n, d in G.nodes(data=True)}
    linhas = []
    for c in caixas.itertuples():
        dist_nos = {n: p.distance(c.geometry) for n, p in pos.items()}
        dentro = sorted((n for n, d in dist_nos.items() if d <= TOL_NO_M), key=dist_nos.get)
        sobre = [(u, v) for (u, v), g in geoms.items() if g.intersects(c.geometry)]
        if dentro:
            no = dentro[0]
            regra = ("no dentro da caixa" if dist_nos[no] == 0
                     else f"no a {dist_nos[no]:.1f} m da caixa")
        elif sobre:
            u, v = sobre[0]
            if (v, u) in sobre:
                no = min((u, v), key=dist_nos.get)
                regra = f"caixa sobre a via de mao dupla {u}<->{v}, ponta mais proxima"
            else:
                no, regra = v, f"caixa sobre a aresta {u}->{v}"
        else:
            no = min(dist_nos, key=dist_nos.get)
            if dist_nos[no] > DIST_MAX_NO_M:
                sys.exit(f"Regiao {c.indice} ({c.nome}) esta a {dist_nos[no]:.0f} m do no mais proximo.")
            regra = f"no mais proximo ({dist_nos[no]:.0f} m)"
        linhas.append({"indice": c.indice, "nome": c.nome, "no": no,
                       "osmid": G.nodes[no]["original_osmid"], "regra": regra})
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# 4. Amostra TomTom: percentuais -> contagens de viagens
# ---------------------------------------------------------------------------
def contagens(links: list) -> tuple[pd.DataFrame, int]:
    L = pd.DataFrame(links, columns=["o", "d", "via", "ext", "pct"])
    unidade = L["pct"].min()
    n = L["pct"] / unidade
    if (n - n.round()).abs().max() > 1e-6:
        sys.exit("Os percentuais nao sao multiplos de 100/N: nao da para recuperar contagens.")
    L["n"] = n.round().astype(int)
    total = int(round(100 / unidade))
    od = L[L["via"] == L["d"]]
    assert od["n"].sum() == total, "visao OD nao fecha com o total da amostra"
    return L, total


def dias_uteis(info: dict) -> int:
    faixa = info["timeDefinition"]["dateRanges"][0]
    ini = dt.date.fromisoformat(faixa["startDate"])
    fim = dt.date.fromisoformat(faixa["endDate"])
    nomes = {"MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4,
             "SATURDAY": 5, "SUNDAY": 6}
    validos = {nomes[d] for d in faixa["daysOfWeek"]}
    excl = {dt.date.fromisoformat(x) for x in faixa.get("exclusions", [])}
    dias = [ini + dt.timedelta(k) for k in range((fim - ini).days + 1)]
    return sum(1 for d in dias if d.weekday() in validos and d not in excl)


# ---------------------------------------------------------------------------
# 5. Fator de expansao: amostra TomTom -> veiculos reais
# ---------------------------------------------------------------------------
def rodovias(texto) -> set:
    return set(re.findall(r"(?:DF|BR)-\d{3}", str(texto or "")))


def pontos_de_calibracao(G, F, mapa, caixas) -> pd.DataFrame:
    """
    Uma caixa serve para calibrar quando mede o fluxo de UMA pista de rodovia
    que tem contador do DETRAN:
      - a caixa esta sobre um no da pista: chega uma aresta e sai outra da mesma
        rodovia (tag ref do OSM), alinhadas. O no pode ter alca chegando
        (convergencia) ou saindo (divergencia); nesse caso a caixa mede a pista
        depois da alca ou antes dela, e isso fica registrado em "tipo_no";
      - a caixa nao encosta em via que nao saia do proprio no (pista oposta,
        rua paralela);
      - o no fica a ate DIST_TRECHO_M de um trecho do DER dessa rodovia;
      - o sentido (crescente = inicio -> fim do trecho) sai do rumo da pista
        comparado ao rumo local do trecho.
    """
    trechos = pd.read_csv(TRECHOS, dtype=str)
    for c in ["lat_inicio", "lon_inicio", "lat_meio", "lon_meio", "lat_fim", "lon_fim"]:
        trechos[c] = trechos[c].astype(float)
    linhas_der = gpd.GeoDataFrame(
        trechos[["CÓDIGO-DO-TRECHO", "snv_rodovia"]],
        geometry=[LineString([(r.lon_inicio, r.lat_inicio), (r.lon_meio, r.lat_meio),
                              (r.lon_fim, r.lat_fim)]) for r in trechos.itertuples()],
        crs=4326).to_crs(CRS)

    fpos = {n: (float(d["x"]), float(d["y"])) for n, d in F.nodes(data=True)}
    outras = gpd.GeoDataFrame(
        [{"u": u, "v": v, "geometry": wkt.loads(d["geometry"]) if "geometry" in d
          else LineString([fpos[u], fpos[v]])} for u, v, d in F.edges(data=True)], crs=CRS)
    pos = {n: np.array([float(d["x"]), float(d["y"])]) for n, d in G.nodes(data=True)}

    pontos = []
    for r in mapa.itertuples():
        if not r.regra.startswith("no "):
            continue
        n = r.no
        osm = G.nodes[n]["original_osmid"]
        caixa = caixas.geometry[r.indice]
        tocadas = outras[outras.intersects(caixa)]
        if not ((tocadas["u"] == osm) | (tocadas["v"] == osm)).all():
            continue                                    # pega outra via: nao e limpa
        # par (entrada, saida) da mesma rodovia, alinhado = a pista passa pelo no
        pista = None
        for a in G.predecessors(n):
            for b in G.successors(n):
                if a == b:
                    continue
                refs = rodovias(G[a][n].get("ref")) & rodovias(G[n][b].get("ref"))
                d1, d2 = pos[n] - pos[a], pos[b] - pos[n]
                alinh = float(d1 @ d2 / np.linalg.norm(d1) / np.linalg.norm(d2))
                if refs and alinh > COS_SENTIDO and (pista is None or alinh > pista[3]):
                    pista = (a, b, refs, alinh)
        if pista is None:
            continue
        a, b, refs, _ = pista
        n_ent, n_sai = G.in_degree(n), G.out_degree(n)
        tipo = ("passagem" if (n_ent, n_sai) == (1, 1) else
                "convergencia" if n_sai == 1 else "divergencia" if n_ent == 1 else "cruzamento")
        if tipo == "cruzamento":
            continue
        ent, sai = [a], [b]
        p = Point(*pos[n])
        cand = linhas_der[linhas_der["snv_rodovia"].isin(refs)]
        if cand.empty:
            continue
        dist = cand.geometry.distance(p)
        if dist.min() > DIST_TRECHO_M:
            continue
        trecho = cand.loc[dist.idxmin()]
        # rumo local do trecho: segmento da linha do DER mais perto do no
        coords = np.array(trecho.geometry.coords)
        seg = min(range(len(coords) - 1),
                  key=lambda i: LineString(coords[i:i + 2]).distance(p))
        dir_trecho = coords[seg + 1] - coords[seg]
        dir_pista = pos[sai[0]] - pos[ent[0]]
        cos = float(dir_trecho @ dir_pista / np.linalg.norm(dir_trecho) / np.linalg.norm(dir_pista))
        if abs(cos) < COS_SENTIDO:
            continue
        pontos.append({"regiao": int(r.indice), "nome": r.nome, "no": n, "tipo_no": tipo,
                       "trecho": trecho["CÓDIGO-DO-TRECHO"], "rodovia": trecho["snv_rodovia"],
                       "sentido": "crescente" if cos > 0 else "decrescente",
                       "dist_trecho_m": round(float(dist.min()), 1)})
    return pd.DataFrame(pontos)


def volumes_detran(trechos: set, hora: int) -> tuple[pd.DataFrame, str]:
    """Mediana dos dias uteis com as 96 janelas de 15 min e volume plausivel."""
    fl = pd.read_csv(FLOW, encoding="utf-8-sig",
                     usecols=["trecho", "sentido", "dia", "intervalo", "porte", "fluxo"])
    t = fl[(fl["porte"] == "total") & fl["trecho"].isin(trechos)].copy()
    t["dia"] = pd.to_datetime(t["dia"])
    t = t[t["dia"].dt.dayofweek < 5]
    dia = t.groupby(["trecho", "sentido", "dia"]).agg(
        janelas=("intervalo", "nunique"), total=("fluxo", "sum")).reset_index()
    validos = dia[(dia["janelas"] == 96) & (dia["total"] >= 100)]
    t = t.merge(validos[["trecho", "sentido", "dia"]])
    t = t[t["intervalo"].str[:2].astype(int) == hora]
    volume = t.groupby(["trecho", "sentido", "dia"])["fluxo"].sum()
    periodo = f"{t['dia'].min():%Y-%m-%d} a {t['dia'].max():%Y-%m-%d}" if len(t) else ""
    return volume.groupby(["trecho", "sentido"]).agg(["median", "count"]), periodo


def calibrar(pontos: pd.DataFrame, passagens_h: pd.Series, hora: int) -> pd.DataFrame:
    """Um fator por (trecho, sentido): volume DETRAN da mesma hora dividido pela
    mediana das viagens TomTom/h nas caixas limpas daquela pista."""
    if pontos.empty or not FLOW.exists():
        return pd.DataFrame()
    tipico, periodo = volumes_detran(set(pontos["trecho"]), hora)
    pontos = pontos.assign(tomtom_viagens_h=pontos["regiao"].map(passagens_h).fillna(0))
    linhas = []
    for (trecho, sentido), grupo in pontos.groupby(["trecho", "sentido"]):
        if (trecho, sentido) not in tipico.index:
            continue                                     # contador sem dia valido nesse sentido
        tt = float(grupo["tomtom_viagens_h"].median())
        if tt <= 0:
            continue
        det = float(tipico.loc[(trecho, sentido), "median"])
        linhas.append({"trecho": trecho, "rodovia": grupo["rodovia"].iloc[0], "sentido": sentido,
                       "regioes": grupo["regiao"].tolist(), "nos": grupo["no"].tolist(),
                       "tipos_no": grupo["tipo_no"].tolist(),
                       "detran_veic_h": round(det),
                       "dias_detran": int(tipico.loc[(trecho, sentido), "count"]),
                       "periodo_detran": periodo,
                       "tomtom_viagens_h": round(tt, 1),
                       "tomtom_viagens_h_faixa": [round(float(grupo["tomtom_viagens_h"].min()), 1),
                                                  round(float(grupo["tomtom_viagens_h"].max()), 1)],
                       "fator_implicito": round(det / tt, 2)})
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analise", default=ANALISE_ID)
    ap.add_argument("--offline", action="store_true", help="usar o bruto salvo, sem chamar a API")
    ap.add_argument("--fator", type=float, default=None, help="forcar o fator de expansao")
    ap.add_argument("--grafo", type=Path, default=GRAFO, help="GraphML de destino da matriz")
    ap.add_argument("--bruto", type=Path, default=BRUTO, help="JSON bruto da TomTom (lido/gravado)")
    ap.add_argument("--saida", type=Path, default=MATRIZ, help="caminho da matriz gerada")
    args = ap.parse_args()

    if args.offline:
        bruto = json.loads(args.bruto.read_text(encoding="utf-8"))
    else:
        bruto = baixar(args.analise, args.bruto)
    info = bruto["analysisInfo"]
    janela = info["timeDefinition"]["timeRanges"][0]
    hora = int(janela["startTime"][:2])
    if janela["endTime"] != f"{hora + 1:02d}:00":
        sys.exit("A calibracao supoe uma janela de exatamente 1 hora cheia.")

    G = nx.read_graphml(args.grafo)
    fonte = AREA_OSM
    F = nx.read_graphml(fonte)
    if not all(F.has_edge(d["original_u"], d["original_v"]) for _, _, d in G.edges(data=True)):
        sys.exit(f"{fonte.name} nao cobre todas as arestas de {args.grafo.name}")
    caixas = caixas_tomtom(bruto["regions"])
    mapa = mapear_regioes(G, caixas, geometria_arestas(G, F))
    sem_regiao = sorted(set(G) - set(mapa["no"]), key=int)
    divididos = mapa.groupby("no")["indice"].apply(list)
    divididos = {n: v for n, v in divididos.items() if len(v) > 1}
    nomes_rep = mapa["nome"].value_counts()
    nomes_rep = sorted(nomes_rep[nomes_rep > 1].index)

    L, total = contagens(bruto["links"])
    dias = dias_uteis(info)
    reg2no = dict(zip(mapa["indice"], mapa["no"]))

    # passagens: viagens distintas que cruzaram cada caixa (drill-down por via)
    passagens = L.groupby("via")["n"].sum()
    passagens_h = passagens / dias

    pontos = pontos_de_calibracao(G, F, mapa, caixas)
    cal = calibrar(pontos, passagens_h, hora)
    if args.fator is not None:
        fator, metodo = args.fator, "informado na linha de comando"
    elif len(cal):
        fator = float(cal["fator_implicito"].median())
        metodo = (f"mediana dos fatores de {len(cal)} pistas com contador DETRAN "
                  f"({len(pontos)} caixas limpas)")
    else:
        sys.exit("Nenhum ponto de calibracao encontrado (ou sem flow.csv): rode com --fator.")

    # grafo para o teste de caminho: sem vias que carro nao usa
    carro = G.copy()
    carro.remove_edges_from([(u, v) for u, v, d in G.edges(data=True)
                             if d.get("highway") in SEM_CARRO])

    # visao OD -> pares de nos
    od = L[L["via"] == L["d"]].copy()
    od["no_o"], od["no_d"] = od["o"].map(reg2no), od["d"].map(reg2no)
    por_cod = od.groupby("ext")["n"].sum()
    intra = od[od["no_o"] == od["no_d"]]["n"].sum()
    pares = (od[od["no_o"] != od["no_d"]].groupby(["no_o", "no_d"])["n"].sum().reset_index())
    pares["tem_caminho"] = [nx.has_path(carro, a, b) for a, b in zip(pares["no_o"], pares["no_d"])]
    sem_caminho = pares[~pares["tem_caminho"]]
    pares = pares[pares["tem_caminho"]]

    osm = nx.get_node_attributes(G, "original_osmid")

    def registro(r):
        return {"origem": r.no_o, "destino": r.no_d,
                "origem_osmid": osm[r.no_o], "destino_osmid": osm[r.no_d],
                "viagens_amostra": int(r.n),
                "veic_h": round(r.n / dias * fator, 2)}

    regioes = []
    for r in mapa.itertuples():
        regioes.append({"indice": int(r.indice), "nome": r.nome, "no": r.no, "osmid": r.osmid,
                        "regra": r.regra, "passagens_amostra": int(passagens.get(r.indice, 0)),
                        "passagens_veic_h": round(passagens_h.get(r.indice, 0) * fator, 1)})

    lim = cal["fator_implicito"] if len(cal) else pd.Series([fator])
    saida = {
        "descricao": (f"Matriz OD no-a-no do grafo {args.grafo.resolve().relative_to(RAIZ).as_posix()}, "
                      "em veiculos/hora no pico de dia util, para alocacao de trafego (Frank-Wolfe)."),
        "unidade": "veiculos/hora",
        "ids_dos_nos": "ids do GraphML (nx.read_graphml devolve strings); *_osmid = no do OpenStreetMap",
        "vias_sem_carro": sorted(SEM_CARRO),
        "fonte": {
            "produto": "TomTom O/D Analysis - flow matrix",
            "analise_id": info["id"], "nome": info["name"],
            "periodo": f"{info['timeDefinition']['dateRanges'][0]['startDate']} a "
                       f"{info['timeDefinition']['dateRanges'][0]['endDate']}",
            "janela": f"{janela['startTime']}-{janela['endTime']} ({info['timeDefinition']['zoneId']})",
            "condicao_janela": info["timeDefinition"].get("timeRangeCondition"),
            "mapa": info.get("map"),
            "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        },
        "amostra": {
            "viagens_tomtom": total,
            "dias_uteis": dias,
            "viagens_por_tipo_de_ponta": {
                "ambas_dentro": int(por_cod.get(0, 0)), "comecou_fora": int(por_cod.get(1, 0)),
                "terminou_fora": int(por_cod.get(2, 0)), "passagem": int(por_cod.get(3, 0))},
            "descartadas_mesmo_no": int(intra),
            "descartadas_sem_caminho_no_grafo": int(sem_caminho["n"].sum()),
            "alocaveis": int(pares["n"].sum()),
        },
        "cobertura": {
            "nos_sem_regiao": sem_regiao,
            "nos_com_mais_de_uma_regiao": divididos,
            "nomes_de_regiao_repetidos": nomes_rep,
        },
        "fator_expansao": {
            "adotado": round(fator, 2),
            "metodo": metodo,
            "faixa_para_sensibilidade": [round(float(lim.min()), 2), round(float(lim.max()), 2)],
            "observacoes": cal.to_dict(orient="records"),
        },
        "pares": [registro(r) for r in pares.sort_values("n", ascending=False).itertuples()],
        "pares_sem_caminho": [registro(r) for r in sem_caminho.sort_values("n", ascending=False).itertuples()],
        "regioes": regioes,
    }
    args.saida.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Mapeamento: {len(mapa)} regioes -> {mapa['no'].nunique()} nos | "
          f"nos sem regiao: {sem_regiao} | nos com 2+ regioes: {divididos}")
    print(mapa["regra"].str.replace(r"[\d.]+", "#", regex=True).value_counts().to_string())
    print(f"\nAmostra: {total} viagens TomTom em {dias} dias uteis | "
          f"{100 * por_cod.get(3, 0) / total:.1f}% de passagem")
    print(f"Descartadas: {intra} no mesmo no, {sem_caminho['n'].sum()} sem caminho no grafo")
    if len(cal):
        print(f"\nCalibracao ({len(pontos)} caixas limpas em rodovia com contador):")
        print(cal[["trecho", "rodovia", "sentido", "regioes", "detran_veic_h", "tomtom_viagens_h",
                   "fator_implicito"]].to_string(index=False))
    print(f"\nFator adotado: {fator:.2f} ({metodo})")
    print(f"Pares OD alocaveis: {len(pares)} | demanda total: "
          f"{pares['n'].sum() / dias * fator:,.0f} veic/h")
    print(f"Matriz salva em {args.saida}")


if __name__ == "__main__":
    main()
