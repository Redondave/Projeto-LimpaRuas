# -*- coding: utf-8 -*-
"""
Constroi o grafo do Sistema Rodoviario do DF (SRDF) a partir das tabelas do
projeto - e nao da malha urbana inteira do OpenStreetMap.

    no     = entroncamento (ponta de trecho do DER-DF)
    aresta = trecho do DER-DF em um sentido de circulacao

Cada trecho vira DUAS arestas dirigidas: "crescente" (sentido do km, da ponta
inicial para a final da geometria) e "decrescente". E a mesma convencao das
contagens do DETRAN (coluna `sentido` do flow.csv), o que permite pendurar o
volume medido direto na aresta certa.

Entradas (relativas a raiz do repositorio):
    Tables/trechos_com_coordenadas.csv   geometria dos trechos (mapping.py)
    Tables/tomtom_flow_consolidado.csv   velocidades TomTom (api-caller.py)
    Tables/Speeds.csv                    radares do DER com limite no ponto
    flow.csv                             contagens do DETRAN, 15 min

Saidas (grafo_rodoviario/saida/):
    grafo_srdf.graphml     DiGraph com atributos numericos (abre no Gephi/igraph)
    arestas_srdf.csv       uma linha por aresta dirigida
    nos_srdf.csv           uma linha por entroncamento
    limpeza_trechos.csv    decisao de limpeza tomada para cada trecho, e por que
    mapa_srdf.png          figura de conferencia

Uso:
    python grafo_rodoviario/construir_grafo.py
"""

import re
import sys
from collections import Counter
from math import cos, radians
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = Path(__file__).resolve().parent / "saida"

TOL_NO_M = 50            # pontas de trecho a menos disso sao o mesmo entroncamento
HORAS_PICO = (7, 18)     # picos medidos no flow.csv (dias uteis de abril/2026)

# Faixas por sentido e capacidade por faixa: ESTIMATIVAS GROSSEIRAS, so para o
# diagnostico V/C. A tabela do DER nao informa numero de faixas; a proxima etapa
# e trazer `lanes` do OpenStreetMap ou levantar manualmente nos corredores.
FAIXAS_POR_SITUACAO = {"DUP": 2, "EOD": 1, "PAV": 1, "EOP": 1, "IMP": 1}
CAP_POR_FAIXA = {"DUP": 1800, "EOD": 1400, "PAV": 1400, "EOP": 800, "IMP": 600}


# --------------------------------------------------------------------------- #
# 1. Trechos + limpeza
# --------------------------------------------------------------------------- #
def carregar_trechos() -> pd.DataFrame:
    df = pd.read_csv(RAIZ / "Tables/trechos_com_coordenadas.csv", dtype=str)
    df = df.rename(columns={"CÓDIGO-DO-TRECHO": "codigo", "SITUAÇÃO-FÍSICA": "situacao",
                            "EXTENSÃO(km)": "extensao_km"})
    for c in ["lat_inicio", "lon_inicio", "lat_fim", "lon_fim", "extensao_geom_km"]:
        df[c] = df[c].astype(float)
    df["extensao_km"] = pd.to_numeric(df["extensao_km"], errors="coerce")
    df["extensao_declarada_km"] = df["extensao_km"]
    sem = ~(df["extensao_km"] > 0)
    df.loc[sem, "extensao_km"] = df.loc[sem, "extensao_geom_km"].round(2)
    # TMD usa ponto como separador de MILHAR ("28.673" = 28 673 veic/dia).
    # Lido como float, viraria 28,673 - erro de 1000x.
    df["tmd_der"] = pd.to_numeric(df["TMD"].str.replace(".", "", regex=False),
                                  errors="coerce")
    return df


def limpar_trechos(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica as regras de limpeza e devolve (trechos mantidos, relatorio)."""
    decisao, motivo = [], []
    codigos = set(df.codigo)
    coincidente = df["TRECHO-COINCIDENTE-DISTRITAL"].fillna("-").str.strip()

    for _, r in df.iterrows():
        par = coincidente.loc[_]
        if r.situacao == "PLA":
            decisao.append("remover"); motivo.append("trecho planejado, nao existe fisicamente")
        elif par != "-" and par in codigos and r.codigo > par:
            # mesmo leito fisico cadastrado sob duas rodovias: mantem so um,
            # senao o grafo ganha uma aresta paralela fantasma e dobra a capacidade
            decisao.append("remover"); motivo.append(f"superposto a {par} (mesmo leito)")
        else:
            if not (r.extensao_declarada_km > 0):
                decisao.append("manter"); motivo.append("extensao declarada zero/ausente: usada a da geometria")
                continue
            rel = r.extensao_geom_km / r.extensao_declarada_km
            if not (0.6 <= rel <= 1.6):
                decisao.append("manter"); motivo.append(f"ALERTA: geometria {rel:.2f}x a extensao declarada")
            elif r.situacao == "IMP":
                decisao.append("manter"); motivo.append("nao pavimentado: fora da analise de trafego")
            else:
                decisao.append("manter"); motivo.append("")

    rel = df.assign(decisao=decisao, motivo=motivo)[
        ["codigo", "snv_rodovia", "situacao", "extensao_km", "extensao_geom_km",
         "decisao", "motivo", "TRECHO-INÍCIO", "TRECHO-FINAL"]]
    return df[np.array(decisao) == "manter"].copy(), rel


# --------------------------------------------------------------------------- #
# 2. Nos: agrupar pontas de trecho
# --------------------------------------------------------------------------- #
def agrupar_pontas(df: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    kx, ky = 111_320 * cos(radians(-15.8)), 110_574          # graus -> metros no DF
    pontos = np.array([p for _, r in df.iterrows()
                       for p in ((r.lon_inicio * kx, r.lat_inicio * ky),
                                 (r.lon_fim * kx, r.lat_fim * ky))])
    pai = list(range(len(pontos)))

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a

    grade = {}
    for i, (x, y) in enumerate(pontos):
        cx, cy = int(x // TOL_NO_M), int(y // TOL_NO_M)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grade.get((cx + dx, cy + dy), []):
                    if (x - pontos[j][0]) ** 2 + (y - pontos[j][1]) ** 2 <= TOL_NO_M ** 2:
                        pai[raiz(i)] = raiz(j)
        grade.setdefault((cx, cy), []).append(i)

    grupos = [raiz(i) for i in range(len(pontos))]
    ids = {g: k for k, g in enumerate(dict.fromkeys(grupos))}
    no_da_ponta = np.array([ids[g] for g in grupos])

    # nome do entroncamento: texto mais frequente nas pontas que caem nele
    textos = [t for _, r in df.iterrows() for t in (r["TRECHO-INÍCIO"], r["TRECHO-FINAL"])]
    lonlat = [p for _, r in df.iterrows()
              for p in ((r.lon_inicio, r.lat_inicio), (r.lon_fim, r.lat_fim))]
    nos = []
    for k in range(len(ids)):
        idx = np.where(no_da_ponta == k)[0]
        nome = Counter(re.sub(r"\s+", " ", str(textos[i])).strip() for i in idx).most_common(1)[0][0]
        nos.append({"no": k, "lon": np.mean([lonlat[i][0] for i in idx]),
                    "lat": np.mean([lonlat[i][1] for i in idx]),
                    "nome": nome, "n_pontas": len(idx)})
    return no_da_ponta.reshape(-1, 2), pd.DataFrame(nos)


# --------------------------------------------------------------------------- #
# 3. Atributos observados
# --------------------------------------------------------------------------- #
def limite_por_rodovia() -> dict:
    """
    Speeds.csv e a lista de RADARES do DER: o limite no ponto do radar, que
    inclui marginais e travessias a 40-50 km/h. Nao e o limite do trecho.
    Melhor aproximacao disponivel: mediana dos radares da propria rodovia,
    sem os de via marginal. O rotulo da rodovia vem normalizado porque a
    extracao do PDF gerou lixo como "VIA DEDF-003".
    """
    sp = pd.read_csv(RAIZ / "Tables/Speeds.csv", encoding="utf-8-sig")
    sp["v"] = sp["VELOCIDADE"].str.extract(r"(\d+)").astype(float)
    sp["rodovia"] = sp["RODOVIA"].str.extract(r"((?:DF|BR)-\d{3})")
    sp = sp[~sp["SENTIDO"].str.contains("MARGINAL", case=False, na=False)]
    return sp.dropna(subset=["rodovia"]).groupby("rodovia")["v"].median().to_dict()


def tomtom_por_trecho() -> pd.DataFrame:
    """
    Da coleta atual, SO a velocidade de fluxo livre e aproveitavel. A coleta foi
    feita na noite do feriado de 7/9: currentSpeed == freeFlowSpeed em 100% dos
    trechos, ou seja, nao ha sinal de congestionamento nenhum. Em compensacao,
    fluxo livre e exatamente o que se quer medir com a via vazia.

    Com zoom=10 a TomTom devolve segmentos longos: varios trechos do DER caem no
    MESMO segmento. Esses ficam marcados - a velocidade nao e do trecho em si.
    """
    tt = pd.read_csv(RAIZ / "Tables/tomtom_flow_consolidado.csv",
                     dtype={"CÓDIGO-DO-TRECHO": str})
    tt = tt[tt["tomtom_sucesso"] == True].copy()
    chave = tt["tomtom_freeFlowSpeed"].astype(str) + "|" + tt["tomtom_freeFlowTravelTime"].astype(str)
    tt["tomtom_compartilhado"] = chave.map(chave.value_counts()) > 1
    tt["tomtom_seg_km"] = tt["tomtom_freeFlowTravelTime"] * tt["tomtom_freeFlowSpeed"] / 3600
    return tt.rename(columns={"CÓDIGO-DO-TRECHO": "codigo",
                              "tomtom_freeFlowSpeed": "v_livre_tomtom"})[
        ["codigo", "v_livre_tomtom", "tomtom_compartilhado", "tomtom_seg_km"]]


def volumes_pico() -> pd.DataFrame:
    """
    Volume horario tipico nos picos, por trecho e sentido: mediana dos dias uteis
    de abril/2026, usando so dias com as 96 janelas de 15 min presentes e volume
    diario plausivel (sensor que registrou < 100 veiculos no dia falhou).
    """
    fl = pd.read_csv(RAIZ / "flow.csv", encoding="utf-8-sig",
                     usecols=["trecho", "sentido", "dia", "intervalo", "porte", "fluxo"])
    t = fl[fl["porte"] == "total"].copy()
    t["dia"] = pd.to_datetime(t["dia"])
    t = t[t["dia"].dt.dayofweek < 5]
    completo = t.groupby(["trecho", "sentido", "dia"]).agg(
        janelas=("intervalo", "nunique"), total=("fluxo", "sum")).reset_index()
    validos = completo[(completo.janelas == 96) & (completo.total >= 100)]
    t = t.merge(validos[["trecho", "sentido", "dia"]])
    t["hora"] = t["intervalo"].str[:2].astype(int)

    horario = t.groupby(["trecho", "sentido", "dia", "hora"])["fluxo"].sum().reset_index()
    tipico = horario.groupby(["trecho", "sentido", "hora"])["fluxo"].median().unstack("hora")
    out = pd.DataFrame({f"vol_{h}h": tipico[h] for h in HORAS_PICO})
    out["dias_validos"] = validos.groupby(["trecho", "sentido"]).size()
    return out.reset_index().rename(columns={"trecho": "codigo"})


# --------------------------------------------------------------------------- #
# 4. Montagem
# --------------------------------------------------------------------------- #
def montar() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)

    brutos = carregar_trechos()
    trechos, relatorio = limpar_trechos(brutos)
    relatorio.to_csv(SAIDA / "limpeza_trechos.csv", index=False, encoding="utf-8-sig")
    print(f"trechos: {len(brutos)} com geometria -> {len(trechos)} apos limpeza "
          f"({(relatorio.decisao == 'remover').sum()} removidos)")

    pontas, nos = agrupar_pontas(trechos)
    trechos["no_inicio"], trechos["no_fim"] = pontas[:, 0], pontas[:, 1]

    limites = limite_por_rodovia()
    trechos["v_limite"] = trechos["snv_rodovia"].map(limites)
    trechos = trechos.merge(tomtom_por_trecho(), on="codigo", how="left")
    vols = volumes_pico()

    G = nx.DiGraph()
    G.graph.update(fonte="DER-DF (SRDF) + TomTom + DETRAN", crs="EPSG:4326")
    for _, n in nos.iterrows():
        G.add_node(int(n.no), lon=float(n.lon), lat=float(n.lat),
                   nome=n.nome, n_pontas=int(n.n_pontas))

    linhas = []
    for _, r in trechos.iterrows():
        faixas = FAIXAS_POR_SITUACAO.get(r.situacao, 1)
        cap = faixas * CAP_POR_FAIXA.get(r.situacao, 600)
        for sentido, u, v in (("crescente", r.no_inicio, r.no_fim),
                              ("decrescente", r.no_fim, r.no_inicio)):
            if u == v:
                continue                                    # trecho degenerado
            vol = vols[(vols.codigo == r.codigo) & (vols.sentido == sentido)]
            a = {
                "codigo": r.codigo, "sentido": sentido, "rodovia": r.snv_rodovia,
                "situacao": r.situacao, "pavimentada": r.situacao in ("PAV", "DUP", "EOD"),
                "extensao_km": float(r.extensao_km),
                "tmd_der": float(r.tmd_der) if pd.notna(r.tmd_der) else np.nan,
                "v_limite": float(r.v_limite) if pd.notna(r.v_limite) else np.nan,
                "v_livre_tomtom": float(r.v_livre_tomtom) if pd.notna(r.v_livre_tomtom) else np.nan,
                "tomtom_compartilhado": bool(r.tomtom_compartilhado) if pd.notna(r.tomtom_compartilhado) else False,
                "faixas_estimadas": faixas, "capacidade_estimada": cap,
                "tem_contagem": len(vol) > 0,
            }
            for h in HORAS_PICO:
                a[f"vol_{h}h"] = float(vol[f"vol_{h}h"].iloc[0]) if len(vol) else np.nan
                a[f"vc_{h}h"] = a[f"vol_{h}h"] / cap if len(vol) else np.nan
            # K observado fica vazio ate existir velocidade medida NO PICO.
            # Definicao proposta: K = v_livre / v_observada (= indice de tempo de viagem).
            a["K_observado"] = np.nan
            a["t_livre_s"] = (a["extensao_km"] / a["v_livre_tomtom"] * 3600
                              if a["v_livre_tomtom"] == a["v_livre_tomtom"] else np.nan)
            G.add_edge(int(u), int(v), **{k: (x if not (isinstance(x, float) and np.isnan(x)) else -1.0)
                                          for k, x in a.items()})
            linhas.append({"u": int(u), "v": int(v), **a})

    arestas = pd.DataFrame(linhas)
    arestas.to_csv(SAIDA / "arestas_srdf.csv", index=False, encoding="utf-8-sig")
    nos.to_csv(SAIDA / "nos_srdf.csv", index=False, encoding="utf-8-sig")
    nx.write_graphml(G, SAIDA / "grafo_srdf.graphml")

    resumo(G, arestas, relatorio)
    desenhar(G, arestas)


# --------------------------------------------------------------------------- #
def resumo(G, arestas, relatorio) -> None:
    fracos = sorted((len(c) for c in nx.weakly_connected_components(G)), reverse=True)
    fortes = sorted((len(c) for c in nx.strongly_connected_components(G)), reverse=True)
    print(f"\nGRAFO SRDF: {G.number_of_nodes()} entroncamentos, {G.number_of_edges()} arestas dirigidas")
    print(f"  componentes fracos: {len(fracos)} (maior com {fracos[0]} nos) | "
          f"maior componente forte: {fortes[0]} nos")
    print(f"  malha: {arestas.drop_duplicates('codigo').extensao_km.sum():,.0f} km")

    c = arestas[arestas.tem_contagem]
    print(f"\n  arestas com contagem DETRAN: {len(c)} ({c.codigo.nunique()} trechos)")
    print(f"  arestas com v_limite (mediana dos radares da rodovia): {(arestas.v_limite > 0).sum()}")
    print(f"  arestas com v_livre TomTom: {(arestas.v_livre_tomtom > 0).sum()} "
          f"(das quais {arestas.tomtom_compartilhado.sum()} em segmento compartilhado)")

    livre = arestas[(arestas.v_limite > 0) & (arestas.v_livre_tomtom > 0)].drop_duplicates("codigo")
    razao = livre.v_livre_tomtom / livre.v_limite
    print(f"\n  v_livre_tomtom / v_limite: mediana {razao.median():.2f}, "
          f"{(razao > 1).mean():.0%} dos trechos acima de 1")
    print("  -> numa via vazia o motorista anda acima do limite do radar; qualquer K com")
    print("     o limite no denominador sai > 1 sem haver congestionamento.")

    vc = c[["vc_7h", "vc_18h"]].max(axis=1)
    print(f"\n  V/C no pico com capacidade estimada: mediana {vc.median():.2f} | "
          f"> 1,2 em {(vc > 1.2).sum()} de {len(c)} arestas")
    print("  -> V/C muito acima de 1 nao e congestionamento fisicamente possivel: e o")
    print("     numero de faixas subestimado. Levantar faixas nos corredores e prioridade.")
    top = c.assign(vc=vc).sort_values("vc", ascending=False).head(8)
    print(top[["codigo", "sentido", "rodovia", "situacao", "vol_7h", "vol_18h",
               "capacidade_estimada", "vc"]].round(2).to_string(index=False))


def desenhar(G, arestas) -> None:
    fig, ax = plt.subplots(figsize=(14, 10), dpi=150)
    fig.patch.set_facecolor("#0d1117"); ax.set_facecolor("#0d1117")
    cor = {"DUP": "#ffb000", "PAV": "#5aa9e6", "EOD": "#ff7f50", "EOP": "#9e7bd9", "IMP": "#4a5563"}
    feitos = set()
    for _, a in arestas.iterrows():
        if a.codigo in feitos:
            continue
        feitos.add(a.codigo)
        u, v = G.nodes[a.u], G.nodes[a.v]
        ax.plot([u["lon"], v["lon"]], [u["lat"], v["lat"]],
                color=cor.get(a.situacao, "#888"), lw=2.6 if a.tem_contagem else 1.0,
                alpha=1 if a.tem_contagem else .75, solid_capstyle="round", zorder=3 if a.tem_contagem else 2)
    lon = [d["lon"] for _, d in G.nodes(data=True)]
    lat = [d["lat"] for _, d in G.nodes(data=True)]
    ax.scatter(lon, lat, s=5, c="#c9d1d9", zorder=4, linewidths=0)
    ax.set_aspect(1 / cos(radians(-15.8)))
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    rotulos = {"DUP": "duplicada", "PAV": "pavimentada simples", "EOD": "em obra de duplicacao",
               "EOP": "em obra de pavimentacao", "IMP": "nao pavimentada"}
    for k, c in cor.items():
        ax.plot([], [], color=c, lw=2.5, label=rotulos[k])
    ax.plot([], [], color="#c9d1d9", lw=3.5, label="traco grosso = tem contagem DETRAN")
    leg = ax.legend(loc="lower left", frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color("#c9d1d9")
    ax.set_title("Grafo do Sistema Rodoviario do DF - trechos DER-DF",
                 color="#e6edf3", fontsize=13, loc="left")
    fig.savefig(SAIDA / "mapa_srdf.png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    print(f"\n  arquivos em {SAIDA}")


if __name__ == "__main__":
    montar()
