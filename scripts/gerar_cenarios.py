"""
Gera os cenarios de intervencao (cenarios/*.json) a partir de criterios sobre o
grafo atribuido, cobrindo os tipos previstos no artigo (artigo/artigoFinal.tex,
"Alocacao, cenarios e indicadores"): acrescimo de faixa, inversao de sentido e
remocao de arestas (teste de Braess). Cada cenario registra o criterio que
escolheu as arestas, para o relatorio (research/relatorio_cenarios.md).

Familias:
    F  faixa adicional (+1 faixa; nos gargalos, capacidade efetiva x (n+1)/n)
    S  sentido de circulacao (inversao, ou mao dupla -> mao unica)
    R  remocao / fechamento de acessos que alimentam os gargalos
    B  caso de Braess, se a varredura (frank_wolfe.py --varredura-*) confirmar algum

O cenario C0 (cenarios/C0_faixa_epct_norte_trevo.json) ja existia e nao e
gerado aqui. Cenarios que desconectariam algum par OD sao descartados com aviso.

Uso (da raiz do repositorio):
    python scripts/gerar_cenarios.py
    python scripts/frank_wolfe.py --todos
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from frank_wolfe import CENARIOS, GRAFO, MATRIZ, RESULTADOS, aplicar_cenario, checar_alcance  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

K_ALCA_CRITICA = 0.25     # alcas com K observado abaixo disso (artigo: "K < 0,25 nas alcas")


def rumo(G: nx.DiGraph, u: str, v: str) -> str:
    a, b = G.nodes[u], G.nodes[v]
    ang = math.degrees(math.atan2(float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))) % 360
    return ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"][int((ang + 22.5) // 45) % 8]


def binario(G: nx.DiGraph, via: str) -> tuple[list[str], list[str], float, float]:
    """Separa os dois sentidos de uma via de mao dupla pelo rumo em relacao ao
    primeiro trecho. Devolve (sentido mantido, sentido removido, fluxos), mantendo
    o sentido de maior fluxo na situacao atual (resultados/base, demanda adotada)."""
    fluxo = pd.read_csv(RESULTADOS / "base/arestas_adotada.csv", encoding="utf-8-sig").set_index("aresta")["fluxo_veic_h"]
    es = [(u, v) for u, v, d in G.edges(data=True) if d["permite_carro"] and str(d.get("name", "")) == via]
    vec = lambda u, v: np.array([float(G.nodes[v]["x"]) - float(G.nodes[u]["x"]),  # noqa: E731
                                 float(G.nodes[v]["y"]) - float(G.nodes[u]["y"])])
    ref = vec(*es[0])
    a = [f"{u}->{v}" for u, v in es if vec(u, v) @ ref >= 0]
    b = [f"{u}->{v}" for u, v in es if vec(u, v) @ ref < 0]
    fa, fb = sum(fluxo[e] for e in a), sum(fluxo[e] for e in b)
    return (a, b, fa, fb) if fa >= fb else (b, a, fb, fa)


def arestas(G, filtro) -> list[str]:
    return sorted((f"{u}->{v}" for u, v, d in G.edges(data=True) if d["permite_carro"] and filtro(u, v, d)),
                  key=lambda r: [int(x) for x in r.split("->")])


def cenarios(G: nx.DiGraph) -> list[dict]:
    epct = lambda d: "DF-001" in str(d.get("ref", ""))  # noqa: E731
    nome = lambda d, n: str(d.get("name", "")) == n      # noqa: E731
    sf = "Avenida São Francisco"
    manter, remover, fm, fr = binario(G, "Marginal DF-480")
    lista = [
        {"codigo": "F1", "nome": "F1_faixa_epct_norte", "familia": "faixa",
         "descricao": "+1 faixa em todos os gargalos da EPCT (DF-001) sentido norte",
         "criterio": "arestas com gargalo = True, ref DF-001 e rumo noroeste (sentido norte da EPCT)",
         "arestas": arestas(G, lambda u, v, d: d["gargalo"] and epct(d) and rumo(G, u, v) == "noroeste")},
        {"codigo": "F2", "nome": "F2_faixa_epct_sul", "familia": "faixa",
         "descricao": "+1 faixa em todos os gargalos da EPCT (DF-001) sentido sul",
         "criterio": "arestas com gargalo = True, ref DF-001 e rumo sudeste (sentido sul da EPCT)",
         "arestas": arestas(G, lambda u, v, d: d["gargalo"] and epct(d) and rumo(G, u, v) == "sudeste")},
        {"codigo": "F3", "nome": "F3_faixa_df480", "familia": "faixa",
         "descricao": "+1 faixa em todos os gargalos da DF-480 (sentido sudoeste) e na alça de acesso",
         "criterio": "arestas com gargalo = True que não são da EPCT (DF-480, classe primary, e a alça 'Acesso DF-480')",
         "arestas": arestas(G, lambda u, v, d: d["gargalo"] and not epct(d))},
        {"codigo": "F4", "nome": "F4_faixa_alcas_k_baixo", "familia": "faixa",
         "descricao": "+1 faixa nas alças do trevo com K observado < 0,25",
         "criterio": f"classe trunk_link com k_inicial < {K_ALCA_CRITICA} (as alças apontadas como gargalo crítico no diagnóstico do K)",
         "arestas": arestas(G, lambda u, v, d: d["classe"] == "trunk_link" and d.get("k_inicial", 1) < K_ALCA_CRITICA)},
        {"codigo": "F5", "nome": "F5_faixa_av_sao_francisco", "familia": "faixa",
         "descricao": "+1 faixa na Avenida São Francisco (coletora), nos dois sentidos",
         "criterio": "arestas com name = 'Avenida São Francisco': a via coletora de maior fluxo do grafo",
         "arestas": arestas(G, lambda u, v, d: nome(d, sf))},
        {"codigo": "F6", "nome": "F6_faixa_marginal_df480", "familia": "faixa",
         "descricao": "+1 faixa na Marginal DF-480, nos dois sentidos",
         "criterio": "arestas com name = 'Marginal DF-480': coletora com K observado entre 0,26 e 0,6",
         "arestas": arestas(G, lambda u, v, d: nome(d, "Marginal DF-480"))},
        {"codigo": "S1", "nome": "S1_binario_marginal_df480", "familia": "sentido",
         "descricao": "Marginal DF-480 em mão única (binário): remove o sentido de menor fluxo",
         "criterio": (f"mantém o sentido de maior fluxo na situação atual ({fm:.0f} veíc/h somados nas {len(manter)} arestas) "
                      f"e remove o oposto ({fr:.0f} veíc/h). A Av. São Francisco, primeira candidata, desconectaria 52 pares OD"),
         "alteracoes": [{"tipo": "remover", "arestas": sorted(remover, key=lambda r: [int(x) for x in r.split("->")])}],
         "arestas_mantidas": sorted(manter, key=lambda r: [int(x) for x in r.split("->")])},
        {"codigo": "S2", "nome": "S2_inverter_acesso_df480_30_7", "familia": "sentido",
         "descricao": "Inverte o acesso 30→7: a entrada na DF-480 vira saída da DF-480",
         "criterio": "30→7 é a mão única que converge no gargalo 7→22 da DF-480 (415 veíc/h na situação atual)",
         "alteracoes": [{"tipo": "inverter", "arestas": ["30->7"]}]},
        {"codigo": "S3", "nome": "S3_inverter_alca_acesso_df480", "familia": "sentido",
         "descricao": "Inverte a alça 'Acesso DF-480' (26→21→18): a ligação EPCT sul → DF-480 passa a ser DF-480 → EPCT",
         "criterio": ("alça com 879–888 veíc/h que converge no gargalo 18→4 da DF-480; a inversão do acesso "
                      "127→130→103→126 (primeira candidata) desconectaria 54 pares OD"),
         "alteracoes": [{"tipo": "inverter", "arestas": ["26->21", "21->18"]}]},
        {"codigo": "R1", "nome": "R1_fechar_alca_acesso_df480_21_18", "familia": "remocao",
         "descricao": "Fecha a alça 21→18 ('Acesso DF-480'), que converge no gargalo 18→4",
         "criterio": ("acesso de maior fluxo (888 veíc/h) que pode ser fechado sem desconectar pares OD e que alimenta um gargalo; "
                      "o acesso 103→126 à EPCT norte, primeira candidata, desconectaria 47 pares OD"),
         "alteracoes": [{"tipo": "remover", "arestas": ["21->18"]}]},
        {"codigo": "R2", "nome": "R2_fechar_acesso_df480_30_7", "familia": "remocao",
         "descricao": "Fecha o acesso 30→7 à DF-480",
         "criterio": "acesso (415 veíc/h) que converge no gargalo 7→22 da DF-480; teste de Braess por fechamento de acesso",
         "alteracoes": [{"tipo": "remover", "arestas": ["30->7"]}]},
        {"codigo": "R3", "nome": "R3_fechar_alca_11_63", "familia": "remocao",
         "descricao": "Fecha a alça 11→63 (retorno EPCT sul → EPCT norte), de K observado 0,16",
         "criterio": ("alça com K observado baixo e 138 veíc/h que se junta à EPCT norte em 63, logo antes do gargalo 63→102; "
                      "a alça 67→66, primeira candidata, desconectaria 16 pares OD"),
         "alteracoes": [{"tipo": "remover", "arestas": ["11->63"]}]},
    ]
    for c in lista:
        if "alteracoes" not in c:
            c["alteracoes"] = [{"tipo": "faixa", "arestas": c.pop("arestas"), "faixas": 1}]
    return lista + cenarios_braess()


def cenarios_braess() -> list[dict]:
    """Um cenario por caso de Braess confirmado nas varreduras da situacao atual
    (alpha e beta do grafo)."""
    saida = []
    for modo, tipo in (("remocao", "remover"), ("faixa", "faixa")):
        resumo = RESULTADOS / f"varredura_{modo}" / "resumo.json"
        if not resumo.exists():
            continue
        casos = json.loads(resumo.read_text(encoding="utf-8"))["casos_braess_confirmados"]
        vistos = set()
        for c in sorted(casos, key=lambda c: c["delta_tstt_pct_confirmado"] * (-1 if modo == "faixa" else 1)):
            if c["aresta"] in vistos:
                continue
            vistos.add(c["aresta"])
            cod = f"B{len(saida) + 1}"
            alt = {"tipo": tipo, "arestas": [c["aresta"]]}
            if tipo == "faixa":
                alt["faixas"] = 1
            saida.append({
                "codigo": cod, "nome": f"{cod}_braess_{modo}_{c['aresta'].replace('->', '_')}", "familia": "braess",
                "descricao": f"Paradoxo de Braess: {'fechar' if modo == 'remocao' else '+1 faixa em'} {c['aresta']}",
                "criterio": (f"caso confirmado na varredura de {modo} (gap 1e-7): delta TSTT "
                             f"{c['delta_tstt_pct_confirmado']:+.3f}% na demanda {c['nivel']}"),
                "alteracoes": [alt]})
    return saida


def main() -> None:
    G = nx.read_graphml(GRAFO)
    matriz = json.loads(MATRIZ.read_text(encoding="utf-8"))
    CENARIOS.mkdir(exist_ok=True)
    for c in cenarios(G):
        if not any(a["arestas"] for a in c["alteracoes"]):
            print(f"  {c['codigo']} {c['nome']}: nenhuma aresta atende ao critério, ignorado")
            continue
        try:
            H = aplicar_cenario(G, c)
        except ValueError as e:
            print(f"  {c['codigo']} {c['nome']}: DESCARTADO ({e})")
            continue
        perdidos = checar_alcance(H, matriz)
        if perdidos:
            dem = sum(p["veic_h"] for p in perdidos)
            print(f"  {c['codigo']} {c['nome']}: DESCARTADO, desconecta {len(perdidos)} pares OD ({dem:.0f} veic/h)")
            continue
        n = sum(len(a["arestas"]) for a in c["alteracoes"])
        (CENARIOS / f"{c['nome']}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {c['codigo']} {c['nome']}: {n} aresta(s) -> cenarios/{c['nome']}.json")


if __name__ == "__main__":
    main()
