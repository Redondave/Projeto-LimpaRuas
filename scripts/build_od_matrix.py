"""
Constroi a matriz OD no-a-no do grafo do Gama a partir da analise "flow matrix"
do TomTom O/D Analysis, pronta para o Frank-Wolfe (Passo 3 do research_plan.md).

Desenho da analise no portal: uma regiao (caixa pequena) sobre cada no do grafo
de 30 nos. Para viagens que comecam ou terminam fora das regioes (~95% aqui), a
TomTom atribui como origem a PRIMEIRA regiao em que a viagem entrou e como
destino a ULTIMA da qual saiu. Ou seja: a "visao OD" do resultado ja e a matriz
de entrada -> saida do subgrafo, que e exatamente o que a alocacao precisa.

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
horario.

Uso (da raiz do repositorio):
    set TOMTOM_API_KEY=...                      (Windows)  /  export TOMTOM_API_KEY=...
    python scripts/build_od_matrix.py           # baixa a analise e gera tudo
    python scripts/build_od_matrix.py --offline # reusa o bruto salvo, sem API
    python scripts/build_od_matrix.py --fator 15  # forca o fator de expansao
    python scripts/build_od_matrix.py --offline --grafo cache/gama_drive_expanded.graphml

Saidas:
    Tables/od_tomtom_gama3_bruto.json   resposta da TomTom (metadados, regioes, links)
    Tables/matriz_od_gama3.json         matriz no-a-no em veic/h + calibracao + validacao
"""

import argparse
import datetime as dt
import json
import os
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
ANALISE_ID = "4305589173730324104"          # "Gama 3" no portal TomTom O/D
GRAFO = RAIZ / "cache/gama_drive_sample_30.graphml"
GRAFO_COMPLETO = RAIZ / "cache/gama_drive_projected.graphml"   # so para a geometria das arestas
AREA_OSM = RAIZ / "cache/gama_area_estudo_osm.graphml"          # idem, inclui o que fica fora da RA
CRS = "EPSG:31983"                           # SIRGAS 2000 / UTM 23S, o mesmo do grafo
FLOW = RAIZ / "flow.csv"
SAIDA_BRUTO = RAIZ / "Tables/od_tomtom_gama3_bruto.json"
SAIDA_MATRIZ = RAIZ / "Tables/matriz_od_gama3.json"

API = "https://api.tomtom.com/origindestination/1/analysis/flowmatrix"
DIST_MAX_NO_M = 50     # caixa fora da rede: aceita o no mais proximo ate esta distancia
TOL_NO_M = 5           # no a menos disso da caixa conta como "dentro" (caixa desenhada a mao)

# Pontos de calibracao: caixa TomTom sobre UMA pista de rodovia com contador do
# DETRAN. O sentido foi definido comparando o rumo da pista coberta pela caixa
# com o rumo do trecho do DER (inicio -> fim = crescente).
#   "limpa": a caixa cobre so aquela pista, sem alca nem rua lateral
CALIBRACAO = [
    {"regiao": 28, "trecho": "480EDF0030", "sentido": "decrescente",
     "via": "DF-480 sentido Gama", "qualidade": "limpa"},
    {"regiao": 10, "trecho": "001EDF0250", "sentido": "decrescente",
     "via": "EPCT sentido EPIA", "qualidade": "limpa"},
    {"regiao": 11, "trecho": "480EDF0030", "sentido": "crescente",
     "via": "DF-480 sentido EPCT", "qualidade": "caixa pega tambem uma alca"},
    {"regiao": 7, "trecho": "065EDF0010", "sentido": "crescente",
     "via": "EPIP chegando ao trevo", "qualidade": "caixa fora da geometria OSM; sentido inferido pela OD"},
    {"regiao": 9, "trecho": "065EDF0010", "sentido": "decrescente",
     "via": "EPIP saindo do trevo", "qualidade": "caixa fora da geometria OSM; sentido inferido pela OD"},
]


# ---------------------------------------------------------------------------
# 1. Download (ou leitura do bruto salvo)
# ---------------------------------------------------------------------------
def baixar(analise_id: str) -> dict:
    chave = os.environ.get("TOMTOM_API_KEY")
    if not chave:
        sys.exit("Defina TOMTOM_API_KEY, ou rode com --offline para usar o bruto salvo.")

    def get(url):
        sep = "&" if "?" in url else "?"
        r = requests.get(f"{url}{sep}key={chave}", timeout=120)
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
    SAIDA_BRUTO.write_text(json.dumps(bruto, ensure_ascii=False), encoding="utf-8")
    print(f"Bruto salvo em {SAIDA_BRUTO.relative_to(RAIZ)}")
    return bruto


# ---------------------------------------------------------------------------
# 2. Regiao TomTom -> no do grafo
# ---------------------------------------------------------------------------
def mapear_regioes(G: nx.DiGraph, regioes: list, fonte_geometria: Path) -> pd.DataFrame:
    """
    Regra, em ordem:
      1. a caixa contem um no do grafo (com folga de TOL_NO_M) -> esse no;
      2. a caixa cai no meio de uma aresta u->v -> v. A aresta e de mao unica e
         nao tem cruzamento no meio, entao quem passa pela caixa chega em v;
      3. caixa fora da rede -> no mais proximo, ate DIST_MAX_NO_M.
    """
    F = nx.read_graphml(fonte_geometria)
    pos = {n: Point(float(d["x"]), float(d["y"])) for n, d in G.nodes(data=True)}
    fpos = {n: (float(d["x"]), float(d["y"])) for n, d in F.nodes(data=True)}

    arestas = []
    for u, v, d in G.edges(data=True):
        ou, ov = d["original_u"], d["original_v"]
        geom = None
        for fd in (F[ou][ov].values() if F.has_edge(ou, ov) else []):
            if "geometry" in fd:
                geom = wkt.loads(fd["geometry"])
                break
        arestas.append((u, v, geom or LineString([fpos[ou], fpos[ov]])))

    caixas = gpd.GeoDataFrame(
        [{"indice": i, "nome": f["properties"]["name"], "geometry": shape(f["geometry"])}
         for i, f in enumerate(regioes)], crs=4326).to_crs(CRS)

    linhas = []
    for c in caixas.itertuples():
        dist_nos = {n: p.distance(c.geometry) for n, p in pos.items()}
        dentro = sorted((n for n, d in dist_nos.items() if d <= TOL_NO_M), key=dist_nos.get)
        sobre = [(u, v) for u, v, g in arestas if g.intersects(c.geometry)]
        if dentro:
            no = dentro[0]
            regra = ("no dentro da caixa" if dist_nos[no] == 0
                     else f"no a {dist_nos[no]:.1f} m da caixa")
        elif sobre:
            u, v = sobre[0]
            no, regra = v, f"caixa sobre a aresta {u}->{v}"
        else:
            no = min(pos, key=lambda n: pos[n].distance(c.geometry))
            dist = pos[no].distance(c.geometry)
            if dist > DIST_MAX_NO_M:
                sys.exit(f"Regiao {c.indice} ({c.nome}) esta a {dist:.0f} m do no mais proximo.")
            regra = f"no mais proximo ({dist:.0f} m)"
        linhas.append({"indice": c.indice, "nome": c.nome, "no": no,
                       "osmid": G.nodes[no]["original_osmid"], "regra": regra})
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# 3. Amostra TomTom: percentuais -> contagens de viagens
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
# 4. Fator de expansao: amostra TomTom -> veiculos reais
# ---------------------------------------------------------------------------
def calibrar(passagens_h: pd.Series, hora: int) -> pd.DataFrame:
    """Compara, em cada ponto de CALIBRACAO, o volume DETRAN da mesma hora
    (mediana dos dias uteis completos) com as viagens TomTom/h na caixa."""
    fl = pd.read_csv(FLOW, encoding="utf-8-sig",
                     usecols=["trecho", "sentido", "dia", "intervalo", "porte", "fluxo"])
    alvo = {c["trecho"] for c in CALIBRACAO}
    t = fl[(fl["porte"] == "total") & fl["trecho"].isin(alvo)].copy()
    t["dia"] = pd.to_datetime(t["dia"])
    t = t[t["dia"].dt.dayofweek < 5]
    dia = t.groupby(["trecho", "sentido", "dia"]).agg(
        janelas=("intervalo", "nunique"), total=("fluxo", "sum")).reset_index()
    validos = dia[(dia["janelas"] == 96) & (dia["total"] >= 100)]
    t = t.merge(validos[["trecho", "sentido", "dia"]])
    t = t[t["intervalo"].str[:2].astype(int) == hora]
    volume = t.groupby(["trecho", "sentido", "dia"])["fluxo"].sum()
    tipico = volume.groupby(["trecho", "sentido"]).agg(["median", "count"])
    periodo = f"{t['dia'].min():%Y-%m-%d} a {t['dia'].max():%Y-%m-%d}"

    linhas = []
    for c in CALIBRACAO:
        chave = (c["trecho"], c["sentido"])
        tt = float(passagens_h.get(c["regiao"], 0.0))
        if chave not in tipico.index or tt == 0:
            continue
        det = float(tipico.loc[chave, "median"])
        linhas.append({**c, "detran_veic_h": round(det), "dias_detran": int(tipico.loc[chave, "count"]),
                       "periodo_detran": periodo, "tomtom_viagens_h": round(tt, 1),
                       "fator_implicito": round(det / tt, 2)})
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analise", default=ANALISE_ID)
    ap.add_argument("--offline", action="store_true", help="usar o bruto salvo, sem chamar a API")
    ap.add_argument("--fator", type=float, default=None, help="forcar o fator de expansao")
    ap.add_argument("--grafo", type=Path, default=GRAFO, help="GraphML de destino da matriz")
    ap.add_argument("--saida", type=Path, default=None, help="caminho da matriz gerada")
    args = ap.parse_args()

    if args.offline:
        bruto = json.loads(SAIDA_BRUTO.read_text(encoding="utf-8"))
    else:
        bruto = baixar(args.analise)
    info = bruto["analysisInfo"]
    janela = info["timeDefinition"]["timeRanges"][0]
    hora = int(janela["startTime"][:2])
    if janela["endTime"] != f"{hora + 1:02d}:00":
        sys.exit("A calibracao supoe uma janela de exatamente 1 hora cheia.")

    G = nx.read_graphml(args.grafo)
    # geometria real das arestas: a area baixada cobre tudo; o grafo do Gama so o que e da RA
    fonte = AREA_OSM if AREA_OSM.exists() else GRAFO_COMPLETO
    if not all(fonte == AREA_OSM or d["original_u"] in nx.read_graphml(fonte)
               for _, _, d in G.edges(data=True)):
        sys.exit(f"{fonte.name} nao cobre todas as arestas de {args.grafo.name}")
    mapa = mapear_regioes(G, bruto["regions"], fonte)
    saida_matriz = args.saida or SAIDA_MATRIZ
    print("\nRegiao TomTom -> no do grafo")
    print(mapa[["indice", "nome", "no", "regra"]].to_string(index=False))

    L, total = contagens(bruto["links"])
    dias = dias_uteis(info)
    reg2no = dict(zip(mapa["indice"], mapa["no"]))

    # passagens: viagens distintas que cruzaram cada caixa (drill-down por via)
    passagens = L.groupby("via")["n"].sum()
    passagens_h = passagens / dias

    cal = calibrar(passagens_h, hora) if FLOW.exists() else pd.DataFrame()
    if args.fator is not None:
        fator, metodo = args.fator, "informado na linha de comando"
    elif len(cal):
        fator = float(cal["fator_implicito"].median())
        metodo = f"mediana dos fatores implicitos em {len(cal)} pontos de calibracao"
    else:
        sys.exit("Sem flow.csv para calibrar: rode com --fator.")

    # visao OD -> pares de nos
    od = L[L["via"] == L["d"]].copy()
    od["no_o"], od["no_d"] = od["o"].map(reg2no), od["d"].map(reg2no)
    por_cod = od.groupby("ext")["n"].sum()
    intra = od[od["no_o"] == od["no_d"]]["n"].sum()
    pares = (od[od["no_o"] != od["no_d"]].groupby(["no_o", "no_d"])["n"].sum().reset_index())
    pares["tem_caminho"] = [nx.has_path(G, a, b) for a, b in zip(pares["no_o"], pares["no_d"])]
    sem_caminho = pares[~pares["tem_caminho"]]
    pares = pares[pares["tem_caminho"]]

    osm = nx.get_node_attributes(G, "original_osmid")

    def registro(r):
        return {"origem": r.no_o, "destino": r.no_d,
                "origem_osmid": osm[r.no_o], "destino_osmid": osm[r.no_d],
                "viagens_amostra": int(r.n),
                "veic_h": round(r.n / dias * fator, 1)}

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
    saida_matriz.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nAmostra: {total} viagens TomTom em {dias} dias uteis | "
          f"{100 * por_cod.get(3, 0) / total:.1f}% de passagem")
    print(f"Descartadas: {intra} no mesmo no, {sem_caminho['n'].sum()} sem caminho no grafo")
    if len(cal):
        print("\nCalibracao (DETRAN veic/h / TomTom viagens/h):")
        print(cal[["regiao", "via", "trecho", "sentido", "detran_veic_h", "tomtom_viagens_h",
                   "fator_implicito", "qualidade"]].to_string(index=False))
    print(f"\nFator adotado: {fator:.2f} ({metodo})")
    print(f"Pares OD alocaveis: {len(pares)} | demanda total: "
          f"{pares['n'].sum() / dias * fator:,.0f} veic/h")
    print(f"Matriz salva em {saida_matriz}")


if __name__ == "__main__":
    main()
