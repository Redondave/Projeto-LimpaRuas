"""
Alocacao de trafego por equilibrio do usuario (Wardrop, 1952) com o algoritmo
de Frank-Wolfe (LeBlanc, Morlok e Pierskalla, 1975) no grafo atribuido do Gama.
Secao 6.3 de research/metodologia.md.

Problema (Beckmann, McGuire e Winsten, 1956):
    min Z(x) = soma_a integral_0^{x_a} t_a(w) dw
    t_a(x)   = t0_a * (1 + alpha * (x / c_a) ** beta)          (BPR, 1964)
sujeito a conservacao de fluxo por par OD, demanda fixa e x >= 0.

Algoritmo:
    1. x = tudo-ou-nada com os custos t0;
    2. custos t(x); caminhos minimos (Dijkstra); y = tudo-ou-nada auxiliar;
    3. gap relativo = (soma x t - soma_od q_od * custo minimo_od) / soma x t;
       para se gap < GAP_MAX ou ITER_MAX iteracoes;
    4. passo: lambda em [0, 1] que minimiza Z(x + lambda (y - x)), por bissecao
       na derivada soma_a (y_a - x_a) t_a(x_a + lambda (y_a - x_a));
    5. x = x + lambda (y - x) e volta ao 2.

Niveis de demanda (obrigatorios, research/problemas_do_modelo.md, problema 3):
toda rodada resolve os tres fatores de expansao da matriz OD. Em cada nivel a
demanda de cada par e veic_h * fator / fator adotado, e a capacidade e a coluna
do grafo calibrada para aquele fator (capacidade efetiva nos 25 gargalos).

Cenarios (secao 6.5): um JSON com alteracoes discretas no grafo:
    {"nome": "...", "descricao": "...",
     "alteracoes": [
        {"tipo": "faixa",      "arestas": ["63->102"], "faixas": 1},
        {"tipo": "remover",    "arestas": ["11->9"]},
        {"tipo": "inverter",   "arestas": ["30->79"]},
        {"tipo": "capacidade", "arestas": ["7->22"], "fator": 1.2}]}
    - faixa: nos gargalos, capacidade efetiva x (faixas + n) / faixas (regra do
      problema 1); nas demais, + n x capacidade por faixa da classe;
    - remover: tira a aresta (fechamento; teste de Braess);
    - inverter: u->v passa a v->u (mao unica invertida); falha se v->u existir;
    - capacidade: multiplica as capacidades da aresta.
O cenario e comparado com a situacao atual, nivel a nivel (delta TSTT, K, fluxo).

Sensibilidade de alpha e beta: com valores diferentes dos do grafo, a
capacidade efetiva dos gargalos e recalculada para que a situacao atual continue
reproduzindo o tempo observado (mesmo conjunto de gargalos).

Uso (da raiz do repositorio):
    python scripts/frank_wolfe.py                              # situacao atual
    python scripts/frank_wolfe.py --cenario cenarios/x.json    # cenario + comparacao
    python scripts/frank_wolfe.py --alpha 0.8 --beta 4.7       # sensibilidade
    python scripts/frank_wolfe.py --teste                      # valida o algoritmo
    python scripts/frank_wolfe.py --sioux-falls DIR            # benchmark TNTP

Saidas em resultados/<rodada>/ (rodada = base, nome do cenario, + sufixo de alpha/beta):
    arestas_<nivel>.csv   fluxo, tempo, V/C, velocidade e K modelados por aresta
    resumo.json           TSTT, gap, iteracoes, convergencia, conferencias, deltas
Visualizacao: python scripts/visualizar_resultados.py
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
GRAFO = RAIZ / "cache/gama_drive_expanded_atributos.graphml"
MATRIZ = RAIZ / "Tables/matriz_od_final.json"
RESULTADOS = RAIZ / "resultados"

GAP_MAX = 1e-4            # criterio de parada (metodologia, secao 6.3)
ITER_MAX = 500
BISSECAO_ITER = 60        # passos da busca linear (precisao ~1e-18 em lambda)
NIVEIS = {                # nivel -> (chave do fator no grafo, coluna de capacidade)
    "baixa": ("min", "capacidade_veic_h_fator_min"),
    "adotada": ("adotado", "capacidade_veic_h"),
    "alta": ("max", "capacidade_veic_h_fator_max"),
}


# ---------------------------------------------------------------------------
# Funcoes volume-atraso
# ---------------------------------------------------------------------------
@dataclass
class BPR:
    """t = t0 (1 + alpha (x/c)^beta). alpha e beta escalares ou por aresta."""
    t0: np.ndarray
    cap: np.ndarray
    alpha: float | np.ndarray = 0.15
    beta: float | np.ndarray = 4.0

    def tempo(self, x: np.ndarray) -> np.ndarray:
        return self.t0 * (1 + self.alpha * (x / self.cap) ** self.beta)

    def integral(self, x: np.ndarray) -> np.ndarray:
        return self.t0 * (x + self.alpha * self.cap / (self.beta + 1) * (x / self.cap) ** (self.beta + 1))


@dataclass
class Linear:
    """t = a + b x (usada nos testes com solucao analitica)."""
    a: np.ndarray
    b: np.ndarray

    def tempo(self, x):
        return self.a + self.b * x

    def integral(self, x):
        return self.a * x + self.b * x ** 2 / 2


# ---------------------------------------------------------------------------
# Rede e demanda em forma de vetores
# ---------------------------------------------------------------------------
@dataclass
class Rede:
    nos: list[str]
    cauda: np.ndarray            # indice do no de origem de cada aresta
    cabeca: np.ndarray           # indice do no de destino de cada aresta
    vdf: BPR | Linear
    rotulos: list[str] = field(default_factory=list)   # "u->v"

    def __post_init__(self):
        n = len(self.nos)
        self.aresta_de = -np.ones((n, n), dtype=np.int64)
        self.aresta_de[self.cauda, self.cabeca] = np.arange(len(self.cauda))
        if len(set(zip(self.cauda.tolist(), self.cabeca.tolist()))) != len(self.cauda):
            raise ValueError("arestas paralelas nao sao suportadas")


@dataclass
class Demanda:
    origens: np.ndarray          # indices dos nos de origem com demanda
    q: np.ndarray                # matriz (origens x nos) de veic/h


def montar_demanda(rede: Rede, pares: list[tuple[str, str, float]]) -> Demanda:
    idx = {n: i for i, n in enumerate(rede.nos)}
    origens = sorted({idx[o] for o, _, _ in pares})
    linha = {o: k for k, o in enumerate(origens)}
    q = np.zeros((len(origens), len(rede.nos)))
    for o, d, v in pares:
        q[linha[idx[o]], idx[d]] += v
    return Demanda(np.array(origens), q)


# ---------------------------------------------------------------------------
# Frank-Wolfe
# ---------------------------------------------------------------------------
def tudo_ou_nada(rede: Rede, dem: Demanda, custo: np.ndarray) -> tuple[np.ndarray, float]:
    """Carrega toda a demanda nos caminhos minimos. Devolve (fluxo por aresta,
    soma q_od * custo minimo_od)."""
    n = len(rede.nos)
    M = sp.csr_matrix((custo, (rede.cauda, rede.cabeca)), shape=(n, n))
    dist, pred = dijkstra(M, directed=True, indices=dem.origens, return_predecessors=True)
    y = np.zeros(len(custo))
    sptt = 0.0
    for k, o in enumerate(dem.origens):
        q = dem.q[k]
        alvo = q > 0
        if np.isinf(dist[k][alvo]).any():
            raise RuntimeError(f"par sem caminho a partir de {rede.nos[o]}")
        sptt += float(q[alvo] @ dist[k][alvo])
        # empurra a demanda pela arvore de caminhos minimos, das folhas para a
        # raiz. A ordem e pela profundidade na arvore, nao pela distancia: com
        # arestas de custo zero, pai e filho empatam na distancia.
        acumulado = q.copy()
        for no in np.argsort(-_profundidade(pred[k], o)):
            p = pred[k, no]
            if p < 0 or acumulado[no] == 0:
                continue
            y[rede.aresta_de[p, no]] += acumulado[no]
            acumulado[p] += acumulado[no]
    return y, sptt


def _profundidade(pred: np.ndarray, raiz: int) -> np.ndarray:
    """Numero de arestas entre a raiz e cada no na arvore de predecessores (-1 se inalcancavel)."""
    prof = np.full(len(pred), -1)
    prof[raiz] = 0
    for no in range(len(pred)):
        cadeia, atual = [], no
        while prof[atual] < 0 and pred[atual] >= 0:
            cadeia.append(atual)
            atual = pred[atual]
        if prof[atual] < 0:
            continue
        for k, c in enumerate(reversed(cadeia), 1):
            prof[c] = prof[atual] + k
    return prof


def busca_linear(vdf, x: np.ndarray, d: np.ndarray) -> float:
    """lambda em [0, 1] que minimiza Z(x + lambda d): zero da derivada, que e
    crescente em lambda porque t e crescente."""
    def derivada(lam):
        return float(d @ vdf.tempo(x + lam * d))
    if derivada(1.0) <= 0:
        return 1.0
    if derivada(0.0) >= 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(BISSECAO_ITER):
        meio = (lo + hi) / 2
        if derivada(meio) > 0:
            hi = meio
        else:
            lo = meio
    return (lo + hi) / 2


@dataclass
class Solucao:
    x: np.ndarray
    t: np.ndarray
    iteracoes: int
    gap: float
    convergiu: bool
    historico: list[dict]
    segundos: float

    @property
    def tstt(self) -> float:
        return float(self.x @ self.t)


def frank_wolfe(rede: Rede, dem: Demanda, gap_max: float = GAP_MAX, iter_max: int = ITER_MAX,
                verbose: bool = False) -> Solucao:
    inicio = time.perf_counter()
    vdf = rede.vdf
    x, _ = tudo_ou_nada(rede, dem, vdf.tempo(np.zeros(len(rede.cauda))))
    historico = []
    gap, it = math.inf, 0
    for it in range(1, iter_max + 1):
        t = vdf.tempo(x)
        y, sptt = tudo_ou_nada(rede, dem, t)
        tstt = float(x @ t)
        gap = (tstt - sptt) / tstt
        historico.append({"iteracao": it, "gap": gap, "tstt": tstt,
                          "beckmann": float(vdf.integral(x).sum())})
        if gap < gap_max:
            break
        lam = busca_linear(vdf, x, y - x)
        historico[-1]["passo"] = lam
        x = x + lam * (y - x)
        if verbose and it % 50 == 0:
            print(f"    iteracao {it}: gap {gap:.2e}")
    t = vdf.tempo(x)
    return Solucao(x, t, it, gap, gap < gap_max, historico, time.perf_counter() - inicio)


# ---------------------------------------------------------------------------
# Grafo do Gama -> Rede
# ---------------------------------------------------------------------------
def fatores_do_grafo(G: nx.DiGraph) -> dict:
    return json.loads(G.graph["fatores_expansao"])


def capacidades_bpr(G: nx.DiGraph, nivel: str, alpha: float, beta: float) -> dict:
    """Capacidade de cada aresta no nivel de demanda. Com alpha/beta do grafo, a
    coluna ja gravada; com outros, a capacidade efetiva dos gargalos e
    recalculada pela mesma formula do enrich_graph (mesmo conjunto de gargalos)."""
    chave, coluna = NIVEIS[nivel]
    padrao = math.isclose(alpha, G.graph["bpr_alpha"]) and math.isclose(beta, G.graph["bpr_beta"])
    fat = fatores_do_grafo(G)
    caps = {}
    for u, v, d in G.edges(data=True):
        if not d["permite_carro"]:
            continue
        if padrao or not d["gargalo"]:
            caps[(u, v)] = float(d[coluna])
            continue
        fluxo = d["fluxo_atual_estimado_veic_h"] * fat[chave] / fat["adotado"]
        r = d["razao_t_obs_t0"]
        caps[(u, v)] = min(float(d["capacidade_nominal_veic_h"]), fluxo / ((r - 1) / alpha) ** (1 / beta))
    return caps


def rede_do_grafo(G: nx.DiGraph, caps: dict, alpha: float, beta: float) -> Rede:
    arestas = [(u, v) for u, v, d in G.edges(data=True) if d["permite_carro"]]
    nos = sorted({n for e in arestas for n in e}, key=int)
    idx = {n: i for i, n in enumerate(nos)}
    t0 = np.array([float(G[u][v]["t0_min"]) for u, v in arestas])
    cap = np.array([caps[(u, v)] for u, v in arestas])
    return Rede(nos, np.array([idx[u] for u, _ in arestas]), np.array([idx[v] for _, v in arestas]),
                BPR(t0, cap, alpha, beta), [f"{u}->{v}" for u, v in arestas])


def pares_do_nivel(matriz: dict, fatores: dict, nivel: str) -> list[tuple[str, str, float]]:
    escala = fatores[NIVEIS[nivel][0]] / fatores["adotado"]
    return [(p["origem"], p["destino"], p["veic_h"] * escala) for p in matriz["pares"]]


# ---------------------------------------------------------------------------
# Cenarios
# ---------------------------------------------------------------------------
COLUNAS_CAP = ["capacidade_nominal_veic_h", "capacidade_veic_h",
               "capacidade_veic_h_fator_min", "capacidade_veic_h_fator_max"]


def aplicar_cenario(G: nx.DiGraph, cenario: dict) -> nx.DiGraph:
    H = copy.deepcopy(G)
    for alt in cenario["alteracoes"]:
        for rot in alt["arestas"]:
            u, v = rot.split("->")
            if not H.has_edge(u, v):
                raise ValueError(f"cenario {cenario['nome']}: aresta {rot} nao existe")
            d = H[u][v]
            tipo = alt["tipo"]
            if tipo == "faixa":
                n = int(alt.get("faixas", 1))
                faixas = d["lanes_sentido"]
                for c in COLUNAS_CAP:
                    if d["gargalo"] and c != "capacidade_nominal_veic_h":
                        d[c] = d[c] * (faixas + n) / faixas
                    else:
                        d[c] = d[c] + n * d["capacidade_por_faixa"]
                d["lanes_sentido"] = faixas + n
            elif tipo == "capacidade":
                for c in COLUNAS_CAP:
                    d[c] = d[c] * float(alt["fator"])
            elif tipo == "remover":
                H.remove_edge(u, v)
            elif tipo == "inverter":
                if H.has_edge(v, u):
                    raise ValueError(f"cenario {cenario['nome']}: {v}->{u} ja existe, nao da para inverter {rot}")
                dados = dict(d)
                H.remove_edge(u, v)
                if "geometry" in dados:
                    from shapely import wkt
                    dados["geometry"] = wkt.loads(dados["geometry"]).reverse().wkt
                H.add_edge(v, u, **dados)
            else:
                raise ValueError(f"tipo de alteracao desconhecido: {tipo}")
    return H


def checar_alcance(G: nx.DiGraph, matriz: dict) -> list[dict]:
    carro = nx.DiGraph([(u, v) for u, v, d in G.edges(data=True) if d["permite_carro"]])
    return [p for p in matriz["pares"]
            if p["origem"] not in carro or p["destino"] not in carro
            or not nx.has_path(carro, p["origem"], p["destino"])]


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------
def tabela_arestas(G: nx.DiGraph, rede: Rede, sol: Solucao) -> pd.DataFrame:
    linhas = []
    for i, rot in enumerate(rede.rotulos):
        u, v = rot.split("->")
        d = G[u][v]
        L = float(d["length"])
        vel = L / 1000 / (sol.t[i] / 60)
        linhas.append({
            "aresta": rot, "u": u, "v": v, "nome": d.get("name", ""), "classe": d["classe"],
            "length_m": round(L, 1), "faixas": d["lanes_sentido"], "gargalo": d["gargalo"],
            "limite_kmh": d["limite_kmh"], "v0_kmh": d["v0_kmh"], "t0_min": d["t0_min"],
            "capacidade_veic_h": round(float(rede.vdf.cap[i]), 1),
            "fluxo_veic_h": round(float(sol.x[i]), 2),
            "vc": round(float(sol.x[i] / rede.vdf.cap[i]), 4),
            "tempo_min": round(float(sol.t[i]), 5),
            "velocidade_kmh": round(vel, 2),
            "k_modelado": round(vel / d["limite_kmh"], 4),
            "vmed_obs_kmh": d.get("vmed_kmh"), "t_obs_min": d.get("t_obs_min"),
            "k_obs": d.get("k_inicial"), "fluxo_atual_estimado_veic_h": d.get("fluxo_atual_estimado_veic_h"),
        })
    return pd.DataFrame(linhas)


def indicadores(t: pd.DataFrame, sol: Solucao, demanda_total: float) -> dict:
    vkt = float((t["fluxo_veic_h"] * t["length_m"] / 1000).sum())
    peso = t["fluxo_veic_h"] * t["length_m"]
    return {
        "demanda_veic_h": round(demanda_total, 1),
        "tstt_veic_min": round(sol.tstt, 1),
        "tstt_veic_h": round(sol.tstt / 60, 2),
        "vkt_veic_km": round(vkt, 1),
        "velocidade_media_rede_kmh": round(vkt / (sol.tstt / 60), 2),
        "tempo_medio_viagem_min": round(sol.tstt / demanda_total, 3),
        "k_rede": round(float((peso * t["k_modelado"]).sum() / peso.sum()), 4),
        "arestas_vc_acima_1": int((t["vc"] > 1).sum()),
        "arestas_k_abaixo_0_5": int(((t["k_modelado"] < 0.5) & (t["fluxo_veic_h"] > 0)).sum()),
        "iteracoes": sol.iteracoes, "gap_relativo": sol.gap, "convergiu": sol.convergiu,
        "segundos": round(sol.segundos, 2),
    }


def geh(m: np.ndarray, c: np.ndarray) -> np.ndarray:
    return np.sqrt(2 * (m - c) ** 2 / np.maximum(m + c, 1e-9))


def conferencias(G: nx.DiGraph, t: pd.DataFrame, matriz: dict) -> dict:
    """Comparacoes da situacao atual (nivel adotado) com o observado. Nao e
    validacao independente (problemas_do_modelo.md, problema 2)."""
    out = {}
    # 1. passagens nas caixas TomTom, nas arestas medidas isoladamente
    pas = {}
    for r in matriz["regioes"]:
        pas[r["no"]] = pas.get(r["no"], 0) + r["passagens_veic_h"]
    fl = t.set_index("aresta")["fluxo_veic_h"]
    m, c = [], []
    for rot, f in fl.items():
        u, v = rot.split("->")
        if G.out_degree(u) == 1 and pas.get(u, 0) > 0:
            m.append(f), c.append(pas[u])
        elif G.in_degree(v) == 1 and pas.get(v, 0) > 0:
            m.append(f), c.append(pas[v])
    m, c = np.array(m), np.array(c)
    g = geh(m, c)
    out["fluxo_x_passagens_tomtom"] = {
        "testa": "escolha de rota (mesma amostra da matriz)", "arestas": len(m),
        "correlacao": round(float(np.corrcoef(m, c)[0, 1]), 3),
        "razao_mediana_modelo_obs": round(float(np.median(m / c)), 3),
        "geh_mediano": round(float(np.median(g)), 2), "fracao_geh_abaixo_5": round(float((g < 5).mean()), 3),
        "rmse_relativo": round(float(np.sqrt(np.mean((m - c) ** 2)) / c.mean()), 3)}
    # 2. tempo modelado x observado, separando o que foi calibrado
    ok = t[t["t_obs_min"].notna()].copy()
    ok["razao"] = ok["tempo_min"] / ok["t_obs_min"]
    calibrado = ok["gargalo"] | np.isclose(ok["v0_kmh"], ok["vmed_obs_kmh"], atol=0.05)
    def resumo(s):
        return {"arestas": int(len(s)), "razao_mediana_modelo_obs": round(float(s.median()), 3),
                "fracao_dentro_10pct": round(float((abs(s - 1) <= 0.10).mean()), 3)}
    out["tempo_x_observado"] = {
        "nao_calibradas": resumo(ok.loc[~calibrado, "razao"]),
        "calibradas_gargalo_ou_v0_do_pico": resumo(ok.loc[calibrado, "razao"]),
        "por_classe_nao_calibradas": {k: round(float(s.median()), 3)
                                      for k, s in ok.loc[~calibrado].groupby("classe")["razao"]},
        "tempo_total_modelo_sobre_obs": round(float((ok["tempo_min"] * ok["fluxo_veic_h"]).sum()
                                                     / (ok["t_obs_min"] * ok["fluxo_veic_h"]).sum()), 3)}
    # 3. contadores do DETRAN (calibram o fator: nao e validacao). O fator de
    # cada pista foi calculado com a passagem pela caixa sobre o no, entao a
    # comparacao e com o movimento total do no (maior entre o que entra e o que
    # sai). Com um fator unico, o modelo so pode acertar a pista cujo fator e o
    # adotado: "esperado_pelo_fator" = DETRAN x fator adotado / fator da pista.
    entra, sai = {}, {}
    for rot, f in fl.items():
        u, v = rot.split("->")
        sai[u] = sai.get(u, 0) + f
        entra[v] = entra.get(v, 0) + f
    adotado = matriz["fator_expansao"]["adotado"]
    det = []
    for o in matriz["fator_expansao"]["observacoes"]:
        mod = float(np.median([max(entra.get(n, 0), sai.get(n, 0)) for n in o["nos"]]))
        det.append({"trecho": o["trecho"], "sentido": o["sentido"], "detran_veic_h": o["detran_veic_h"],
                    "modelo_veic_h": round(mod),
                    "esperado_pelo_fator_veic_h": round(o["detran_veic_h"] * adotado / o["fator_implicito"]),
                    "geh_modelo_x_detran": round(float(geh(np.array(mod), np.array(o["detran_veic_h"]))), 2)})
    out["fluxo_x_detran"] = {"testa": "nada independente (as 4 pistas calibram o fator de expansao)",
                             "pistas": det}
    return out


def comparar(base: pd.DataFrame, cen: pd.DataFrame, ind_b: dict, ind_c: dict) -> dict:
    j = base.set_index("aresta")[["fluxo_veic_h", "k_modelado", "tempo_min"]].join(
        cen.set_index("aresta")[["fluxo_veic_h", "k_modelado", "tempo_min"]], how="outer", rsuffix="_cen")
    j["delta_fluxo"] = j["fluxo_veic_h_cen"].fillna(0) - j["fluxo_veic_h"].fillna(0)
    j["delta_k"] = j["k_modelado_cen"] - j["k_modelado"]
    top = j.reindex(j["delta_fluxo"].abs().sort_values(ascending=False).index).head(15)
    d_tstt = ind_c["tstt_veic_min"] - ind_b["tstt_veic_min"]
    return {
        "delta_tstt_veic_min": round(d_tstt, 1),
        "delta_tstt_pct": round(100 * d_tstt / ind_b["tstt_veic_min"], 3),
        "delta_k_rede": round(ind_c["k_rede"] - ind_b["k_rede"], 4),
        "maiores_mudancas_de_fluxo": [{"aresta": a, "delta_fluxo": round(float(r["delta_fluxo"]), 1),
                                       "delta_k": None if pd.isna(r["delta_k"]) else round(float(r["delta_k"]), 4)}
                                      for a, r in top.iterrows()],
    }


def rodar(G: nx.DiGraph, matriz: dict, alpha: float, beta: float, gap_max: float, iter_max: int,
          rotulo: str) -> tuple[dict, dict]:
    fat = fatores_do_grafo(G)
    resultados, tabelas = {}, {}
    for nivel in NIVEIS:
        caps = capacidades_bpr(G, nivel, alpha, beta)
        rede = rede_do_grafo(G, caps, alpha, beta)
        pares = pares_do_nivel(matriz, fat, nivel)
        dem = montar_demanda(rede, pares)
        sol = frank_wolfe(rede, dem, gap_max, iter_max)
        t = tabela_arestas(G, rede, sol)
        ind = indicadores(t, sol, sum(p[2] for p in pares))
        estado = "convergiu" if sol.convergiu else "NAO convergiu"
        print(f"  [{rotulo}] demanda {nivel:7s} (fator {fat[NIVEIS[nivel][0]]:5.2f}): "
              f"{ind['demanda_veic_h']:8.0f} veic/h | TSTT {ind['tstt_veic_h']:8.1f} veic.h | "
              f"K rede {ind['k_rede']:.3f} | V/C>1: {ind['arestas_vc_acima_1']:2d} | "
              f"{sol.iteracoes} iter, gap {sol.gap:.1e} ({estado}, {sol.segundos:.1f} s)")
        resultados[nivel] = {"fator": fat[NIVEIS[nivel][0]], "indicadores": ind,
                             "convergencia": [{k: (float(f"{v:.6g}") if isinstance(v, float) else v) for k, v in h.items()}
                                              for h in sol.historico]}
        tabelas[nivel] = t
    return resultados, tabelas


def salvar(pasta: Path, meta: dict, resultados: dict, tabelas: dict) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for nivel, t in tabelas.items():
        t.to_csv(pasta / f"arestas_{nivel}.csv", index=False, encoding="utf-8-sig")
    (pasta / "resumo.json").write_text(json.dumps({**meta, "niveis": resultados}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")


# ---------------------------------------------------------------------------
# Testes com solucao conhecida
# ---------------------------------------------------------------------------
def _rede_simples(arestas, vdf):
    nos = sorted({n for a, b in arestas for n in (a, b)})
    idx = {n: i for i, n in enumerate(nos)}
    return Rede(nos, np.array([idx[a] for a, _ in arestas]), np.array([idx[b] for _, b in arestas]),
                vdf, [f"{a}->{b}" for a, b in arestas])


def testes() -> bool:
    ok = True

    def confere(nome, cond, detalhe):
        nonlocal ok
        ok &= bool(cond)
        print(f"  [{'ok' if cond else 'FALHOU'}] {nome}: {detalhe}")

    # 1. Paradoxo de Braess (Braess, 1968): 6 veiculos de s a t
    base = [("s", "A"), ("s", "B"), ("A", "t"), ("B", "t")]
    a, b = np.array([0, 50, 50, 0.0]), np.array([10, 1, 1, 10.0])
    r = _rede_simples(base, Linear(a, b))
    s = frank_wolfe(r, montar_demanda(r, [("s", "t", 6)]), gap_max=1e-10, iter_max=5000)
    custo = s.t[0] + s.t[2]
    confere("Braess sem a ponte", np.allclose(s.x, 3, atol=1e-3) and abs(custo - 83) < 1e-2,
            f"fluxos {np.round(s.x, 3).tolist()}, custo do caminho {custo:.3f} (esperado 3 em cada, 83)")
    com = base + [("A", "B")]
    r = _rede_simples(com, Linear(np.append(a, 10), np.append(b, 1)))
    s = frank_wolfe(r, montar_demanda(r, [("s", "t", 6)]), gap_max=1e-10, iter_max=5000)
    custo = s.t[0] + s.t[4] + s.t[3]
    confere("Braess com a ponte", np.allclose(s.x, [4, 2, 2, 4, 2], atol=1e-2) and abs(custo - 92) < 1e-1,
            f"fluxos {np.round(s.x, 3).tolist()}, custo {custo:.3f} (esperado [4,2,2,4,2], 92: TSTT sobe de 498 para 552)")

    # 2. Duas rotas paralelas com BPR: solucao por bissecao na igualdade de custos
    t0, cap, q = np.array([10.0, 15.0]), np.array([1000.0, 3000.0]), 4000.0
    vdf = BPR(t0, cap, 0.15, 4.0)
    lo, hi = 0.0, q
    for _ in range(200):
        x1 = (lo + hi) / 2
        dif = vdf.tempo(np.array([x1, q - x1]))
        lo, hi = (x1, hi) if dif[0] < dif[1] else (lo, x1)
    r = _rede_simples([("o", "d"), ("o", "m"), ("m", "d")],
                      BPR(np.array([10.0, 15.0, 1e-9]), np.array([1000.0, 3000.0, 1e9]), 0.15, 4.0))
    s = frank_wolfe(r, montar_demanda(r, [("o", "d", q)]), gap_max=1e-8, iter_max=5000)
    confere("duas rotas BPR", abs(s.x[0] - x1) / q < 1e-3,
            f"rota 1 com {s.x[0]:.1f} veic/h (analitico {x1:.1f}), {s.iteracoes} iteracoes")

    # 3. Propriedades na rede do Gama: Beckmann nao cresce e o gap cai
    G = nx.read_graphml(GRAFO)
    matriz = json.loads(MATRIZ.read_text(encoding="utf-8"))
    fat = fatores_do_grafo(G)
    rede = rede_do_grafo(G, capacidades_bpr(G, "alta", 0.15, 4.0), 0.15, 4.0)
    s = frank_wolfe(rede, montar_demanda(rede, pares_do_nivel(matriz, fat, "alta")), iter_max=ITER_MAX)
    z = [h["beckmann"] for h in s.historico]
    confere("Beckmann monotono (Gama, demanda alta)", all(b <= a * (1 + 1e-12) for a, b in zip(z, z[1:])),
            f"{len(z)} iteracoes, Z de {z[0]:.0f} para {z[-1]:.0f}")
    # conservacao: o que sai de cada no menos o que entra = producao - atracao
    dem = montar_demanda(rede, pares_do_nivel(matriz, fat, "alta"))
    saldo = np.zeros(len(rede.nos))
    np.add.at(saldo, rede.cauda, s.x)
    np.subtract.at(saldo, rede.cabeca, s.x)
    esperado = np.zeros(len(rede.nos))
    esperado[dem.origens] += dem.q.sum(axis=1)
    esperado -= dem.q.sum(axis=0)
    confere("conservacao de fluxo nos nos", np.allclose(saldo, esperado, atol=1e-6),
            f"maior desvio {np.abs(saldo - esperado).max():.2e} veic/h")
    return ok


# ---------------------------------------------------------------------------
# Benchmark Sioux Falls (formato TNTP)
# ---------------------------------------------------------------------------
def _ler_tntp_tabela(caminho: Path) -> pd.DataFrame:
    linhas = caminho.read_text().splitlines()
    ini = next(i for i, l in enumerate(linhas) if l.strip().startswith("~"))
    cab = [c.strip() for c in linhas[ini].strip("~ \t;").split("\t") if c.strip()]
    dados = [l.strip().rstrip(";").split() for l in linhas[ini + 1:] if l.strip() and not l.startswith("~")]
    return pd.DataFrame(dados, columns=cab[:len(dados[0])]).apply(pd.to_numeric, errors="ignore")


def sioux_falls(pasta: Path) -> None:
    net = _ler_tntp_tabela(pasta / "SiouxFalls_net.tntp")
    net.columns = [c.lower().replace(" ", "_") for c in net.columns]
    arestas = list(zip(net["init_node"].astype(str), net["term_node"].astype(str)))
    vdf = BPR(net["free_flow_time"].to_numpy(float), net["capacity"].to_numpy(float),
              net["b"].to_numpy(float), net["power"].to_numpy(float))
    rede = _rede_simples(arestas, vdf)
    pares, origem = [], None
    for l in (pasta / "SiouxFalls_trips.tntp").read_text().splitlines():
        l = l.strip()
        if l.startswith("Origin"):
            origem = l.split()[1]
        elif origem and ":" in l:
            for item in l.split(";"):
                if ":" in item:
                    d, v = item.split(":")
                    if float(v) > 0 and d.strip() != origem:
                        pares.append((origem, d.strip(), float(v)))
    s = frank_wolfe(rede, montar_demanda(rede, pares), gap_max=1e-5, iter_max=20000)
    ref = _ler_tntp_tabela(pasta / "SiouxFalls_flow.tntp")
    ref.columns = [c.lower() for c in ref.columns]
    vol = ref.set_index([ref.columns[0], ref.columns[1]])["volume"]
    x_ref = np.array([vol[(int(a), int(b))] for a, b in arestas])
    tstt_ref = float(x_ref @ vdf.tempo(x_ref))
    print(f"Sioux Falls: {s.iteracoes} iteracoes, gap {s.gap:.1e}")
    print(f"  TSTT modelo {s.tstt:,.0f} | referencia {tstt_ref:,.0f} | diferenca {100 * (s.tstt / tstt_ref - 1):.3f}%")
    print(f"  fluxo por aresta: correlacao {np.corrcoef(s.x, x_ref)[0, 1]:.5f}, "
          f"maior desvio relativo {np.max(np.abs(s.x - x_ref) / np.maximum(x_ref, 1)):.3%}")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--cenario", type=Path, help="JSON com as alteracoes do cenario")
    ap.add_argument("--alpha", type=float, help="alpha da BPR (padrao: o do grafo)")
    ap.add_argument("--beta", type=float, help="beta da BPR (padrao: o do grafo)")
    ap.add_argument("--gap", type=float, default=GAP_MAX)
    ap.add_argument("--iter-max", type=int, default=ITER_MAX)
    ap.add_argument("--teste", action="store_true", help="valida o algoritmo em redes com solucao conhecida")
    ap.add_argument("--sioux-falls", type=Path, help="pasta com SiouxFalls_net/_trips/_flow.tntp")
    args = ap.parse_args()

    if args.teste:
        print("Testes do Frank-Wolfe:")
        sys.exit(0 if testes() else 1)
    if args.sioux_falls:
        sioux_falls(args.sioux_falls)
        return

    G = nx.read_graphml(GRAFO)
    matriz = json.loads(MATRIZ.read_text(encoding="utf-8"))
    alpha = args.alpha if args.alpha is not None else G.graph["bpr_alpha"]
    beta = args.beta if args.beta is not None else G.graph["bpr_beta"]
    sufixo = "" if (math.isclose(alpha, G.graph["bpr_alpha"]) and math.isclose(beta, G.graph["bpr_beta"])) \
        else f"_a{alpha:g}_b{beta:g}"
    meta = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "grafo": GRAFO.relative_to(RAIZ).as_posix(),
            "matriz": MATRIZ.relative_to(RAIZ).as_posix(), "bpr": {"alpha": alpha, "beta": beta},
            "parada": {"gap_relativo": args.gap, "iteracoes": args.iter_max}}

    pasta_base = RESULTADOS / f"base{sufixo}"
    print(f"Situacao atual (alpha {alpha:g}, beta {beta:g}):")
    res_b, tab_b = rodar(G, matriz, alpha, beta, args.gap, args.iter_max, "base")
    res_b["adotada"]["conferencias"] = conferencias(G, tab_b["adotada"], matriz)
    salvar(pasta_base, {**meta, "rodada": f"base{sufixo}", "cenario": None}, res_b, tab_b)
    conf = res_b["adotada"]["conferencias"]
    print(f"  conferencia (demanda adotada): fluxo x passagens TomTom: correlacao "
          f"{conf['fluxo_x_passagens_tomtom']['correlacao']}, GEH mediano {conf['fluxo_x_passagens_tomtom']['geh_mediano']}; "
          f"tempo modelo/observado nas arestas nao calibradas: "
          f"{conf['tempo_x_observado']['nao_calibradas']['razao_mediana_modelo_obs']} (mediana)")
    print(f"  -> {pasta_base.relative_to(RAIZ)}")

    if args.cenario:
        cenario = json.loads(args.cenario.read_text(encoding="utf-8"))
        H = aplicar_cenario(G, cenario)
        perdidos = checar_alcance(H, matriz)
        if perdidos:
            demanda = sum(p["veic_h"] for p in perdidos)
            sys.exit(f"Cenario {cenario['nome']} desconecta {len(perdidos)} pares OD ({demanda:.0f} veic/h). "
                     "Reveja as alteracoes.")
        print(f"\nCenario '{cenario['nome']}': {cenario.get('descricao', '')}")
        res_c, tab_c = rodar(H, matriz, alpha, beta, args.gap, args.iter_max, cenario["nome"])
        for nivel in NIVEIS:
            res_c[nivel]["comparacao_com_base"] = comparar(tab_b[nivel], tab_c[nivel],
                                                           res_b[nivel]["indicadores"], res_c[nivel]["indicadores"])
            c = res_c[nivel]["comparacao_com_base"]
            print(f"  demanda {nivel:7s}: delta TSTT {c['delta_tstt_veic_min']:+9.1f} veic.min "
                  f"({c['delta_tstt_pct']:+.2f}%) | delta K rede {c['delta_k_rede']:+.4f}")
        pasta = RESULTADOS / f"{cenario['nome']}{sufixo}"
        salvar(pasta, {**meta, "rodada": f"{cenario['nome']}{sufixo}", "cenario": cenario,
                       "base": pasta_base.relative_to(RAIZ).as_posix()}, res_c, tab_c)
        print(f"  -> {pasta.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
