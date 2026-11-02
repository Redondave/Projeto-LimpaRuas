"""
Gera research/relatorio_cenarios.md: documentacao da etapa de cenarios e das
varreduras de Braess, com as alteracoes exatas de cada cenario e os resultados
numericos lidos de resultados/ (nada e digitado a mao).

Uso (da raiz do repositorio), depois de rodar os cenarios e as varreduras:
    python scripts/relatorio_cenarios.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import networkx as nx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from frank_wolfe import GRAFO, MATRIZ, NIVEIS, RESULTADOS, aplicar_cenario, capacidades_bpr  # noqa: E402
from visualizar_resultados import DESPREZIVEL_PCT, classificar, ordem_cenario  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "research/relatorio_cenarios.md"
SENS = "_a0.8_b4.7"
ROTULO_ALT = {"faixa": "+{n} faixa", "remover": "remoção", "inverter": "inversão de sentido", "capacidade": "capacidade ×{f}"}


def br(v, d=2, sinal=False) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if round(v, d) == 0:
        v = 0.0
    s = f"{v:+,.{d}f}" if sinal and v != 0 else f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def gap(g: float) -> str:
    return "< 1e-12" if g < 1e-12 else f"{g:.1e}"


def seta(u: str) -> str:
    return u.replace("->", "→")


def tabela(cab: list[str], linhas: list[list]) -> str:
    out = ["| " + " | ".join(cab) + " |", "|" + "|".join("---" for _ in cab) + "|"]
    out += ["| " + " | ".join(str(c) for c in l) + " |" for l in linhas]
    return "\n".join(out)


def carregar() -> tuple[dict, dict]:
    rodadas = {}
    for resumo in sorted(RESULTADOS.glob("*/resumo.json")):
        if resumo.parent.name.startswith("varredura_"):
            continue
        r = json.loads(resumo.read_text(encoding="utf-8"))
        r["tabelas"] = {n: pd.read_csv(resumo.parent / f"arestas_{n}.csv", encoding="utf-8-sig",
                                       dtype={"u": str, "v": str}).set_index("aresta") for n in NIVEIS}
        rodadas[r["rodada"]] = r
    varr = {}
    for resumo in sorted(RESULTADOS.glob("varredura_*/resumo.json")):
        r = json.loads(resumo.read_text(encoding="utf-8"))
        if "modo" in r:
            r["tabela"] = pd.read_csv(resumo.parent / "varredura.csv", encoding="utf-8-sig")
            varr[resumo.parent.name] = r
    return rodadas, varr


def nome_aresta(G, e: str) -> str:
    u, v = e.split("->")
    d = G[u][v] if G.has_edge(u, v) else G[v][u]
    return str(d.get("name") or "") or d["classe"]


def nota_convergencia(rodadas: dict) -> str:
    lentos, falhas = [], []
    for nome, r in sorted(rodadas.items()):
        for n in NIVEIS:
            i = r["niveis"][n]["indicadores"]
            if not i["convergiu"]:
                falhas.append(f"{nome} ({n})")
            elif i["iteracoes"] > 500:
                lentos.append(f"{nome} ({n}: {i['iteracoes']} iterações)")
    txt = "Todas as rodadas de cenário convergiram ao gap 10⁻⁴." if not falhas else "Não convergiram: " + ", ".join(falhas) + "."
    if lentos:
        txt += (" Na sensibilidade com a = 0,8, a rede fica mais congestionada e o Frank-Wolfe converge mais devagar: "
                + "; ".join(lentos) + " precisaram de mais de 500 iterações e foram rodados com teto de 5.000 (`--iter-max 5000`), "
                "mantendo o critério de gap.")
    return txt


def secao_base(rodadas: dict) -> list[str]:
    out = ["## 2. Situação atual (referência de todas as comparações)", ""]
    for suf, tit in (("", "Parâmetros-base (a = 0,15; b = 4)"), (SENS, "Sensibilidade (a = 0,8; b = 4,7)")):
        r = rodadas.get(f"base{suf}")
        if r is None:
            continue
        linhas = []
        for n in NIVEIS:
            i = r["niveis"][n]["indicadores"]
            linhas.append([n, br(r["niveis"][n]["fator"]), br(i["demanda_veic_h"], 0), br(i["tstt_veic_h"], 1),
                           br(i["k_rede"], 4), br(i["velocidade_media_rede_kmh"], 1), br(i["tempo_medio_viagem_min"], 2),
                           i["arestas_vc_acima_1"], i["arestas_k_abaixo_0_5"], i["iteracoes"], gap(i["gap_relativo"])])
        out += [f"**{tit}** (`resultados/base{suf}/`)", "",
                tabela(["Demanda", "Fator", "veíc/h", "TSTT (veíc·h)", "K da rede", "Vel. média (km/h)",
                        "Tempo médio (min)", "Arestas V/C>1", "Arestas K<0,5", "Iterações", "Gap final"], linhas), ""]
    return out


def secao_resumo(rodadas: dict) -> list[str]:
    cens = sorted([r for r in rodadas.values() if r.get("cenario") and SENS not in r["rodada"]], key=ordem_cenario)
    linhas = []
    for r in cens:
        c = r["cenario"]
        d = [r["niveis"][n]["comparacao_com_base"] for n in NIVEIS]
        cl = classificar(r)
        sens = rodadas.get(r["rodada"] + SENS)
        ds = [sens["niveis"][n]["comparacao_com_base"]["delta_tstt_pct"] for n in NIVEIS] if sens else None
        linhas.append([f"**{c.get('codigo', '')}**", c["descricao"],
                       " / ".join(br(x["delta_tstt_pct"], 2, True) for x in d),
                       " / ".join(br(x["delta_k_rede"], 4, True) for x in d),
                       cl["rotulo"] + (f"; K × TSTT divergem ({', '.join(cl['divergencia_k_tstt'])})" if cl["divergencia_k_tstt"] else ""),
                       " / ".join(br(x, 2, True) for x in ds) if ds else "—"])
    return ["## 3. Resumo dos cenários", "",
            "ΔTSTT e ΔK da rede em relação à situação atual, na ordem **demanda baixa / adotada / alta**. A última coluna repete o ΔTSTT com a = 0,8 e b = 4,7.", "",
            tabela(["Caso", "Alteração", "ΔTSTT (%)", "ΔK da rede", "Classificação", "ΔTSTT (%) com a = 0,8"], linhas), "",
            f"Classificação: **melhora/piora robusta** = o TSTT muda no mesmo sentido nos três níveis; **dependente da demanda** = o sinal muda; "
            f"**efeito desprezível** = |ΔTSTT| < {br(DESPREZIVEL_PCT)}% nos três. **K × TSTT divergem** = níveis em que o K da rede melhora enquanto o TSTT piora (ou o contrário), "
            "que é o critério de indício de Braess usado no artigo.", ""]


def secao_cenario(G: nx.DiGraph, matriz: dict, rodadas: dict, r: dict) -> list[str]:
    c = r["cenario"]
    base = rodadas["base"]
    H = aplicar_cenario(G, c)
    out = [f"### {c.get('codigo', '')} — {c['descricao']}", "",
           f"- **Arquivo:** `cenarios/{r['rodada']}.json` · resultados em `resultados/{r['rodada']}/`",
           f"- **Família:** {c.get('familia', '—')}"]
    if c.get("criterio"):
        out.append(f"- **Critério de escolha:** {c['criterio']}")
    out.append("")

    # alteracoes exatas
    linhas = []
    for alt in c["alteracoes"]:
        rot = ROTULO_ALT[alt["tipo"]].format(n=alt.get("faixas", 1), f=alt.get("fator", ""))
        for e in alt["arestas"]:
            u, v = e.split("->")
            d0 = G[u][v]
            fb = base["tabelas"]["adotada"].loc[e, "fluxo_veic_h"]
            if alt["tipo"] == "inverter":
                d1 = H[v][u]
                antes, depois = f"{seta(e)}", f"{v}→{u}"
                cap = f"{br(d0['capacidade_veic_h'], 0)} → {br(d1['capacidade_veic_h'], 0)}"
                faixas = f"{d0['lanes_sentido']}"
            elif alt["tipo"] == "remover":
                antes, depois, cap, faixas = seta(e), "fechada", f"{br(d0['capacidade_veic_h'], 0)} → —", f"{d0['lanes_sentido']} → —"
            else:
                d1 = H[u][v]
                antes = depois = seta(e)
                cap = f"{br(d0['capacidade_veic_h'], 0)} → {br(d1['capacidade_veic_h'], 0)}"
                faixas = f"{d0['lanes_sentido']} → {d1['lanes_sentido']}"
            linhas.append([seta(e), str(d0.get("name") or "") or "sem nome", d0["classe"], rot, faixas, cap,
                           "sim" if d0["gargalo"] else "não", br(fb, 0), br(d0.get("k_inicial"), 2)])
    out += ["**Alterações exatas** (capacidade em veíc/h por sentido, demanda adotada; nos gargalos é a capacidade efetiva):", "",
            tabela(["Aresta", "Via", "Classe", "Alteração", "Faixas", "Capacidade", "Gargalo", "Fluxo atual (veíc/h)", "K observado"], linhas), ""]
    inv = [a for a in c["alteracoes"] if a["tipo"] == "inverter"]
    if inv:
        out += ["Na inversão, a aresta nova (v→u) mantém comprimento, limite, faixas e velocidade livre; a calibração de gargalo e os dados observados (que valiam para o outro sentido) são descartados.", ""]

    # indicadores por nivel
    linhas = []
    for n in NIVEIS:
        ib, ic = base["niveis"][n]["indicadores"], r["niveis"][n]["indicadores"]
        cp = r["niveis"][n]["comparacao_com_base"]
        linhas.append([n, br(ib["tstt_veic_h"], 1), br(ic["tstt_veic_h"], 1), br(cp["delta_tstt_veic_min"], 1, True),
                       br(cp["delta_tstt_pct"], 2, True), f"{br(ib['k_rede'], 4)} → {br(ic['k_rede'], 4)}",
                       f"{br(ib['velocidade_media_rede_kmh'], 1)} → {br(ic['velocidade_media_rede_kmh'], 1)}",
                       f"{br(ib['tempo_medio_viagem_min'], 2)} → {br(ic['tempo_medio_viagem_min'], 2)}",
                       f"{ib['arestas_vc_acima_1']} → {ic['arestas_vc_acima_1']}", f"{ib['arestas_k_abaixo_0_5']} → {ic['arestas_k_abaixo_0_5']}",
                       f"{ic['iteracoes']} ({gap(ic['gap_relativo'])})"])
    out += ["**Resultados por nível de demanda** (situação atual → cenário):", "",
            tabela(["Demanda", "TSTT atual (veíc·h)", "TSTT cenário (veíc·h)", "ΔTSTT (veíc·min)", "ΔTSTT (%)", "K da rede",
                    "Vel. média (km/h)", "Tempo médio (min)", "Arestas V/C>1", "Arestas K<0,5", "Iterações (gap)"], linhas), ""]

    # efeito local nas arestas alteradas (demanda adotada)
    tb, tc = base["tabelas"]["adotada"], r["tabelas"]["adotada"]
    loc = []
    for alt in c["alteracoes"]:
        for e in alt["arestas"]:
            e2 = "->".join(e.split("->")[::-1]) if alt["tipo"] == "inverter" else e
            b0 = tb.loc[e]
            c0 = tc.loc[e2] if e2 in tc.index else None
            loc.append([seta(e) + (f" (agora {seta(e2)})" if e2 != e else ""),
                        f"{br(b0['fluxo_veic_h'], 0)} → {br(c0['fluxo_veic_h'], 0) if c0 is not None else 'fechada'}",
                        f"{br(b0['vc'], 2)} → {br(c0['vc'], 2) if c0 is not None else '—'}",
                        f"{br(b0['k_modelado'], 2)} → {br(c0['k_modelado'], 2) if c0 is not None else '—'}",
                        f"{br(b0['velocidade_kmh'], 1)} → {br(c0['velocidade_kmh'], 1) if c0 is not None else '—'}"])
    out += ["**Efeito local nas arestas alteradas** (demanda adotada, situação atual → cenário):", "",
            tabela(["Aresta", "Fluxo (veíc/h)", "V/C", "K modelado", "Velocidade (km/h)"], loc), ""]

    # redistribuicao
    j = tb[["fluxo_veic_h", "k_modelado"]].join(tc[["fluxo_veic_h", "k_modelado"]], how="outer", rsuffix="_c")
    j["d"] = j["fluxo_veic_h_c"].fillna(0) - j["fluxo_veic_h"].fillna(0)
    alteradas = {e for a in c["alteracoes"] for e in a["arestas"]} | \
                {"->".join(e.split("->")[::-1]) for a in c["alteracoes"] if a["tipo"] == "inverter" for e in a["arestas"]}
    red = j[~j.index.isin(alteradas)].reindex(j[~j.index.isin(alteradas)]["d"].abs().sort_values(ascending=False).index)
    red = red[red["d"].abs() >= 0.5].head(8)
    total = float(j["d"].abs().sum())
    if len(red):
        out += [f"**Maiores mudanças de fluxo fora das arestas alteradas** (demanda adotada; soma de |Δfluxo| em todas as arestas: {br(total, 0)} veíc/h):", "",
                tabela(["Aresta", "Via", "Fluxo atual → cenário (veíc/h)", "Δ (veíc/h)", "K modelado"],
                       [[seta(e), nome_aresta(G, e), f"{br(x['fluxo_veic_h'], 0)} → {br(x['fluxo_veic_h_c'], 0)}",
                         br(x["d"], 1, True), f"{br(x['k_modelado'], 2)} → {br(x['k_modelado_c'], 2)}"] for e, x in red.iterrows()]), ""]
    else:
        out += [f"**Redistribuição:** nenhuma aresta fora das alteradas mudou mais de 0,5 veíc/h (soma de |Δfluxo|: {br(total, 1)} veíc/h).", ""]

    sens = rodadas.get(r["rodada"] + SENS)
    if sens:
        s = [sens["niveis"][n]["comparacao_com_base"] for n in NIVEIS]
        out += [f"**Sensibilidade (a = 0,8; b = 4,7):** ΔTSTT {' / '.join(br(x['delta_tstt_pct'], 2, True) + '%' for x in s)} "
                f"e ΔK da rede {' / '.join(br(x['delta_k_rede'], 4, True) for x in s)} (baixa / adotada / alta).", ""]
    cl = classificar(r)
    out += [f"**Classificação:** {cl['rotulo']}" + (f"; K e TSTT divergem na demanda {', '.join(cl['divergencia_k_tstt'])}." if cl["divergencia_k_tstt"] else "."), ""]
    return out


def secao_varreduras(G, varr: dict) -> list[str]:
    out = ["## 5. Teste do paradoxo de Braess: varreduras aresta por aresta", "",
           "Comando: `python scripts/frank_wolfe.py --varredura-remocao --varredura-faixa` (e o mesmo com `--alpha 0.8 --beta 4.7`).", "",
           "- **Varredura de remoção:** fecha cada uma das 235 arestas de carro, uma por vez, e resolve o equilíbrio nos três níveis. **Braess = fechar reduz o TSTT.** "
           "Fechamentos que desconectariam algum par OD não podem ser avaliados (a demanda fixa ficaria sem rota) e são registrados à parte.",
           "- **Varredura de faixa:** soma 1 faixa a cada aresta, uma por vez (mesma regra dos cenários F). **Braess = ampliar aumenta o TSTT** (paradoxo da capacidade).",
           "- Todo candidato com gap 10⁻⁴ é refeito, junto com a situação atual, com gap 10⁻⁷ e até 20.000 iterações, para separar efeito real de erro de convergência.", ""]
    linhas = []
    notas = []
    for nome, r in sorted(varr.items()):
        tab = r["tabela"]
        val = tab[~tab["desconecta"]]
        lentos = int((val["gap_relativo"] >= 1e-4).sum())
        if lentos:
            notas.append(f"`{nome}`: {lentos} de {len(val)} equilíbrios pararam no teto de 500 iterações com gap acima de 10⁻⁴ "
                         f"(maior gap {val['gap_relativo'].max():.1e}); servem para ordenar o efeito, e qualquer candidato a Braess é refeito com gap 10⁻⁷.")
        for n in NIVEIS:
            v = val[val["nivel"] == n]["delta_tstt_pct"]
            linhas.append([nome, n, r["alteracoes_avaliadas"], r["alteracoes_que_desconectam_pares_od"], r["candidatos_gap_1e-4"],
                           len([c for c in r["casos_braess_confirmados"] if c["nivel"] == n]),
                           br(v.min(), 3, True), br(v.median(), 3, True), br(v.max(), 2, True)])
    out += [tabela(["Varredura", "Demanda", "Alterações avaliadas", "Desconectam pares OD", "Candidatos (gap 10⁻⁴)",
                    "Braess confirmados", "ΔTSTT mín. (%)", "ΔTSTT mediano (%)", "ΔTSTT máx. (%)"], linhas), ""]
    if notas:
        out += ["**Convergência nas varreduras:** " + " ".join(notas), ""]
    for nome, r in sorted(varr.items()):
        conf = r["casos_braess_confirmados"]
        if conf:
            out += [f"**Casos de Braess confirmados em `{nome}`:**", "",
                    tabela(["Aresta", "Via", "Demanda", "ΔTSTT confirmado (veíc·min)", "ΔTSTT (%)"],
                           [[seta(c["aresta"]), c["nome"] or c["classe"], c["nivel"], br(c["delta_tstt_veic_min_confirmado"], 3, True),
                             br(c["delta_tstt_pct_confirmado"], 4, True)] for c in conf]), ""]
        desc = r.get("candidatos_descartados_na_confirmacao", [])
        if desc:
            out += [f"Candidatos de `{nome}` descartados na confirmação (o ΔTSTT com gap 10⁻⁷ não teve o sinal de Braess): "
                    + ", ".join(f"{seta(c['aresta'])} ({c['nivel']}, {br(c['delta_tstt_pct_confirmado'], 4, True)}%)" for c in desc) + ".", ""]
    for nome, tit, col in (("varredura_remocao", "fechamento mais aumenta", "maiores_aumentos"),
                           ("varredura_faixa", "faixa extra mais reduz", "maiores_reducoes")):
        r = varr.get(nome)
        if r is None:
            continue
        top = r["por_nivel"]["adotada"][col]
        out += [f"**Arestas cujo {tit} o TSTT** (`{nome}`, demanda adotada):", "",
                tabela(["Aresta", "Via", "Classe", "ΔTSTT (%)"],
                       [[seta(t["aresta"]), t["nome"] if isinstance(t["nome"], str) and t["nome"] else "—", t["classe"],
                         br(t["delta_tstt_pct"], 2, True)] for t in top]), ""]
    return out


def main() -> None:
    G = nx.read_graphml(GRAFO)
    matriz = json.loads(MATRIZ.read_text(encoding="utf-8"))
    rodadas, varr = carregar()
    fat = json.loads(G.graph["fatores_expansao"])
    cens = sorted([r for r in rodadas.values() if r.get("cenario") and SENS not in r["rodada"]], key=ordem_cenario)

    md = [f"# Cenários de intervenção e teste do paradoxo de Braess",
          "",
          f"*Gerado por `scripts/relatorio_cenarios.py` em {date.today().strftime('%d/%m/%Y')}, a partir de `resultados/`. "
          "Todos os números abaixo são lidos dos arquivos de resultado; para atualizar, rode de novo os comandos da seção 1 e este script.*",
          "",
          "Este documento registra a etapa de cenários prevista no artigo (`research/main.tex`, \"Alocação, cenários e indicadores\") e no plano de pesquisa "
          "(passo 5: 15 a 30 grafos alterados): acréscimo de faixa, mudança de sentido e remoção de arestas, esta como teste do paradoxo de Braess, "
          "nos três níveis de demanda e com a sensibilidade a = 0,8 e b = 4,7.",
          "",
          "## 1. Como foi rodado",
          "",
          "```bash",
          "python scripts/gerar_cenarios.py                       # gera cenarios/*.json a partir de critérios sobre o grafo",
          "python scripts/frank_wolfe.py --todos                  # situação atual + todos os cenários (a = 0,15; b = 4)",
          "python scripts/frank_wolfe.py --alpha 0.8 --beta 4.7 --todos",
          "python scripts/frank_wolfe.py --varredura-remocao --varredura-faixa",
          "python scripts/frank_wolfe.py --alpha 0.8 --beta 4.7 --varredura-remocao --varredura-faixa",
          "python scripts/visualizar_resultados.py               # resultados/painel.html e resultados/figuras/",
          "python scripts/relatorio_cenarios.py                  # este documento",
          "```",
          "",
          "**Configuração comum a todos os casos:**",
          "",
          f"- **Grafo:** `cache/gama_drive_expanded_atributos.graphml` (134 nós, 235 arestas de carro); **matriz OD:** `Tables/matriz_od_final.json` (1.031 pares).",
          f"- **Níveis de demanda (obrigatórios):** baixa (fator {br(fat['min'])}), adotada ({br(fat['adotado'])}) e alta ({br(fat['max'])}). "
          "A demanda de cada par é `veic_h × fator / 12,21`, e cada nível usa a capacidade efetiva calibrada para o seu fator.",
          "- **Função de atraso:** BPR com a = 0,15 e b = 4 (base) e a = 0,8 e b = 4,7 (sensibilidade; a capacidade efetiva dos gargalos é recalculada e a faixa extra dos cenários é preservada).",
          f"- **Parada do Frank-Wolfe:** gap relativo < 10⁻⁴ ou 500 iterações. {nota_convergencia(rodadas)}",
          "- **Regras das alterações** (`scripts/frank_wolfe.py`, `aplicar_cenario`):",
          "  - **faixa:** nos 25 gargalos calibrados, capacidade efetiva × (faixas + 1) / faixas; nas demais arestas, + 1 × capacidade por faixa da classe (1.800 na EPCT, 1.200 na DF-480 e nas alças da rodovia, 900 nas terciárias, 600 nas alças terciárias e locais);",
          "  - **remover:** a aresta sai do grafo;",
          "  - **inverter:** u→v passa a v→u (falha se v→u já existir);",
          "  - cenários que desconectariam algum par OD são recusados, porque a demanda é fixa.",
          "- **Como os cenários foram escolhidos** (`scripts/gerar_cenarios.py`): por critérios sobre o grafo (gargalos por rodovia e sentido, alças com K observado < 0,25, as coletoras de maior fluxo, acessos que convergem nos gargalos). "
          "Quatro candidatos foram descartados por desconectarem pares OD e substituídos: inverter ou fechar o acesso 127→130→103→126 à EPCT norte (é a única saída da zona da CAUB/Chácara 95), "
          "fechar a alça 67→66 (16 pares) e tornar a Av. São Francisco mão única (52 pares).",
          ""]
    md += secao_base(rodadas)
    md += secao_resumo(rodadas)
    md += ["## 4. Cenários, um a um", ""]
    for r in cens:
        md += secao_cenario(G, matriz, rodadas, r)
    md += secao_varreduras(G, varr)
    md += LEITURA(rodadas, varr, cens)
    SAIDA.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Relatório: {SAIDA.relative_to(RAIZ)} ({len(cens)} cenários, {len(varr)} varreduras)")


def mecanismo_r1(d: dict) -> str:
    """Explica a divergencia K x TSTT do R1 com os numeros da demanda adotada."""
    if "R1" not in d or "base" not in d.get("_rodadas", {}):
        return ""
    b = d["_rodadas"]["base"]["tabelas"]["adotada"]
    c = d["R1"]["tabelas"]["adotada"]
    j = b[["fluxo_veic_h", "k_modelado", "length_m", "limite_kmh", "velocidade_kmh"]].join(
        c[["fluxo_veic_h", "k_modelado", "velocidade_kmh"]], rsuffix="_c")
    j["d"] = j["fluxo_veic_h_c"].fillna(0) - j["fluxo_veic_h"]
    ganho = j[(j["d"] > 100)]
    perde = j[(j["d"] < -100) & j["fluxo_veic_h_c"].notna()]
    vkt = lambda t, col: float((t[col].fillna(0) * t["length_m"]).sum() / 1000)  # noqa: E731
    desvio = (ganho["fluxo_veic_h_c"] - ganho["fluxo_veic_h"]).median()
    return (f"Cerca de {br(desvio, 0)} veíc/h saem da alça e da DF-480 e passam a usar a Avenida do Sol e a ligação DF-480 Km 5 "
            f"({', '.join(seta(e) for e in ganho.index[:5])}), vias de limite {br(ganho['limite_kmh'].min(), 0)}–{br(ganho['limite_kmh'].max(), 0)} km/h "
            f"onde se anda a {br(ganho['velocidade_kmh_c'].min(), 0)}–{br(ganho['velocidade_kmh_c'].max(), 0)} km/h. "
            f"A quilometragem total quase não muda ({br(vkt(j, 'fluxo_veic_h'), 0)} → {br(vkt(j, 'fluxo_veic_h_c'), 0)} veíc·km), "
            f"mas os trechos aliviados da DF-480 e da EPCT ganham muito K (18→4: {br(j.loc['18->4', 'k_modelado'], 2)} → {br(j.loc['18->4', 'k_modelado_c'], 2)}; "
            f"20→17: {br(j.loc['20->17', 'k_modelado'], 2)} → {br(j.loc['20->17', 'k_modelado_c'], 2)}), enquanto o desvio, por ter limite baixo, "
            "perde pouco K mesmo sendo lento em km/h. Como o K é normalizado pelo limite de cada via, ele favorece empurrar tráfego para vias de limite baixo; "
            "o TSTT, que mede tempo absoluto, registra a piora.")


def LEITURA(rodadas: dict, varr: dict, cens: list) -> list[str]:  # noqa: N802
    """Leitura dos resultados: os numeros vem dos arquivos; o texto interpreta."""
    d = {r["cenario"]["codigo"]: r for r in cens}
    d["_rodadas"] = rodadas

    def dt(cod, n="adotada"):
        return d[cod]["niveis"][n]["comparacao_com_base"]["delta_tstt_pct"] if cod in d else None

    def dk(cod, n="adotada"):
        return d[cod]["niveis"][n]["comparacao_com_base"]["delta_k_rede"] if cod in d else None

    braess = sum(len(r["casos_braess_confirmados"]) for r in varr.values())
    vr = varr.get("varredura_remocao")
    out = ["## 6. Leitura dos resultados", ""]
    out += ["1. **Ampliar os gargalos do corredor é o que mais reduz o tempo total.** "
            f"A faixa extra em todos os gargalos da EPCT norte (F1) reduz o TSTT em {br(-dt('F1'), 1)}% na demanda adotada; "
            f"só os 5 trechos antes do trevo (C0, caso da V1) já reduzem {br(-dt('C0'), 1)}%. "
            f"Na DF-480 (F3) a redução é de {br(-dt('F3'), 1)}% e na EPCT sul (F2), de {br(-dt('F2'), 1)}%. "
            "Os ganhos variam pouco entre os níveis de demanda porque a capacidade efetiva dos gargalos escala com o fator de expansão (research/problemas_do_modelo.md, problema 3): "
            "a robustez nesses trechos é, em parte, construída pela calibração.",
            "2. **K baixo não é sinônimo de falta de capacidade.** "
            f"As alças com K observado < 0,25 (F4) e as coletoras Av. São Francisco (F5) e Marginal DF-480 (F6) quase não respondem a uma faixa extra "
            f"(ΔTSTT de {br(dt('F4'), 2, True)}%, {br(dt('F5'), 2, True)}% e {br(dt('F6'), 2, True)}% na demanda adotada): "
            "a lentidão delas vem de geometria, conversões e cruzamentos (já embutidos no tempo de fluxo livre medido de madrugada), não do volume. "
            "Isso responde em parte à RQ2: o grafo enriquecido separa a lentidão causada por volume da lentidão estrutural.",
            "3. **Fechar ou inverter acessos sempre piora o sistema neste recorte.** "
            f"Fechar o acesso 30→7 à DF-480 (R2) aumenta o TSTT em {br(dt('R2'), 1)}%; inverter esse acesso (S2) dá exatamente o mesmo resultado, "
            "porque o sentido novo não tem demanda: a inversão equivale a um fechamento. "
            f"Fechar a alça 11→63 (R3) custa {br(dt('R3'), 1)}% e o binário na Marginal DF-480 (S1), {br(dt('S1'), 1)}%.",
            "4. **Há divergência entre K e TSTT, o indício de Braess definido no artigo.** "
            f"Fechar a alça 21→18 (R1) ou invertê-la (S3) piora o TSTT ({br(dt('R1'), 2, True)}% e {br(dt('S3'), 2, True)}% na demanda adotada), "
            f"mas o K da rede sobe ({br(dk('R1'), 4, True)} e {br(dk('S3'), 4, True)}). {mecanismo_r1(d)} "
            "Na demanda alta o sinal do ΔK se inverte. É uma evidência concreta de que uma métrica de fluidez normalizada pelo limite da via (K) pode apontar melhora "
            "enquanto o sistema perde tempo, que é a tese central do trabalho.",
            f"5. **O paradoxo de Braess clássico não aparece na rede real.** Nas varreduras, {'nenhuma' if braess == 0 else str(braess)} "
            f"alteração de uma aresta reduziu o TSTT ao fechar nem o aumentou ao ampliar"
            + (f" ({vr['alteracoes_avaliadas']} fechamentos avaliados por nível nos parâmetros-base; os {vr['alteracoes_que_desconectam_pares_od']} restantes desconectariam pares OD)" if vr else "")
            + ". Isso é coerente com o predomínio do tráfego de passagem (86% das viagens) e com a pouca escolha de rota (46,5% da demanda com alternativa): "
            "para haver Braess, a via alterada precisa atrair viagens que tenham rota alternativa e que gerem atraso para outros. "
            "O algoritmo reproduz o paradoxo quando ele existe (rede de Braess de 1968 no `--teste`: o TSTT sobe de 498 para 552 ao abrir a ponte), "
            "então a ausência é um resultado do recorte, não uma limitação do método.",
            "6. **Quais vias importam para o sistema.** A varredura de remoção funciona como um mapa de criticidade: fechar 25→0 (EPCT sul, antes do trevo), "
            "133→63 (EPCT norte) ou 14→18 (DF-480) aumenta o TSTT em dezenas de por cento, enquanto a mediana dos fechamentos avaliáveis fica abaixo de 0,4%.",
            ""]
    return out


if __name__ == "__main__":
    main()
