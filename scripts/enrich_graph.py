"""
Monta o grafo atribuido que o Frank-Wolfe vai ler (Etapas 3b e 4 do
research/o_que_falta_fazer_pre_frank_wolfe.md).

Junta, em cada aresta do grafo de estudo:
  - faixas por sentido e limite de velocidade  (Tables/faixas_limite_arestas.csv)
  - velocidade no pico e de madrugada, K inicial (Tables/velocidades_arestas.csv)
e calcula:
  - v0_kmh     velocidade livre (Etapa 6):
                 v0 = min(limite, max(v_madrugada, v_pico))
               - madrugada (00-04h, dias uteis de julho): via vazia, mas com a
                 geometria, o trevo e os semaforos que o limite ignora;
               - nunca abaixo da velocidade de pico: de madrugada passam poucos
                 veiculos e, em ruas com amostra baixa, a media sai mais lenta que
                 no pico (onibus, caminhao de lixo, gente estacionando);
               - nunca acima do limite: excesso de velocidade nao e referencia;
               - sem dado de madrugada (cobertura < 50%): o limite.
  - t0_min     tempo em fluxo livre = length / v0
  - capacidade efetiva nos gargalos do corredor (research/problemas_do_modelo.md,
    problema 1). A BPR por aresta nao representa a fila do trevo: perto dele a
    EPCT e a DF-480 ficam lentas com so ~60% da capacidade ocupada. Nos trechos
    de gargalo, a capacidade e reduzida ate a BPR reproduzir o tempo observado:
        1. fluxo atual estimado: a matriz OD alocada tudo-ou-nada pelos caminhos
           minimos com os tempos observados no pico (t_obs). Se os tempos
           observados sao os de equilibrio, cada viagem usa o caminho mais
           rapido sob eles. Conferido contra as passagens das caixas TomTom;
        2. gargalo = aresta do corredor (CLASSES_CORREDOR) com velocidade
           observada ok, fluxo >= VC_MIN_GARGALO x capacidade nominal e atraso
           observado (t_obs/t0) acima do previsto pela BPR em mais de FOLGA_GARGALO;
        3. capacidade efetiva = fluxo / ((t_obs/t0 - 1) / alpha) ** (1 / beta),
           nunca acima da nominal.
    O conjunto de gargalos e definido com o fator de expansao adotado (e uma
    caracteristica fisica, medida pelo tempo observado). Como o fluxo escala com
    o fator, a capacidade efetiva tambem: nos fatores minimo e maximo ela e a do
    fator adotado x (fator / fator adotado), nunca acima da nominal.
O K continua sendo vmed / limite (research_plan.md); a madrugada entra so no t0.
  - capacidade_veic_h = lanes_sentido x capacidade por faixa da classe

Antes de gravar, confere o que o Frank-Wolfe pressupoe:
  - toda aresta que carro usa tem t0 > 0 e capacidade > 0;
  - v0 entre 10 e 120 km/h;
  - todos os pares da matriz OD tem caminho no grafo sem as vias proibidas a carro;
  - os nos da matriz existem no grafo.
E faz a checagem de sanidade da capacidade: nas 4 pistas com contador do DETRAN,
o volume medido no pico dividido pela capacidade (V/C) deve ficar abaixo de ~1,2.

Uso (da raiz do repositorio):
    python scripts/enrich_graph.py

Leitura: nx.read_graphml(...) devolve os atributos ja tipados (float, int, bool).
O ox.load_graphml NAO serve para este arquivo: ele espera todos os atributos
como texto e quebra nos tipados.

Saidas:
    cache/gama_drive_expanded_atributos.graphml          grafo para o Frank-Wolfe
    cache/gama_drive_expanded_atributos_relatorio.json   cobertura, checagens, V/C
    cache/gama_drive_expanded_k_inicial.png              mapa do K inicial
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

import matplotlib
import networkx as nx
import pandas as pd
from shapely import wkt
from shapely.geometry import LineString

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
GRAFO = RAIZ / "cache/gama_drive_expanded.graphml"
FAIXAS_LIMITE = RAIZ / "Tables/faixas_limite_arestas.csv"
VELOCIDADES = RAIZ / "Tables/velocidades_arestas.csv"
MATRIZ = RAIZ / "Tables/matriz_od_final.json"
SAIDA = RAIZ / "cache/gama_drive_expanded_atributos.graphml"
RELATORIO = RAIZ / "cache/gama_drive_expanded_atributos_relatorio.json"
FIGURA = RAIZ / "cache/gama_drive_expanded_k_inicial.png"

# Capacidade por faixa (veic/h/faixa), faixas do research_plan.md:
# expressas ~1.800-2.000, arteriais principais ~1.000-1.200, secundarias e locais ~500-900.
CAPACIDADE_POR_FAIXA = {
    "motorway": 1800, "trunk": 1800,
    "motorway_link": 1200, "trunk_link": 1200, "primary": 1200,
    "primary_link": 900, "secondary": 900, "tertiary": 900,
    "secondary_link": 600, "tertiary_link": 600, "unclassified": 600,
    "residential": 600, "living_street": 600,
}
# BPR padrao (Bureau of Public Roads, 1964); sensibilidade: 0,8 e 4,7 (Etapa 6)
BPR_ALPHA, BPR_BETA = 0.15, 4.0
V0_MIN, V0_MAX = 10, 120
COBERTURA_OK = 0.5        # mesma regra do velocidades_traffic_stats.py
# gargalos do corredor (capacidade efetiva)
CLASSES_CORREDOR = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link"}
VC_MIN_GARGALO = 0.3      # abaixo disso o atraso nao vem do volume (cruzamento, conversao)
FOLGA_GARGALO = 0.05      # atraso observado - atraso da BPR, em fracao de t0
VC_MAX_SANIDADE = 1.2


def classe(h: str) -> str:
    return h.strip("[]").split(",")[0].strip(" '") if h.startswith("[") else h


def fluxo_atual(G: nx.DiGraph, matriz: dict) -> dict:
    """Fluxo por aresta (veic/h, fator adotado): matriz OD alocada tudo-ou-nada
    pelos caminhos minimos com os tempos observados no pico."""
    C = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        if d["permite_carro"]:
            C.add_edge(u, v, w=d.get("t_obs_min", d["t0_min"]))
    fluxo = dict.fromkeys(C.edges, 0.0)
    por_origem = {}
    for p in matriz["pares"]:
        por_origem.setdefault(p["origem"], []).append(p)
    for o, pares in por_origem.items():
        _, caminhos = nx.single_source_dijkstra(C, o, weight="w")
        for p in pares:
            c = caminhos[p["destino"]]
            for a, b in zip(c, c[1:]):
                fluxo[(a, b)] += p["veic_h"]
    return fluxo


def capacidade_efetiva(d: dict, fluxo: float, alpha: float = BPR_ALPHA, beta: float = BPR_BETA) -> float | None:
    """Capacidade que faz a BPR reproduzir o tempo observado no pico, ou None se
    a aresta nao e gargalo. Serve tambem para recalcular com outros alpha e beta
    (sensibilidade) ou outro fator de expansao (fluxo proporcional ao fator)."""
    if d["classe"] not in CLASSES_CORREDOR or d.get("status_velocidade") != "ok":
        return None
    c = d["capacidade_nominal_veic_h"]
    r = d["t_obs_min"] / d["t0_min"]
    if fluxo / c < VC_MIN_GARGALO or r - (1 + alpha * (fluxo / c) ** beta) < FOLGA_GARGALO:
        return None
    return min(c, fluxo / ((r - 1) / alpha) ** (1 / beta))


def comparar_passagens(G: nx.DiGraph, matriz: dict, fluxo: dict) -> dict:
    """Fluxo estimado x passagens observadas nas caixas TomTom, nas arestas em que
    a caixa mede so aquela aresta (saida unica do no de origem ou entrada unica do
    de destino)."""
    pas = {}
    for r in matriz["regioes"]:
        pas[r["no"]] = pas.get(r["no"], 0) + r["passagens_veic_h"]
    pares = []
    for (u, v), f in fluxo.items():
        if G.out_degree(u) == 1 and u in pas:
            pares.append((f, pas[u]))
        elif G.in_degree(v) == 1 and v in pas:
            pares.append((f, pas[v]))
    t = pd.DataFrame(pares, columns=["estimado", "observado"])
    t = t[t["observado"] > 0]
    return {"arestas": len(t), "razao_mediana": round(float((t["estimado"] / t["observado"]).median()), 2),
            "correlacao": round(float(t.corr().iloc[0, 1]), 3)}


def checar_capacidade(G: nx.DiGraph, matriz: dict) -> list[dict]:
    """V/C nas pistas com contador do DETRAN: volume medido / capacidade da pista
    nas arestas que saem dos nos de calibracao pela mesma rodovia."""
    linhas = []
    for o in matriz["fator_expansao"]["observacoes"]:
        caps = []
        for n in o["nos"]:
            for _, w, d in G.out_edges(n, data=True):
                if o["rodovia"] in re.findall(r"(?:DF|BR)-\d{3}", str(d.get("ref", ""))):
                    caps.append(d["capacidade_nominal_veic_h"])
        if not caps:
            continue
        cap = sorted(caps)[len(caps) // 2]
        linhas.append({"trecho": o["trecho"], "sentido": o["sentido"], "rodovia": o["rodovia"],
                       "detran_veic_h": o["detran_veic_h"], "capacidade_veic_h": cap,
                       "v_sobre_c": round(o["detran_veic_h"] / cap, 2)})
    return linhas


def velocidade_livre(limite: float, s: pd.Series) -> tuple[float, str]:
    if not (pd.notna(s["v_madrugada_kmh"]) and s["cobertura_madrugada"] >= COBERTURA_OK):
        return limite, "limite (sem dado de madrugada)"
    v, fonte = float(s["v_madrugada_kmh"]), "madrugada"
    if pd.notna(s["vmed_kmh"]) and s["status"] == "ok" and float(s["vmed_kmh"]) > v:
        v, fonte = float(s["vmed_kmh"]), "pico (madrugada mais lenta)"
    if v > limite:
        v, fonte = limite, "limite (madrugada acima dele)"
    return v, fonte


def figura(G: nx.DiGraph) -> None:
    pos = {n: (float(d["x"]), float(d["y"])) for n, d in G.nodes(data=True)}
    fig, ax = plt.subplots(figsize=(11, 11), dpi=120)
    fig.patch.set_facecolor("#0b0f14")
    ax.set_facecolor("#0b0f14")
    cmap = plt.get_cmap("RdYlGn")
    for u, v, d in G.edges(data=True):
        g = wkt.loads(d["geometry"]) if "geometry" in d else LineString([pos[u], pos[v]])
        k = d.get("k_inicial")
        cor = "#4a5563" if k is None else cmap(min(max(k, 0.0), 1.0))
        ax.plot(*g.xy, color=cor, lw=1.2 + 1.2 * (d["capacidade_veic_h"] / 3600), solid_capstyle="round")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
    barra = fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.01)
    barra.set_label("K inicial = vmed / limite (pico, julho/2026)", color="white")
    barra.ax.yaxis.set_tick_params(color="white", labelcolor="white")
    ax.set_title("Grafo do Gama: K inicial (cor) e capacidade (espessura)", color="white", loc="left")
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(FIGURA, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    G = nx.read_graphml(GRAFO)
    fl = pd.read_csv(FAIXAS_LIMITE).set_index("edge_id")
    vel = pd.read_csv(VELOCIDADES).set_index("edge_id")
    matriz = json.loads(MATRIZ.read_text(encoding="utf-8"))

    for u, v, d in G.edges(data=True):
        eid = f"{u}:{v}:0"
        f, s = fl.loc[eid], vel.loc[eid]
        cls = classe(d["highway"])
        carro = bool(f["permite_carro"])
        L = float(d["length"])
        d["length"] = L                       # no grafo de origem vinha como texto
        d["classe"] = cls
        d["permite_carro"] = carro
        d["categoria_ctb"] = f["categoria_ctb"] if pd.notna(f["categoria_ctb"]) else ""
        d["lanes_sentido"] = int(f["lanes_sentido"])
        d["fonte_lanes"] = f["fonte_lanes"]
        d["capacidade_por_faixa"] = CAPACIDADE_POR_FAIXA.get(cls, 600) if carro else 0
        d["capacidade_veic_h"] = d["lanes_sentido"] * d["capacidade_por_faixa"]
        d["fonte_limite"] = f["fonte_maxspeed"]
        d["fonte_v0"] = "corredor de onibus"
        if carro:
            d["limite_kmh"] = float(f["maxspeed_kmh"])
            v0, d["fonte_v0"] = velocidade_livre(d["limite_kmh"], s)
            d["v0_kmh"] = round(v0, 1)
            if pd.notna(s["v_madrugada_kmh"]):
                d["v_madrugada_kmh"] = float(s["v_madrugada_kmh"])
            d["t0_min"] = round(L / (v0 / 3.6) / 60, 5)
        if pd.notna(s["vmed_kmh"]):
            d["vmed_kmh"] = float(s["vmed_kmh"])
            d["t_obs_min"] = round(L / (float(s["vmed_kmh"]) / 3.6) / 60, 5)
        if pd.notna(s["k_inicial"]):
            d["k_inicial"] = float(s["k_inicial"])
        d["status_velocidade"] = s["status"]

    # ---- capacidade efetiva nos gargalos do corredor ----
    for _, _, d in G.edges(data=True):
        d["capacidade_nominal_veic_h"] = d["capacidade_veic_h"]
    fluxo = fluxo_atual(G, matriz)
    fe = matriz["fator_expansao"]
    fatores = {"min": fe["faixa_para_sensibilidade"][0], "adotado": fe["adotado"],
               "max": fe["faixa_para_sensibilidade"][1]}
    gargalos = []
    for u, v, d in G.edges(data=True):
        if not d["permite_carro"]:
            d["gargalo"] = False
            continue
        x = fluxo.get((u, v), 0.0)
        d["fluxo_atual_estimado_veic_h"] = round(x, 1)
        if d.get("status_velocidade") == "ok":
            d["razao_t_obs_t0"] = round(d["t_obs_min"] / d["t0_min"], 3)
        nominal = d["capacidade_nominal_veic_h"]
        c = capacidade_efetiva(d, x)
        d["gargalo"] = c is not None
        cap = {k: min(nominal, c * f / fatores["adotado"]) if c else None for k, f in fatores.items()}
        d["capacidade_veic_h"] = round(cap["adotado"]) if cap["adotado"] else nominal
        d["capacidade_veic_h_fator_min"] = round(cap["min"]) if cap["min"] else nominal
        d["capacidade_veic_h_fator_max"] = round(cap["max"]) if cap["max"] else nominal
        if d["gargalo"]:
            gargalos.append({"aresta": f"{u}->{v}", "nome": d.get("name", ""), "classe": d["classe"],
                             "length_m": round(d["length"]), "fluxo_veic_h": round(x),
                             "t_obs_sobre_t0": d["razao_t_obs_t0"],
                             "capacidade_nominal": nominal, "capacidade_efetiva": d["capacidade_veic_h"],
                             "fracao_da_nominal": round(d["capacidade_veic_h"] / nominal, 2),
                             "capacidade_fator_min": d["capacidade_veic_h_fator_min"],
                             "capacidade_fator_max": d["capacidade_veic_h_fator_max"]})
    conferencia_fluxo = comparar_passagens(G, matriz, fluxo)

    # ---- checagens do que o Frank-Wolfe pressupoe ----
    problemas = []
    for u, v, d in G.edges(data=True):
        if not d["permite_carro"]:
            continue
        if not (d.get("t0_min", 0) > 0 and d["capacidade_veic_h"] > 0):
            problemas.append(f"{u}->{v}: t0 ou capacidade nao positivos")
        if not V0_MIN <= d["v0_kmh"] <= V0_MAX:
            problemas.append(f"{u}->{v}: v0 = {d['v0_kmh']} km/h fora de [{V0_MIN}, {V0_MAX}]")
    carro = G.edge_subgraph([(u, v) for u, v, d in G.edges(data=True) if d["permite_carro"]])
    pares = matriz["pares"]
    fora = [p for p in pares if p["origem"] not in G or p["destino"] not in G]
    sem_caminho = [p for p in pares if p["origem"] in carro and p["destino"] in carro
                   and not nx.has_path(carro, p["origem"], p["destino"])]
    sem_caminho += [p for p in pares if p not in fora and (p["origem"] not in carro or p["destino"] not in carro)]
    if fora:
        problemas.append(f"{len(fora)} pares OD com no fora do grafo")
    if sem_caminho:
        problemas.append(f"{len(sem_caminho)} pares OD sem caminho por vias de carro")

    vc = checar_capacidade(G, matriz)
    for r in vc:
        if r["v_sobre_c"] > VC_MAX_SANIDADE:
            problemas.append(f"V/C = {r['v_sobre_c']} em {r['rodovia']} {r['sentido']}: capacidade subestimada?")
    for g in gargalos:
        d = G.edges[g["aresta"].split("->")[0], g["aresta"].split("->")[1]]
        r_bpr = 1 + BPR_ALPHA * (d["fluxo_atual_estimado_veic_h"] / d["capacidade_veic_h"]) ** BPR_BETA
        if abs(r_bpr - d["razao_t_obs_t0"]) > 0.01 and d["capacidade_veic_h"] < d["capacidade_nominal_veic_h"]:
            problemas.append(f"{g['aresta']}: capacidade efetiva nao reproduz t_obs")

    G.graph.update({
        "crs": "EPSG:31983",
        "descricao": "Grafo do Gama atribuido para alocacao de trafego (Frank-Wolfe)",
        "gerado_em": date.today().isoformat(),
        "matriz_od": MATRIZ.relative_to(RAIZ).as_posix(),
        "unidades": "length m; v0_kmh, limite_kmh, vmed_kmh, v_madrugada_kmh km/h; t0_min, t_obs_min min; "
                    "capacidade_*, fluxo_atual_estimado_veic_h veic/h por sentido",
        "capacidade": ("capacidade_veic_h = efetiva nos gargalos (gargalo = True, fator adotado), nominal "
                       "nas demais; capacidade_veic_h_fator_min/_max para os outros fatores de expansao; "
                       "outros alpha/beta: recalcular com enrich_graph.capacidade_efetiva"),
        "fatores_expansao": json.dumps(fatores),
        "vdf": "BPR: t = t0_min * (1 + bpr_alpha * (fluxo / capacidade_veic_h) ** bpr_beta)",
        "bpr_alpha": BPR_ALPHA, "bpr_beta": BPR_BETA,
        "v0": "min(limite, max(v_madrugada 00-04h, v_pico)); sem dado de madrugada, o limite",
        "k": "k_inicial = vmed_kmh / limite_kmh (pico)",
        "excluir_da_alocacao": "arestas com permite_carro = False",
        "leitura": "nx.read_graphml (ox.load_graphml nao aceita os atributos tipados)",
    })
    nx.write_graphml(G, SAIDA)
    figura(G)

    arestas = pd.DataFrame([{"classe": d["classe"], "carro": d["permite_carro"],
                             "cap": d["capacidade_veic_h"], "t0": d.get("t0_min"),
                             "k": d.get("k_inicial"), "fonte_v0": d["fonte_v0"],
                             "t_obs": d.get("t_obs_min") if d.get("status_velocidade") == "ok" else None,
                             "fonte_lanes": d["fonte_lanes"]} for *_, d in G.edges(data=True)])
    rel = {
        "arestas": G.number_of_edges(), "arestas_de_carro": int(arestas["carro"].sum()),
        "com_k_inicial": int(arestas["k"].notna().sum()),
        "fonte_v0": arestas["fonte_v0"].value_counts().to_dict(),
        "fonte_lanes": arestas["fonte_lanes"].value_counts().to_dict(),
        "t_obs_sobre_t0": {
            "mediana": round(float((arestas["t_obs"] / arestas["t0"]).median()), 2),
            "rede_toda": round(float(arestas.loc[arestas["t_obs"].notna(), "t_obs"].sum()
                                     / arestas.loc[arestas["t_obs"].notna(), "t0"].sum()), 3),
            "por_classe": (arestas["t_obs"] / arestas["t0"]).groupby(arestas["classe"]).median()
                .dropna().round(2).to_dict(),
        },
        "fluxo_estimado_vs_passagens_tomtom": conferencia_fluxo,
        "gargalos": {"regra": {"classes": sorted(CLASSES_CORREDOR), "vc_min": VC_MIN_GARGALO,
                               "folga": FOLGA_GARGALO, "alpha": BPR_ALPHA, "beta": BPR_BETA},
                     "fatores": fatores, "arestas": gargalos},
        "capacidade_por_classe": arestas[arestas["carro"]].groupby("classe")["cap"]
            .agg(lambda c: sorted(set(int(x) for x in c))).to_dict(),
        "capacidade_por_faixa": CAPACIDADE_POR_FAIXA,
        "bpr": {"alpha": BPR_ALPHA, "beta": BPR_BETA},
        "pares_od": len(pares), "pares_od_sem_caminho": len(sem_caminho),
        "v_sobre_c_detran": vc,
        "problemas": problemas,
    }
    RELATORIO.write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Grafo atribuido: {G.number_of_nodes()} nos, {G.number_of_edges()} arestas "
          f"({rel['arestas_de_carro']} de carro) -> {SAIDA.relative_to(RAIZ)}")
    print(f"Capacidade (veic/h por sentido) por classe: {rel['capacidade_por_classe']}")
    print(f"t0 total da rede: {arestas['t0'].sum():.1f} min | K inicial em {rel['com_k_inicial']} arestas")
    print(f"v0 por fonte: {rel['fonte_v0']}")
    print(f"t_obs/t0 no pico: mediana {rel['t_obs_sobre_t0']['mediana']}, rede toda "
          f"{rel['t_obs_sobre_t0']['rede_toda']}, por classe {rel['t_obs_sobre_t0']['por_classe']}")
    print(f"Fluxo estimado x passagens TomTom: {conferencia_fluxo}")
    print(f"Gargalos com capacidade efetiva: {len(gargalos)} arestas")
    for g in gargalos:
        print(f"  {g['aresta']:9s} {g['classe']:10s} {g['length_m']:5d} m  fluxo {g['fluxo_veic_h']:5d}  "
              f"t_obs/t0 {g['t_obs_sobre_t0']:.2f}  capacidade {g['capacidade_nominal']} -> {g['capacidade_efetiva']} "
              f"({g['fracao_da_nominal']:.0%}; fatores min/max: {g['capacidade_fator_min']}/{g['capacidade_fator_max']})")
    print(f"Pares OD: {len(pares)} | sem caminho por vias de carro: {len(sem_caminho)}")
    print("V/C nas pistas com contador DETRAN:")
    for r in vc:
        print(f"  {r['rodovia']} {r['trecho']} {r['sentido']:11s} {r['detran_veic_h']:5d} / "
              f"{r['capacidade_veic_h']:5d} = {r['v_sobre_c']}")
    print("Checagens: " + ("todas ok" if not problemas else f"{len(problemas)} problema(s)"))
    for p in problemas:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
