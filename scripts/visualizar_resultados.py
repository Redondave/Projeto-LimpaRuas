"""
Visualizacao dos resultados do Frank-Wolfe (scripts/frank_wolfe.py).

Le todas as rodadas em resultados/*/resumo.json (situacao atual e cenarios, em
cada nivel de demanda e conjunto de parametros da BPR) e as varreduras de
Braess (resultados/varredura_*/), e gera:

    resultados/painel.html     painel interativo: mapa (fluxo, V/C, K, diferencas
                               para a situacao atual, efeito de fechar ou ampliar
                               cada aresta) com legenda descritiva; ficha do
                               cenario; indicadores; convergencia; variacao do
                               TSTT por cenario; K x TSTT; varreduras de Braess;
                               tabelas. Abre direto no navegador (precisa de
                               internet so para o fundo do mapa e as bibliotecas).
    resultados/figuras/*.png   figuras estaticas para o artigo

Uso (da raiz do repositorio):
    python scripts/visualizar_resultados.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
import networkx as nx
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import LineString

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
GRAFO = RAIZ / "cache/gama_drive_expanded_atributos.graphml"
RESULTADOS = RAIZ / "resultados"
FIGURAS = RESULTADOS / "figuras"
NIVEIS = ["baixa", "adotada", "alta"]
FAMILIAS = {"faixa": "Faixa adicional", "sentido": "Sentido de circulação", "remocao": "Remoção / fechamento",
            "braess": "Paradoxo de Braess", "": "Outros"}
DESPREZIVEL_PCT = 0.05      # |delta TSTT| abaixo disso nos tres niveis: efeito desprezivel

# paleta de referencia (skill dataviz, references/palette.md)
AZUL_SEQ = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
ORDINAL_NIVEIS = {"baixa": "#86b6ef", "adotada": "#2a78d6", "alta": "#104281"}
SERIE = ["#2a78d6", "#eb6834"]
DIVERGENTE = ["#2a78d6", "#f0efec", "#e34948"]
TINTA, TINTA_2, MUDO, GRADE, BASE_LINHA = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def geometrias(G: nx.DiGraph) -> dict:
    """(u, v) -> LineString em EPSG:31983, no sentido de circulacao."""
    pos = {n: (float(d["x"]), float(d["y"])) for n, d in G.nodes(data=True)}
    return {(u, v): (wkt.loads(d["geometry"]) if "geometry" in d else LineString([pos[u], pos[v]]))
            for u, v, d in G.edges(data=True)}


def geometria(geoms: dict, u: str, v: str) -> LineString:
    if (u, v) in geoms:
        return geoms[(u, v)]
    return LineString(list(geoms[(v, u)].coords)[::-1])     # aresta invertida num cenario


def sufixo_bpr(G: nx.DiGraph, bpr: dict) -> str:
    if math.isclose(bpr["alpha"], G.graph["bpr_alpha"]) and math.isclose(bpr["beta"], G.graph["bpr_beta"]):
        return ""
    return f"_a{bpr['alpha']:g}_b{bpr['beta']:g}"


def carregar_rodadas() -> dict:
    rodadas = {}
    for resumo in sorted(RESULTADOS.glob("*/resumo.json")):
        if resumo.parent.name.startswith("varredura_"):
            continue
        r = json.loads(resumo.read_text(encoding="utf-8"))
        r["tabelas"] = {n: pd.read_csv(resumo.parent / f"arestas_{n}.csv", encoding="utf-8-sig",
                                       dtype={"u": str, "v": str}) for n in NIVEIS}
        rodadas[r["rodada"]] = r
    if not rodadas:
        sys.exit("Nenhum resultado em resultados/. Rode antes: python scripts/frank_wolfe.py")
    return rodadas


def carregar_varreduras(G: nx.DiGraph) -> dict:
    """{sufixo: {modo: {"resumo": ..., "tabela": DataFrame}}}"""
    out = {}
    for resumo in sorted(RESULTADOS.glob("varredura_*/resumo.json")):
        r = json.loads(resumo.read_text(encoding="utf-8"))
        if "modo" not in r:
            continue
        tab = pd.read_csv(resumo.parent / "varredura.csv", encoding="utf-8-sig")
        out.setdefault(sufixo_bpr(G, r["bpr"]), {})[r["modo"]] = {"resumo": r, "tabela": tab}
    return out


def base_de(rodadas: dict, r: dict) -> dict | None:
    if r.get("cenario") is None:
        return None
    return rodadas.get(Path(r["base"]).name)


def classificar(r: dict) -> dict | None:
    """Classificacao do cenario pelo sinal do delta TSTT nos tres niveis (artigo:
    robusta / dependente da demanda), e niveis em que K e TSTT divergem."""
    if not r.get("cenario"):
        return None
    d = [r["niveis"][n]["comparacao_com_base"]["delta_tstt_pct"] for n in NIVEIS]
    dk = [r["niveis"][n]["comparacao_com_base"]["delta_k_rede"] for n in NIVEIS]
    relevantes = [(n, x) for n, x in zip(NIVEIS, d) if abs(x) >= DESPREZIVEL_PCT]
    sinais = {x > 0 for _, x in relevantes}
    if not relevantes:
        rotulo = "efeito desprezível"
    elif len(sinais) > 1:
        rotulo = "dependente da demanda"
    elif len(relevantes) == len(NIVEIS):
        rotulo = "piora robusta" if sinais == {True} else "melhora robusta"
    else:
        rotulo = (f"{'piora' if sinais == {True} else 'melhora'} pequena (só na demanda "
                  f"{', '.join(n for n, _ in relevantes)})")
    divergem = [n for n, x, k in zip(NIVEIS, d, dk)
                if (x > DESPREZIVEL_PCT and k > 1e-4) or (x < -DESPREZIVEL_PCT and k < -1e-4)]
    return {"rotulo": rotulo, "divergencia_k_tstt": divergem}


def ordem_cenario(r: dict) -> tuple:
    c = r.get("cenario") or {}
    cod = c.get("codigo", "")
    return (r["bpr"]["alpha"], r["bpr"]["beta"], 0 if not c else 1, "CFSRB".find(cod[:1]) if cod else 9, cod, r["rodada"])


# ---------------------------------------------------------------------------
# Painel interativo
# ---------------------------------------------------------------------------
def dados_painel(G: nx.DiGraph, rodadas: dict, varreduras: dict) -> dict:
    geoms = geometrias(G)
    para_wgs = Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True)

    def latlon(linha: LineString):
        return [[round(lat, 6), round(lon, 6)] for lon, lat in (para_wgs.transform(x, y) for x, y in linha.coords)]

    arestas = {}
    for r in rodadas.values():
        for t in r["tabelas"].values():
            for row in t.itertuples():
                if row.aresta not in arestas:
                    arestas[row.aresta] = {
                        "coords": latlon(geometria(geoms, row.u, row.v)),
                        "nome": "" if pd.isna(row.nome) else row.nome, "classe": row.classe,
                        "L": row.length_m, "lim": row.limite_kmh, "v0": row.v0_kmh,
                        "gargalo": bool(row.gargalo),
                        "k_obs": None if pd.isna(row.k_obs) else row.k_obs,
                        "t_obs": None if pd.isna(row.t_obs_min) else row.t_obs_min}
    saida = {"arestas": arestas, "rodadas": {}, "varreduras": {}}
    for r in sorted(rodadas.values(), key=ordem_cenario):
        base = base_de(rodadas, r)
        niveis = {}
        for n in NIVEIS:
            t = r["tabelas"][n]
            niveis[n] = {
                "fator": r["niveis"][n]["fator"],
                "indicadores": r["niveis"][n]["indicadores"],
                "convergencia": [[h["iteracao"], h["gap"]] for h in r["niveis"][n]["convergencia"]],
                "comparacao": r["niveis"][n].get("comparacao_com_base"),
                "conferencias": r["niveis"][n].get("conferencias"),
                "valores": {row.aresta: [row.fluxo_veic_h, row.vc, row.tempo_min, row.velocidade_kmh,
                                         row.k_modelado, row.capacidade_veic_h, row.faixas]
                            for row in t.itertuples()},
            }
        saida["rodadas"][r["rodada"]] = {
            "cenario": r.get("cenario"), "base": Path(r["base"]).name if base else None,
            "bpr": r["bpr"], "sufixo": sufixo_bpr(G, r["bpr"]), "gerado_em": r["gerado_em"],
            "classificacao": classificar(r), "niveis": niveis}
    for suf, modos in varreduras.items():
        saida["varreduras"][suf] = {}
        for modo, v in modos.items():
            efeito = {}
            for row in v["tabela"].itertuples():
                val = None if row.desconecta else round(float(row.delta_tstt_pct), 4)
                efeito.setdefault(row.aresta, {})[row.nivel] = [val, bool(row.desconecta)]
            res = v["resumo"]
            saida["varreduras"][suf][modo] = {
                "resumo": {k: res[k] for k in ("alteracao", "criterio_braess", "arestas_testadas",
                                               "alteracoes_que_desconectam_pares_od", "alteracoes_avaliadas",
                                               "candidatos_gap_1e-4", "casos_braess_confirmados")},
                "efeito": efeito}
    return saida


PAINEL = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Resultados Frank-Wolfe</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e;
  --muted: #898781; --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --good: #006300; --critical: #d03b3b;
  --seq-0: #86b6ef; --seq-1: #2a78d6; --seq-2: #0d366b;
  --div-neg: #2a78d6; --div-mid: #f0efec; --div-pos: #e34948;
  --ord-baixa: #86b6ef; --ord-adotada: #2a78d6; --ord-alta: #104281;
  --destaque: #eb6834; --removida: #898781; --wash: rgba(235,104,52,0.08);
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7;
    --muted: #898781; --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --good: #0ca30c; --critical: #e66767;
    --seq-0: #184f95; --seq-1: #3987e5; --seq-2: #cde2fb;
    --div-neg: #3987e5; --div-mid: #383835; --div-pos: #e66767;
    --ord-baixa: #184f95; --ord-adotada: #3987e5; --ord-alta: #9ec5f4;
    --destaque: #d95926; --wash: rgba(217,89,38,0.12);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7;
  --muted: #898781; --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --good: #0ca30c; --critical: #e66767;
  --seq-0: #184f95; --seq-1: #3987e5; --seq-2: #cde2fb;
  --div-neg: #3987e5; --div-mid: #383835; --div-pos: #e66767;
  --ord-baixa: #184f95; --ord-adotada: #3987e5; --ord-alta: #9ec5f4;
  --destaque: #d95926; --wash: rgba(217,89,38,0.12);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text-primary);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1240px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; font-weight: 650; }
h2 { font-size: 15px; margin: 0 0 12px; font-weight: 600; }
h3 { font-size: 13px; margin: 0 0 8px; font-weight: 600; }
.sub { color: var(--text-secondary); margin: 0 0 20px; }
.filtros { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: end; margin-bottom: 16px; }
.filtros label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
select, button, input[type=search] { font: inherit; color: var(--text-primary); background: var(--surface-1);
  border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; }
#f-rodada { max-width: 100%; }
.segmentado { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.segmentado button { border: 0; border-radius: 0; padding: 6px 12px; background: var(--surface-1); cursor: pointer; }
.segmentado button[aria-pressed="true"] { background: var(--text-primary); color: var(--surface-1); }
.check { flex-direction: row !important; align-items: center; gap: 6px !important; font-size: 13px !important; color: var(--text-primary) !important; }
.cartao { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.ficha { margin-bottom: 16px; border-left: 3px solid var(--destaque); }
.ficha .linha-ficha { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--text-secondary); margin-top: 6px; }
.chip { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-secondary); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile .rot { font-size: 12px; color: var(--text-secondary); }
.tile .val { font-size: 24px; font-weight: 600; margin-top: 2px; }
.tile .det { font-size: 12px; color: var(--text-secondary); margin-top: 2px; min-height: 18px; }
.melhor { color: var(--good); } .pior { color: var(--critical); }
#mapa { height: 560px; border-radius: 8px; }
.grade2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin-top: 16px; }
.grade2 > * { min-width: 0; }
@media (max-width: 860px) { .grade2 { grid-template-columns: minmax(0, 1fr); } #mapa { height: 420px; } }
.grafico svg { width: 100%; height: auto; display: block; overflow: visible; }
.grafico text { fill: var(--muted); font-size: 11px; }
.grafico .rotulo { fill: var(--text-secondary); font-size: 12px; }
.legenda-fora { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 12px; color: var(--text-secondary); }
.tip { position: fixed; pointer-events: none; background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,.12); display: none; z-index: 1000; max-width: 300px; }
.tip strong { font-size: 13px; }
.tip .linha { display: flex; align-items: center; gap: 6px; }
.tip .chave { width: 14px; height: 2px; display: inline-block; }
/* legenda dentro do mapa */
.leg { background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; width: 250px; max-height: 70vh; overflow-y: auto; font: 12px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
  box-shadow: 0 2px 10px rgba(0,0,0,.10); }
.leg button { width: 100%; text-align: left; border: 0; padding: 0; background: none; font-weight: 600; cursor: pointer; font-size: 12px; }
.leg .corpo { margin-top: 8px; }
.leg .desc { color: var(--text-secondary); margin: 0 0 8px; }
.leg .extremos { display: flex; justify-content: space-between; color: var(--text-secondary); margin-top: -2px; }
.leg svg text { fill: var(--text-secondary); font-size: 10px; }
.leg .sim { display: grid; grid-template-columns: 34px 1fr; gap: 4px 8px; align-items: center; margin-top: 8px; color: var(--text-secondary); }
.leg .sec { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--grid); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: right; padding: 6px 8px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; white-space: nowrap; }
th:first-child, td:first-child, th.txt, td.txt { text-align: left; }
th { color: var(--text-secondary); font-weight: 600; cursor: pointer; user-select: none; }
tr.atual td { background: var(--wash); }
.tabela { overflow-x: auto; }
.nota { font-size: 12px; color: var(--text-secondary); margin-top: 8px; }
.leaflet-tooltip { background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--border); }
.leaflet-container { background: var(--page); }
footer { color: var(--muted); font-size: 12px; margin-top: 24px; }
</style>
</head>
<body>
<main>
  <h1>Alocação de tráfego — trevo EPCT / EPIP / DF-480 (Gama)</h1>
  <p class="sub" id="sub"></p>

  <div class="filtros" role="group" aria-label="Filtros">
    <label>Rodada<select id="f-rodada"></select></label>
    <label>Nível de demanda<span class="segmentado" id="f-nivel"></span></label>
    <label>Cor do mapa<select id="f-metrica"></select></label>
    <label class="check"><input type="checkbox" id="f-gargalo" checked> contornar os 25 gargalos calibrados</label>
  </div>

  <div class="cartao ficha" id="ficha" hidden></div>
  <div class="tiles" id="tiles"></div>

  <div class="cartao">
    <h2 id="t-mapa">Mapa</h2>
    <div id="mapa" role="img" aria-label="Mapa da rede com as arestas coloridas pela métrica escolhida"></div>
    <p class="nota">Passe o mouse ou toque numa aresta para ver os valores. A legenda no canto do mapa explica cores, espessuras e símbolos; a tabela "Arestas" no fim da página traz os mesmos números.</p>
  </div>

  <div class="grade2">
    <div class="cartao grafico"><h2 id="t-delta">Variação do TSTT por cenário</h2><div id="g-delta"></div></div>
    <div class="cartao grafico"><h2>K da rede × TSTT: as duas métricas concordam?</h2><div id="g-kt"></div></div>
  </div>

  <div class="cartao" style="margin-top:16px">
    <h2>Teste do paradoxo de Braess: varreduras aresta por aresta</h2>
    <p class="nota" style="margin-top:0">Cada aresta de carro é alterada sozinha e o equilíbrio é recalculado nos três níveis de demanda. Há paradoxo de Braess se fechar uma via <em>reduz</em> o TSTT, ou se ampliá-la <em>aumenta</em> o TSTT. Os candidatos são refeitos com gap 10⁻⁷ antes de serem confirmados. Os mapas de efeito estão no seletor "Cor do mapa" quando a rodada é a situação atual.</p>
    <div class="grade2" style="margin-top:8px" id="varreduras"></div>
  </div>

  <div class="grade2">
    <div class="cartao grafico"><h2>Convergência (gap relativo por iteração)</h2><div id="g-conv"></div>
      <p class="nota">Critério de parada: gap relativo &lt; 10⁻⁴ ou 500 iterações.</p></div>
    <div class="cartao" id="c-conf">
      <h2>Conferência da situação atual com o observado (demanda adotada)</h2>
      <div class="tabela"><table id="tab-conf"></table></div>
      <p class="nota">Não é validação independente: as passagens vêm da mesma amostra TomTom da matriz, os contadores calibram o fator de expansão e o tempo observado calibra os gargalos (research/problemas_do_modelo.md, problema 2).</p>
    </div>
  </div>

  <div class="cartao" style="margin-top:16px">
    <h2>Comparação entre rodadas</h2>
    <div class="tabela"><table id="tab-rodadas"></table></div>
    <p class="nota">Classificação (artigo, seção de cenários): <strong>melhora/piora robusta</strong> = o TSTT muda no mesmo sentido nos três níveis de demanda; <strong>dependente da demanda</strong> = o sinal muda entre níveis; <strong>efeito desprezível</strong> = |ΔTSTT| &lt; 0,05% nos três. "K × TSTT divergem" marca os níveis em que o K da rede melhora enquanto o TSTT piora (ou o contrário).</p>
  </div>

  <div class="cartao" style="margin-top:16px">
    <h2>Arestas</h2>
    <div class="filtros" style="margin-bottom:8px">
      <label>Buscar por nome ou aresta<input id="f-busca" type="search" placeholder="ex.: Contorno, 63->102"></label>
      <button id="b-todas">Mostrar todas</button>
    </div>
    <div class="tabela"><table id="tab-arestas"></table></div>
  </div>
  <footer id="rodape"></footer>
</main>
<div class="tip" id="tip"></div>
<script id="dados" type="application/json">__DADOS__</script>
<script>
const D = JSON.parse(document.getElementById("dados").textContent);
const NIVEIS = ["baixa", "adotada", "alta"];
const FAMILIAS = {faixa: "Faixa adicional", sentido: "Sentido de circulação", remocao: "Remoção / fechamento", braess: "Paradoxo de Braess"};
const ALT = {faixa: "faixa adicional", remover: "removida", inverter: "invertida", capacidade: "capacidade alterada"};
const fmt = (v, d = 0) => v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", {minimumFractionDigits: d, maximumFractionDigits: d});
const sinal = (v, d) => v == null ? "—" : (Number(v.toFixed(d)) === 0 ? fmt(0, d) : (v > 0 ? "+" : "") + fmt(v, d));
const fmtGap = g => g < 1e-12 ? "< 10⁻¹²" : g.toExponential(1).replace(".", ",");
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const el = (tag, attrs = {}, ...filhos) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else e.setAttribute(k, v); }
  for (const f of filhos) if (f != null) e.append(f instanceof Node ? f : document.createTextNode(String(f))); return e; };
const I = {fluxo: 0, vc: 1, tempo: 2, vel: 3, k: 4, cap: 5, faixas: 6};
const estreito = () => innerWidth < 640;

const estado = {rodada: "base" in D.rodadas ? "base" : Object.keys(D.rodadas)[0],
                nivel: "adotada", metrica: "vc", gargalo: true, todas: false, busca: "", ordem: null, legendaAberta: !estreito()};

const METRICAS = {
  vc: {rot: "V/C (volume ÷ capacidade)", tipo: "seq", dom: [0, 1.5], fmt: v => fmt(v, 2), tick: 1,
       desc: "Quanto da capacidade do trecho está ocupada no equilíbrio. Acima de 1, chegam mais veículos do que o trecho escoa (nos gargalos, a capacidade é a efetiva, calibrada pelo tempo observado).",
       ext: ["folga", "acima da capacidade"]},
  k: {rot: "K modelado (velocidade ÷ limite)", tipo: "seq-inv", dom: [0, 1], fmt: v => fmt(v, 2), tick: 1,
      desc: "Índice de desempenho de velocidade (SPI) no equilíbrio: velocidade modelada dividida pelo limite da via. Mais escuro = mais lento.",
      ext: ["lento", "no limite"]},
  fluxo: {rot: "Fluxo (veíc/h)", tipo: "seq", dom: null, fmt: v => fmt(v, 0), tick: 0,
          desc: "Veículos por hora em cada sentido do trecho, no equilíbrio do usuário.", ext: ["pouco", "muito"]},
  k_obs: {rot: "K observado no pico (TomTom)", tipo: "seq-inv", dom: [0, 1], fmt: v => fmt(v, 2), tick: 1,
          desc: "K medido pela TomTom (julho/2026, 18h–19h). É o mesmo em todas as rodadas: serve de referência.", ext: ["lento", "no limite"]},
  razao_tempo: {rot: "Tempo modelado ÷ observado", tipo: "div", dom: [0.5, 1, 1.5], fmt: v => fmt(v, 2), tick: 1,
                desc: "Compara o tempo do modelo com o medido no pico. Cinza = o modelo acerta; azul = modelo mais rápido que a realidade; vermelho = mais lento.",
                ext: ["modelo mais rápido", "modelo mais lento"]},
  delta_fluxo: {rot: "Δ fluxo vs situação atual (veíc/h)", tipo: "div", dom: null, fmt: v => sinal(v, 0), tick: 0, cen: true,
                desc: "Diferença de fluxo para a situação atual, no mesmo nível de demanda: mostra para onde o tráfego foi.",
                ext: ["perdeu veículos", "ganhou veículos"]},
  delta_k: {rot: "Δ K vs situação atual", tipo: "div-inv", dom: null, fmt: v => sinal(v, 3), tick: 2, cen: true,
            desc: "Diferença de K para a situação atual: azul = o trecho ficou mais rápido; vermelho = mais lento.",
            ext: ["K caiu", "K subiu"]},
  efeito_remocao: {rot: "Efeito no TSTT de fechar a aresta (%)", tipo: "div", dom: [-10, 0, 10], fmt: v => sinal(v, 2) + "%", tick: 0, varredura: "remocao",
                   desc: "Quanto o tempo total do sistema muda se esta aresta for fechada (varredura). Vermelho = a via é importante; azul = fechá-la melhoraria o sistema (Braess). Valores acima de 10% saturam a cor.",
                   ext: ["fechar ajuda (Braess)", "fechar piora"]},
  efeito_faixa: {rot: "Efeito no TSTT de +1 faixa na aresta (%)", tipo: "div", dom: [-10, 0, 10], fmt: v => sinal(v, 2) + "%", tick: 0, varredura: "faixa",
                 desc: "Quanto o tempo total do sistema muda com uma faixa a mais nesta aresta (varredura). Azul = a faixa ajuda; vermelho = piora o sistema (Braess). Valores além de ±10% saturam a cor.",
                 ext: ["faixa ajuda", "faixa piora (Braess)"]},
};

const rodadaAtual = () => D.rodadas[estado.rodada];
const nivelAtual = () => rodadaAtual().niveis[estado.nivel];
const baseAtual = () => { const r = rodadaAtual(); return r.base ? D.rodadas[r.base] : null; };
const varreduraAtual = modo => (D.varreduras[rodadaAtual().sufixo] || {})[modo];
const nomeCurto = r => { const c = r.cenario; if (!c) return r.sufixo ? "Situação atual (a = 0,8)" : "Situação atual";
  return (c.codigo ? c.codigo + " · " : "") + c.descricao; };

function alteracoes() {
  const c = rodadaAtual().cenario, m = {};
  if (c) for (const a of c.alteracoes) for (const e of a.arestas) {
    if (a.tipo === "inverter") { const [u, v] = e.split("->"); m[`${v}->${u}`] = "invertida (sentido novo)"; m[e] = "invertida (sentido antigo)"; }
    else m[e] = a.tipo === "faixa" ? `+${a.faixas || 1} faixa` : ALT[a.tipo] || a.tipo;
  }
  return m;
}

function valorMetrica(id, m) {
  const val = nivelAtual().valores[id], a = D.arestas[id];
  const cfg = METRICAS[m];
  if (cfg.varredura) { const v = varreduraAtual(cfg.varredura); const e = v && v.efeito[id]; return e ? e[estado.nivel][0] : null; }
  if (!val) return null;
  if (m === "vc") return val[I.vc];
  if (m === "k") return val[I.k];
  if (m === "fluxo") return val[I.fluxo];
  if (m === "k_obs") return a.k_obs;
  if (m === "razao_tempo") return a.t_obs ? val[I.tempo] / a.t_obs : null;
  const b = baseAtual(); if (!b) return null;
  const vb = b.niveis[estado.nivel].valores[id];
  if (m === "delta_fluxo") return val[I.fluxo] - (vb ? vb[I.fluxo] : 0);
  if (m === "delta_k") return vb ? val[I.k] - vb[I.k] : null;
}
const desconecta = id => { const cfg = METRICAS[estado.metrica]; if (!cfg.varredura) return false;
  const v = varreduraAtual(cfg.varredura); const e = v && v.efeito[id]; return !!(e && e[estado.nivel][1]); };

function escala(m) {
  const cfg = METRICAS[m];
  const vals = Object.keys(nivelAtual().valores).map(id => valorMetrica(id, m)).filter(v => v != null);
  if (cfg.tipo.startsWith("seq")) {
    const dom = cfg.dom || [0, d3.max(vals) || 1];
    const cores = [css("--seq-0"), css("--seq-1"), css("--seq-2")];
    return {s: d3.scaleSequential(d3.interpolateRgbBasis(cfg.tipo === "seq-inv" ? cores.slice().reverse() : cores)).domain(dom).clamp(true), dom, cfg};
  }
  let dom = cfg.dom;
  if (!dom) { const mx = d3.max(vals, v => Math.abs(v)) || 1; dom = [-mx, 0, mx]; }
  const cores = cfg.tipo === "div-inv" ? [css("--div-pos"), css("--div-mid"), css("--div-neg")] : [css("--div-neg"), css("--div-mid"), css("--div-pos")];
  return {s: d3.scaleDiverging(d3.interpolateRgbBasis(cores)).domain(dom).clamp(true), dom, cfg};
}

// ------------------------------------------------------------------ mapa
const mapa = L.map("mapa", {zoomControl: true, attributionControl: true, zoomSnap: 0.25});
let fundo = null;
const escuro = () => (matchMedia("(prefers-color-scheme: dark)").matches && document.documentElement.dataset.theme !== "light")
                     || document.documentElement.dataset.theme === "dark";
function fundoDoTema() {
  if (fundo) mapa.removeLayer(fundo);
  const servico = escuro() ? "Canvas/World_Dark_Gray_Base" : "Canvas/World_Light_Gray_Base";
  fundo = L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/${servico}/MapServer/tile/{z}/{y}/{x}`,
    {attribution: "Fundo © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors", maxZoom: 16}).addTo(mapa);
}
fundoDoTema();
const camada = L.layerGroup().addTo(mapa);
const todosPontos = Object.values(D.arestas).flatMap(a => a.coords);
const enquadrar = () => { mapa.invalidateSize(); mapa.fitBounds(L.latLngBounds(todosPontos), {padding: [16, 16]}); };
mapa.setView(L.latLngBounds(todosPontos).getCenter(), 14);
let mexeu = false;
for (const ev of ["mousedown", "wheel", "touchstart", "keydown"])
  document.getElementById("mapa").addEventListener(ev, () => { mexeu = true; }, {passive: true});
new ResizeObserver(() => { if (!mexeu) enquadrar(); else mapa.invalidateSize(); }).observe(document.getElementById("mapa"));

const largura = (f, maxF) => 1 + 3.5 * Math.sqrt(Math.max(f, 0) / maxF);

function tooltipAresta(id, situacao) {
  const a = D.arestas[id], val = nivelAtual().valores[id];
  const box = el("div");
  box.append(el("strong", {}, a.nome || "(sem nome)"),
    el("div", {style: "color:var(--text-secondary)"}, `${id} · ${a.classe} · ${fmt(a.L, 0)} m${a.gargalo ? " · gargalo calibrado" : ""}`));
  if (situacao) box.append(el("div", {style: "color:var(--destaque);font-weight:600"}, "Neste cenário: " + situacao));
  if (!val) {
    if (desconecta(id)) box.append(el("div", {}, "Fechar esta aresta desconecta pares origem-destino"));
    else { const v = valorMetrica(id, estado.metrica); if (v != null) box.append(el("div", {}, `${METRICAS[estado.metrica].rot}: ${METRICAS[estado.metrica].fmt(v)}`)); }
    return box;
  }
  const linhas = [["Fluxo", `${fmt(val[I.fluxo], 0)} veíc/h`], ["Capacidade", `${fmt(val[I.cap], 0)} veíc/h (${val[I.faixas]} faixa${val[I.faixas] > 1 ? "s" : ""})`],
    ["V/C", fmt(val[I.vc], 2)], ["Velocidade modelada", `${fmt(val[I.vel], 1)} km/h (limite ${fmt(a.lim, 0)})`],
    ["K modelado", fmt(val[I.k], 2)], ["K observado", fmt(a.k_obs, 2)]];
  const m = estado.metrica;
  if (!["vc", "k", "fluxo", "k_obs"].includes(m)) {
    linhas.push([METRICAS[m].rot, desconecta(id) ? "fechar desconecta pares OD" : METRICAS[m].fmt(valorMetrica(id, m))]);
  }
  for (const [k, v] of linhas) box.append(el("div", {}, el("span", {style: "color:var(--text-secondary)"}, k + ": "), v));
  return box;
}

function desenharMapa() {
  camada.clearLayers();
  const {s} = escala(estado.metrica);
  const vals = nivelAtual().valores;
  const maxF = d3.max(Object.values(vals), v => v[I.fluxo]) || 1;
  const alt = alteracoes();
  const b = baseAtual();
  if (b) for (const id of Object.keys(b.niveis[estado.nivel].valores)) if (!vals[id]) {
    L.polyline(D.arestas[id].coords, {color: css("--removida"), weight: 2, dashArray: "5 5", opacity: .9})
      .bindTooltip(() => tooltipAresta(id, alt[id] || "removida"), {sticky: true}).addTo(camada);
  }
  const ordem = Object.keys(vals).sort((x, y) => vals[x][I.fluxo] - vals[y][I.fluxo]);
  for (const id of ordem) {
    const a = D.arestas[id], w = largura(vals[id][I.fluxo], maxF);
    L.polyline(a.coords, {color: css("--muted"), weight: w + 1.5, opacity: .35, lineCap: "round", interactive: false}).addTo(camada);
    if (alt[id]) L.polyline(a.coords, {color: css("--destaque"), weight: w + 7, opacity: .45, lineCap: "round"}).addTo(camada);
    if (estado.gargalo && a.gargalo) L.polyline(a.coords, {color: css("--text-primary"), weight: w + 2.5, opacity: .35}).addTo(camada);
    const v = valorMetrica(id, estado.metrica), corte = desconecta(id);
    L.polyline(a.coords, {color: corte ? css("--muted") : v == null ? css("--muted") : s(v), weight: w,
      opacity: .95, lineCap: "round", dashArray: corte ? "4 4" : null})
      .bindTooltip(() => tooltipAresta(id, alt[id]), {sticky: true}).addTo(camada);
  }
  legenda.atualizar(maxF);
}

const legenda = L.control({position: "bottomright"});
legenda.onAdd = () => { const d = L.DomUtil.create("div", "leg"); L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d); legenda.div = d; return d; };
legenda.atualizar = maxF => {
  const d = legenda.div; d.replaceChildren();
  const {s, dom, cfg} = escala(estado.metrica);
  const botao = el("button", {type: "button", "aria-expanded": String(estado.legendaAberta)}, (estado.legendaAberta ? "▾ " : "▸ ") + "Legenda — " + cfg.rot);
  botao.onclick = () => { estado.legendaAberta = !estado.legendaAberta; legenda.atualizar(maxF); };
  d.append(botao);
  if (!estado.legendaAberta) return;
  const corpo = el("div", {class: "corpo"});
  corpo.append(el("p", {class: "desc"}, cfg.desc));
  const w = 222, svg = d3.create("svg").attr("width", w + 12).attr("height", 30);
  const gid = "g" + Math.random().toString(36).slice(2);
  const grad = svg.append("defs").append("linearGradient").attr("id", gid);
  d3.range(0, 1.0001, 0.1).forEach(t => grad.append("stop").attr("offset", t).attr("stop-color", s(dom[0] + t * (dom[dom.length - 1] - dom[0]))));
  svg.append("rect").attr("x", 6).attr("y", 2).attr("width", w).attr("height", 10).attr("rx", 2).attr("fill", `url(#${gid})`);
  const x = d3.scaleLinear().domain([dom[0], dom[dom.length - 1]]).range([6, 6 + w]);
  x.ticks(4).forEach(t => svg.append("text").attr("x", x(t)).attr("y", 26).attr("text-anchor", "middle").text((cfg.cen || cfg.varredura) && t > 0 ? "+" + fmt(t, cfg.tick) : fmt(t, cfg.tick)));
  corpo.append(svg.node(), el("div", {class: "extremos"}, el("span", {}, cfg.ext[0]), el("span", {}, cfg.ext[1])));
  const sec = el("div", {class: "sec"}, el("div", {style: "font-weight:600"}, "Espessura = fluxo (veíc/h)"));
  const amostras = [0.1, 0.4, 1].map(f => Math.round(maxF * f / 50) * 50 || Math.round(maxF * f));
  for (const f of amostras) { const lw = largura(f, maxF);
    sec.append(el("div", {class: "sim"}, linhaSvg({cor: css("--seq-1"), w: lw}), `${fmt(f, 0)} veíc/h`)); }
  corpo.append(sec);
  const simb = el("div", {class: "sec"}, el("div", {style: "font-weight:600"}, "Símbolos"));
  if (estado.gargalo) simb.append(el("div", {class: "sim"}, linhaSvg({cor: css("--seq-1"), w: 3, contorno: css("--text-primary")}), "gargalo com capacidade efetiva (calibrada pelo tempo observado)"));
  if (rodadaAtual().cenario) {
    simb.append(el("div", {class: "sim"}, linhaSvg({cor: css("--seq-1"), w: 3, halo: css("--destaque")}), "aresta alterada neste cenário"));
    simb.append(el("div", {class: "sim"}, linhaSvg({cor: css("--removida"), w: 2, tracejado: true}), "aresta que existe na situação atual e saiu neste cenário"));
  }
  if (cfg.varredura) simb.append(el("div", {class: "sim"}, linhaSvg({cor: css("--muted"), w: 2, tracejado: true}), "fechar a aresta desconecta pares origem-destino (não avaliado)"));
  simb.append(el("div", {class: "sim"}, linhaSvg({cor: css("--muted"), w: 3}), "sem valor para esta métrica"));
  corpo.append(simb);
  d.append(corpo);
};
legenda.addTo(mapa);
function linhaSvg({cor, w, contorno, halo, tracejado}) {
  const s = d3.create("svg").attr("width", 34).attr("height", 14);
  if (halo) s.append("line").attr("x1", 3).attr("x2", 31).attr("y1", 7).attr("y2", 7).attr("stroke", halo).attr("stroke-width", w + 7).attr("stroke-opacity", .45).attr("stroke-linecap", "round");
  if (contorno) s.append("line").attr("x1", 3).attr("x2", 31).attr("y1", 7).attr("y2", 7).attr("stroke", contorno).attr("stroke-width", w + 2.5).attr("stroke-opacity", .35);
  s.append("line").attr("x1", 3).attr("x2", 31).attr("y1", 7).attr("y2", 7).attr("stroke", cor).attr("stroke-width", w)
    .attr("stroke-linecap", "round").attr("stroke-dasharray", tracejado ? "4 4" : null);
  return s.node();
}

// ------------------------------------------------------------------ ficha do cenario e indicadores
function ficha() {
  const box = document.getElementById("ficha"), r = rodadaAtual(), c = r.cenario;
  box.hidden = !c; box.replaceChildren(); if (!c) return;
  box.append(el("h2", {style: "margin-bottom:4px"}, `${c.codigo || ""} ${c.codigo ? "· " : ""}${c.descricao}`));
  const linha = el("div", {class: "linha-ficha"});
  linha.append(el("span", {class: "chip"}, FAMILIAS[c.familia] || "cenário"));
  if (r.classificacao) linha.append(el("span", {class: "chip"}, r.classificacao.rotulo));
  if (r.classificacao && r.classificacao.divergencia_k_tstt.length) linha.append(el("span", {class: "chip"}, "K × TSTT divergem: demanda " + r.classificacao.divergencia_k_tstt.join(", ")));
  if (r.sufixo) linha.append(el("span", {class: "chip"}, `sensibilidade: a = ${fmt(r.bpr.alpha, 2)}, b = ${fmt(r.bpr.beta, 1)}`));
  box.append(linha);
  if (c.criterio) box.append(el("p", {class: "nota"}, "Por que estas arestas: " + c.criterio));
  for (const a of c.alteracoes) box.append(el("p", {class: "nota", style: "margin-top:4px"},
    `${a.tipo === "faixa" ? `+${a.faixas || 1} faixa` : ALT[a.tipo] || a.tipo}: ` + a.arestas.map(e => e.replace("->", "→")).join(", ")));
}

function tiles() {
  const box = document.getElementById("tiles"); box.replaceChildren();
  const ind = nivelAtual().indicadores;
  const b = baseAtual(), ib = b ? b.niveis[estado.nivel].indicadores : null;
  const itens = [
    ["TSTT (tempo total no sistema)", `${fmt(ind.tstt_veic_h, 1)} veíc·h`, "tstt_veic_min", true],
    ["K da rede (ponderado por veíc·km)", fmt(ind.k_rede, 3), "k_rede", false],
    ["Velocidade média da rede", `${fmt(ind.velocidade_media_rede_kmh, 1)} km/h`, "velocidade_media_rede_kmh", false],
    ["Tempo médio de viagem", `${fmt(ind.tempo_medio_viagem_min, 2)} min`, "tempo_medio_viagem_min", true],
    ["Arestas com V/C > 1", fmt(ind.arestas_vc_acima_1), "arestas_vc_acima_1", true],
    ["Demanda", `${fmt(ind.demanda_veic_h, 0)} veíc/h`, null, null],
  ];
  for (const [rot, val, chave, menorMelhor] of itens) {
    const det = el("div", {class: "det"});
    if (ib && chave) {
      const d = ind[chave] - ib[chave], pct = ib[chave] ? 100 * d / ib[chave] : 0;
      if (Math.abs(d) < 1e-9) det.append("igual à situação atual");
      else { const bom = menorMelhor ? d < 0 : d > 0;
        det.append(el("span", {class: bom ? "melhor" : "pior"}, `${d < 0 ? "▼" : "▲"} ${fmt(Math.abs(pct), 2)}% (${bom ? "melhor" : "pior"})`), " vs situação atual"); }
    } else if (chave === null) det.append(`fator de expansão ${fmt(nivelAtual().fator, 2)}`);
    box.append(el("div", {class: "cartao tile"}, el("div", {class: "rot"}, rot), el("div", {class: "val"}, val), det));
  }
  box.append(el("div", {class: "cartao tile"}, el("div", {class: "rot"}, "Iterações do Frank-Wolfe"), el("div", {class: "val"}, fmt(ind.iteracoes)),
    el("div", {class: "det"}, `gap ${fmtGap(ind.gap_relativo)} · ${ind.convergiu ? "convergiu" : "NÃO convergiu"}`)));
}

// ------------------------------------------------------------------ tooltip comum
const tip = document.getElementById("tip");
function mostrarTip(ev, nodes) { tip.replaceChildren(...nodes); tip.style.display = "block";
  const r = tip.getBoundingClientRect(); let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14; if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
  tip.style.left = x + "px"; tip.style.top = y + "px"; }
const esconderTip = () => { tip.style.display = "none"; };
function legendaNiveis(box, extra) {
  const lg = el("div", {class: "legenda-fora"});
  for (const n of NIVEIS) lg.append(el("span", {}, el("span", {style: `display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-2px;margin-right:6px;background:${css(`--ord-${n}`)}`}),
    `demanda ${n} (fator ${fmt(rodadaAtual().niveis[n].fator, 2)})`));
  if (extra) lg.append(extra);
  box.append(lg);
}
const cenariosDoConjunto = () => Object.entries(D.rodadas).filter(([, r]) => r.cenario && r.sufixo === rodadaAtual().sufixo);

// ------------------------------------------------------------------ delta TSTT por cenario
function graficoDelta() {
  const box = document.getElementById("g-delta"); box.replaceChildren();
  const cens = cenariosDoConjunto();
  document.getElementById("t-delta").textContent = "Variação do TSTT por cenário" + (rodadaAtual().sufixo ? " (a = 0,8; b = 4,7)" : "");
  if (!cens.length) { box.append(el("p", {class: "nota"}, "Nenhum cenário rodado para estes parâmetros.")); return; }
  const linhas = cens.flatMap(([nome, r]) => NIVEIS.map(n => ({nome, r, n, v: r.niveis[n].comparacao.delta_tstt_pct})));
  const W = 560, bandaH = 9, gap = 2, grupo = NIVEIS.length * (bandaH + gap) + 10, m = {t: 6, r: 56, b: 28, l: 190};
  const H = m.t + m.b + cens.length * grupo;
  const ext = d3.max(linhas, d => Math.abs(d.v)) || 1;
  const x = d3.scaleLinear().domain([-ext, ext]).nice().range([m.l, W - m.r]);
  const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", "Variação percentual do TSTT por cenário e nível de demanda");
  x.ticks(6).forEach(t => { svg.append("line").attr("x1", x(t)).attr("x2", x(t)).attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--grid"));
    svg.append("text").attr("x", x(t)).attr("y", H - m.b + 15).attr("text-anchor", "middle").text(`${sinal(t, 0)}%`); });
  svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--axis"));
  cens.forEach(([nome, r], i) => {
    const y0 = m.t + i * grupo, atual = nome === estado.rodada;
    const rot = nomeCurto(r);
    svg.append("text").attr("x", m.l - 8).attr("y", y0 + grupo / 2).attr("text-anchor", "end").attr("class", "rotulo")
      .style("font-weight", atual ? 700 : 400).text(rot.length > 30 ? rot.slice(0, 29) + "…" : rot)
      .style("cursor", "pointer").on("click", () => trocarRodada(nome));
    NIVEIS.forEach((n, j) => { const d = linhas.find(l => l.nome === nome && l.n === n), yy = y0 + 5 + j * (bandaH + gap);
      const x1 = Math.min(x(0), x(d.v)), w = Math.max(1, Math.abs(x(d.v) - x(0)));
      svg.append("rect").attr("x", x1).attr("y", yy).attr("width", w).attr("height", bandaH).attr("rx", 2).attr("fill", css(`--ord-${n}`))
        .on("pointermove", ev => mostrarTip(ev, [el("strong", {}, `${sinal(d.v, 2)}%`), el("div", {}, `${rot} · demanda ${n}`)])).on("pointerleave", esconderTip);
      if (j === 1) svg.append("text").attr("x", d.v < 0 ? x1 - 4 : x1 + w + 4).attr("y", yy + bandaH - 1).attr("text-anchor", d.v < 0 ? "end" : "start").text(`${sinal(d.v, 1)}%`);
    });
  });
  legendaNiveis(box);
  box.append(el("p", {class: "nota"}, "Negativo = o sistema inteiro gasta menos tempo que na situação atual. O rótulo numérico é o da demanda adotada; os outros níveis estão no tooltip e na tabela. Clique no nome para abrir o cenário."));
}

// ------------------------------------------------------------------ K x TSTT
function graficoKT() {
  const box = document.getElementById("g-kt"); box.replaceChildren();
  const cens = cenariosDoConjunto();
  if (!cens.length) return;
  const pts = cens.flatMap(([nome, r]) => NIVEIS.map(n => ({nome, r, n, x: r.niveis[n].comparacao.delta_tstt_pct, y: r.niveis[n].comparacao.delta_k_rede})));
  const W = 520, H = 330, m = {t: 14, r: 16, b: 38, l: 58};
  const ex = d3.max(pts, p => Math.abs(p.x)) || 1, ey = d3.max(pts, p => Math.abs(p.y)) || 0.01;
  const x = d3.scaleLinear().domain([-ex, ex]).nice().range([m.l, W - m.r]);
  const y = d3.scaleLinear().domain([-ey, ey]).nice().range([H - m.b, m.t]);
  const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", "Variação do K da rede contra variação do TSTT, por cenário e nível de demanda");
  svg.append("rect").attr("x", x(0)).attr("y", m.t).attr("width", W - m.r - x(0)).attr("height", y(0) - m.t).attr("fill", css("--wash"));
  svg.append("text").attr("x", W - m.r - 4).attr("y", m.t + 12).attr("text-anchor", "end").attr("class", "rotulo").text("K melhora, TSTT piora");
  svg.append("text").attr("x", W - m.r - 4).attr("y", m.t + 26).attr("text-anchor", "end").text("(divergência: critério de Braess do artigo)");
  x.ticks(6).forEach(t => { svg.append("line").attr("x1", x(t)).attr("x2", x(t)).attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--grid"));
    svg.append("text").attr("x", x(t)).attr("y", H - m.b + 14).attr("text-anchor", "middle").text(`${sinal(t, 0)}%`); });
  y.ticks(6).forEach(t => { svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(t)).attr("y2", y(t)).attr("stroke", css("--grid"));
    svg.append("text").attr("x", m.l - 6).attr("y", y(t) + 4).attr("text-anchor", "end").text(sinal(t, 3)); });
  svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--axis"));
  svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(0)).attr("y2", y(0)).attr("stroke", css("--axis"));
  svg.append("text").attr("x", (m.l + W - m.r) / 2).attr("y", H - 4).attr("text-anchor", "middle").text("Δ TSTT (%)  →  piora");
  svg.append("text").attr("transform", `translate(12,${(m.t + H - m.b) / 2}) rotate(-90)`).attr("text-anchor", "middle").text("Δ K da rede  →  melhora");
  const rotulados = new Set();
  for (const p of pts) {
    const g = svg.append("g").style("cursor", "pointer").on("click", () => trocarRodada(p.nome));
    g.append("circle").attr("cx", x(p.x)).attr("cy", y(p.y)).attr("r", 12).attr("fill", "transparent")
      .on("pointermove", ev => mostrarTip(ev, [el("strong", {}, `TSTT ${sinal(p.x, 2)}% · K ${sinal(p.y, 4)}`), el("div", {}, `${nomeCurto(p.r)} · demanda ${p.n}`)]))
      .on("pointerleave", esconderTip);
    g.append("circle").attr("cx", x(p.x)).attr("cy", y(p.y)).attr("r", p.nome === estado.rodada ? 6 : 4.5).attr("fill", css(`--ord-${p.n}`))
      .attr("stroke", css("--surface-1")).attr("stroke-width", 2).style("pointer-events", "none");
    const diverge = (p.x > 0.05 && p.y > 1e-4) || (p.x < -0.05 && p.y < -1e-4);
    const cod = p.r.cenario.codigo || "";
    if ((diverge || Math.abs(p.x) > ex * 0.6) && p.n === "adotada" && !rotulados.has(cod)) {
      rotulados.add(cod);
      svg.append("text").attr("x", x(p.x) + 8).attr("y", y(p.y) - 6).attr("class", "rotulo").text(cod);
    }
  }
  legendaNiveis(box);
  box.append(el("p", {class: "nota"}, "Cada ponto é um cenário num nível de demanda. Nos quadrantes de concordância, K e TSTT melhoram ou pioram juntos; no quadrante destacado, o K da rede sobe enquanto o sistema perde tempo."));
}

// ------------------------------------------------------------------ varreduras
function varreduras() {
  const box = document.getElementById("varreduras"); box.replaceChildren();
  for (const [modo, titulo] of [["remocao", "Fechar cada aresta"], ["faixa", "+1 faixa em cada aresta"]]) {
    const v = varreduraAtual(modo), card = el("div", {class: "grafico"});
    card.append(el("h3", {}, titulo + (rodadaAtual().sufixo ? " (a = 0,8; b = 4,7)" : "")));
    if (!v) { card.append(el("p", {class: "nota"}, "Varredura não rodada para estes parâmetros.")); box.append(card); continue; }
    const r = v.resumo, conf = r.casos_braess_confirmados;
    card.append(el("p", {class: "nota", style: "margin-top:0"},
      `${r.alteracoes_avaliadas} de ${r.arestas_testadas} arestas avaliadas` + (r.alteracoes_que_desconectam_pares_od ? ` (${r.alteracoes_que_desconectam_pares_od} desconectariam pares OD)` : "") +
      `. Critério: ${r.criterio_braess}. Candidatos com gap 10⁻⁴: ${r.candidatos_gap_1e_4 ?? r["candidatos_gap_1e-4"]}. `,
      el("strong", {}, conf.length ? `Braess confirmado em ${conf.length} caso(s).` : "Nenhum caso de Braess.")));
    const linhas = Object.entries(v.efeito).map(([id, e]) => ({id, v: e[estado.nivel][0]})).filter(d => d.v != null);
    const top = linhas.sort((a, b) => Math.abs(b.v) - Math.abs(a.v)).slice(0, 10);
    const W = 520, bh = 16, m = {t: 4, r: 64, b: 24, l: 150}, H = m.t + m.b + top.length * (bh + 4);
    const mx = d3.max(top, d => Math.abs(d.v)) || 1;
    const x = d3.scaleLinear().domain(modo === "remocao" ? [0, mx] : [-mx, 0]).nice().range([m.l, W - m.r]);
    const svg = d3.select(card).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", `As 10 arestas de maior efeito: ${titulo}`);
    x.ticks(5).forEach(t => { svg.append("line").attr("x1", x(t)).attr("x2", x(t)).attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--grid"));
      svg.append("text").attr("x", x(t)).attr("y", H - m.b + 14).attr("text-anchor", "middle").text(`${sinal(t, 0)}%`); });
    top.forEach((d, i) => { const a = D.arestas[d.id], yy = m.t + i * (bh + 4);
      const rot = `${d.id.replace("->", "→")} ${a.nome ? a.nome.replace("Estrada Parque Contorno", "EPCT") : a.classe}`;
      svg.append("text").attr("x", m.l - 6).attr("y", yy + bh - 4).attr("text-anchor", "end").attr("class", "rotulo").text(rot.length > 24 ? rot.slice(0, 23) + "…" : rot);
      const x0 = x(0), x1 = x(d.v);
      svg.append("rect").attr("x", Math.min(x0, x1)).attr("y", yy).attr("width", Math.max(1, Math.abs(x1 - x0))).attr("height", bh).attr("rx", 2)
        .attr("fill", css(d.v > 0 ? "--div-pos" : "--div-neg"))
        .on("pointermove", ev => mostrarTip(ev, [el("strong", {}, `${sinal(d.v, 2)}% no TSTT`), el("div", {}, `${modo === "remocao" ? "fechar" : "+1 faixa em"} ${d.id} (${a.nome || a.classe}) · demanda ${estado.nivel}`)]))
        .on("pointerleave", esconderTip);
      svg.append("text").attr("x", d.v > 0 ? Math.max(x0, x1) + 4 : Math.min(x0, x1) - 4).attr("y", yy + bh - 4).attr("text-anchor", d.v > 0 ? "start" : "end").text(`${sinal(d.v, 1)}%`);
    });
    card.append(el("p", {class: "nota"}, modo === "remocao"
      ? `As 10 arestas cujo fechamento mais aumenta o TSTT (demanda ${estado.nivel}): as mais importantes para o sistema.`
      : `As 10 arestas em que uma faixa a mais mais reduz o TSTT (demanda ${estado.nivel}).`));
    const b = el("button", {type: "button", style: "margin-top:6px"}, "Ver no mapa");
    b.onclick = () => { trocarRodada(rodadaAtual().sufixo ? "base" + rodadaAtual().sufixo : "base", modo === "remocao" ? "efeito_remocao" : "efeito_faixa");
      document.getElementById("t-mapa").scrollIntoView({behavior: "smooth"}); };
    card.append(b);
    box.append(card);
  }
}

// ------------------------------------------------------------------ convergencia
function graficoConvergencia() {
  const box = document.getElementById("g-conv"); box.replaceChildren();
  const r = rodadaAtual(), W = 520, H = 250, m = {t: 12, r: 70, b: 34, l: 52};
  const series = NIVEIS.map(n => ({n, pts: r.niveis[n].convergencia.filter(p => p[1] > 0)}));
  const maxIt = d3.max(series, s => d3.max(s.pts, p => p[0])) || 1;
  const x = d3.scaleLinear().domain([1, Math.max(2, maxIt)]).range([m.l, W - m.r]);
  const ys = series.flatMap(s => s.pts.map(p => p[1]));
  const y = d3.scaleLog().domain([Math.min(1e-5, d3.min(ys) || 1e-5), Math.max(1, d3.max(ys) || 1)]).range([H - m.b, m.t]).nice();
  const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", "Gap relativo por iteração nos três níveis de demanda");
  y.ticks(6).filter(t => Number.isInteger(Math.log10(t))).forEach(t => {
    svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(t)).attr("y2", y(t)).attr("stroke", css("--grid"));
    svg.append("text").attr("x", m.l - 6).attr("y", y(t) + 4).attr("text-anchor", "end").text(`10${sup(Math.log10(t))}`); });
  x.ticks(6).filter(Number.isInteger).forEach(t => svg.append("text").attr("x", x(t)).attr("y", H - m.b + 16).attr("text-anchor", "middle").text(t));
  svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", H - m.b).attr("y2", H - m.b).attr("stroke", css("--axis"));
  svg.append("text").attr("x", (m.l + W - m.r) / 2).attr("y", H - 2).attr("text-anchor", "middle").text("iteração");
  svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(1e-4)).attr("y2", y(1e-4)).attr("stroke", css("--muted")).attr("stroke-dasharray", "4 4");
  svg.append("text").attr("x", W - m.r + 4).attr("y", y(1e-4) + 4).attr("class", "rotulo").text("critério");
  const linha = d3.line().x(p => x(p[0])).y(p => y(p[1]));
  for (const s of series) {
    const cor = css(`--ord-${s.n}`);
    svg.append("path").attr("d", linha(s.pts)).attr("fill", "none").attr("stroke", cor).attr("stroke-width", 2);
    svg.selectAll(null).data(s.pts).join("circle").attr("cx", p => x(p[0])).attr("cy", p => y(p[1])).attr("r", 3).attr("fill", cor);
    const ult = s.pts[s.pts.length - 1];
    if (ult) svg.append("text").attr("x", x(ult[0]) + 6).attr("y", y(ult[1]) + 4).attr("class", "rotulo").text(s.n);
  }
  const cruz = svg.append("line").attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--axis")).style("display", "none");
  svg.append("rect").attr("x", m.l).attr("y", m.t).attr("width", W - m.r - m.l).attr("height", H - m.b - m.t).attr("fill", "transparent")
    .on("pointermove", ev => { const [px] = d3.pointer(ev); const it = Math.max(1, Math.min(maxIt, Math.round(x.invert(px))));
      cruz.attr("x1", x(it)).attr("x2", x(it)).style("display", null);
      const nodes = [el("div", {}, `iteração ${it}`)];
      for (const s of series) { const p = s.pts.find(q => q[0] === it);
        nodes.push(el("div", {class: "linha"}, el("span", {class: "chave", style: `background:${css(`--ord-${s.n}`)}`}),
          el("strong", {}, p ? p[1].toExponential(2).replace(".", ",") : "convergiu antes"), ` demanda ${s.n}`)); }
      mostrarTip(ev, nodes); })
    .on("pointerleave", () => { cruz.style("display", "none"); esconderTip(); });
  legendaNiveis(box);
}
const sup = n => String(n).replace("-", "⁻").replace(/\d/g, d => "⁰¹²³⁴⁵⁶⁷⁸⁹"[d]);

// ------------------------------------------------------------------ tabelas
function tabelaRodadas() {
  const t = document.getElementById("tab-rodadas"); t.replaceChildren();
  const cab = ["Rodada", "Demanda", "TSTT (veíc·h)", "Δ TSTT", "K da rede", "Δ K", "Vel. média (km/h)", "V/C > 1", "Iter.", "Classificação"];
  t.append(el("thead", {}, el("tr", {}, ...cab.map((c, i) => el("th", {class: i < 2 || i === 9 ? "txt" : ""}, c)))));
  const tb = el("tbody");
  for (const [nome, r] of Object.entries(D.rodadas)) for (const n of NIVEIS) {
    const ind = r.niveis[n].indicadores, c = r.niveis[n].comparacao, cl = r.classificacao;
    let clas = "—";
    if (cl && n === "baixa") clas = cl.rotulo + (cl.divergencia_k_tstt.length ? ` · K × TSTT divergem (${cl.divergencia_k_tstt.join(", ")})` : "");
    const celulas = [nomeCurto(r), n, fmt(ind.tstt_veic_h, 1), c ? `${sinal(c.delta_tstt_pct, 2)}%` : "—", fmt(ind.k_rede, 3),
      c ? sinal(c.delta_k_rede, 4) : "—", fmt(ind.velocidade_media_rede_kmh, 1), fmt(ind.arestas_vc_acima_1), fmt(ind.iteracoes), clas];
    const tr = el("tr", {class: nome === estado.rodada ? "atual" : ""}, ...celulas.map((v, i) => el("td", {class: i < 2 || i === 9 ? "txt" : ""}, v)));
    tr.style.cursor = "pointer"; tr.onclick = () => trocarRodada(nome);
    tb.append(tr);
  }
  t.append(tb);
}

function tabelaConferencia() {
  const t = document.getElementById("tab-conf"), card = document.getElementById("c-conf"); t.replaceChildren();
  const r = rodadaAtual(), b = r.cenario ? D.rodadas[r.base] : r;
  const c = b && b.niveis.adotada.conferencias; if (!c) { card.style.display = "none"; return; } card.style.display = "";
  const p = c.fluxo_x_passagens_tomtom, tm = c.tempo_x_observado;
  const linhas = [
    ["Fluxo × passagens TomTom", "escolha de rota", `${p.arestas} arestas`, `correlação ${fmt(p.correlacao, 2)}; GEH mediano ${fmt(p.geh_mediano, 1)}; ${fmt(100 * p.fracao_geh_abaixo_5, 0)}% com GEH < 5`],
    ["Tempo × observado, não calibradas", "VDF e t0", `${tm.nao_calibradas.arestas} arestas`, `modelo/obs. ${fmt(tm.nao_calibradas.razao_mediana_modelo_obs, 2)} (mediana); ${fmt(100 * tm.nao_calibradas.fracao_dentro_10pct, 0)}% em ±10%`],
    ["Tempo total ponderado pelo fluxo", "aderência global", "", `modelo/obs. ${fmt(tm.tempo_total_modelo_sobre_obs, 3)}`],
  ];
  for (const d of c.fluxo_x_detran.pistas) linhas.push([`DER-DF ${d.trecho} ${d.sentido}`, "nada (calibra o fator)", `${fmt(d.detran_veic_h)} contados`, `modelo ${fmt(d.modelo_veic_h)}; esperado pelo fator único ${fmt(d.esperado_pelo_fator_veic_h)}`]);
  t.append(el("thead", {}, el("tr", {}, ...["Comparação", "O que testa", "Base", "Resultado"].map(h => el("th", {class: "txt"}, h)))));
  const tb = el("tbody"); for (const l of linhas) tb.append(el("tr", {}, ...l.map(v => el("td", {class: "txt"}, v)))); t.append(tb);
}

function tabelaArestas() {
  const t = document.getElementById("tab-arestas"); t.replaceChildren();
  const m = estado.metrica, cfg = METRICAS[m], vals = nivelAtual().valores, alt = alteracoes();
  const cols = [["Aresta", r => r.id, true], ["Nome", r => r.a.nome, true], ["Classe", r => r.a.classe, true],
    ["Fluxo (veíc/h)", r => r.v[I.fluxo], false, 0], ["Capacidade", r => r.v[I.cap], false, 0], ["V/C", r => r.v[I.vc], false, 2],
    ["Vel. (km/h)", r => r.v[I.vel], false, 1], ["K modelado", r => r.v[I.k], false, 2], ["K obs.", r => r.a.k_obs, false, 2]];
  if (!["vc", "k", "fluxo", "k_obs"].includes(m)) cols.push([cfg.rot, r => valorMetrica(r.id, m), false, null]);
  if (Object.keys(alt).length) cols.push(["Neste cenário", r => alt[r.id] || "", true]);
  let linhas = Object.keys(vals).map(id => ({id, a: D.arestas[id], v: vals[id]}));
  const q = estado.busca.toLowerCase();
  if (q) linhas = linhas.filter(r => r.id.includes(q) || (r.a.nome || "").toLowerCase().includes(q));
  const padrao = cfg.cen || cfg.varredura || m === "razao_tempo" ? 9 : m === "k" ? 7 : m === "k_obs" ? 8 : m === "fluxo" ? 3 : 5;
  const [ci, dir] = estado.ordem || [padrao, m === "k" || m === "k_obs" ? 1 : -1];
  const absoluto = !estado.ordem && (cfg.cen || cfg.varredura);
  linhas.sort((x, y) => { let a = cols[ci][1](x), b = cols[ci][1](y);
    if (absoluto) { a = a == null ? null : Math.abs(a); b = b == null ? null : Math.abs(b); }
    if (a == null) return 1; if (b == null) return -1; return (a > b ? 1 : a < b ? -1 : 0) * dir; });
  t.append(el("thead", {}, el("tr", {}, ...cols.map(([c, , txt], i) => { const th = el("th", {class: txt ? "txt" : "", tabindex: "0"}, c + (i === ci ? (dir > 0 ? " ▲" : " ▼") : ""));
    const ordenar = () => { estado.ordem = [i, i === ci ? -dir : (txt ? 1 : -1)]; tabelaArestas(); };
    th.addEventListener("click", ordenar); th.addEventListener("keydown", e => { if (e.key === "Enter") ordenar(); }); return th; }))));
  const tb = el("tbody");
  for (const r of (estado.todas || q ? linhas : linhas.slice(0, 25))) tb.append(el("tr", {}, ...cols.map(([, f, txt, dec]) => {
    const v = f(r); const s = txt ? (v || "—") : v == null ? "—" : dec == null ? cfg.fmt(v) : fmt(v, dec);
    return el("td", {class: txt ? "txt" : ""}, s); })));
  t.append(tb);
  document.getElementById("b-todas").textContent = estado.todas ? "Mostrar só as 25 primeiras" : `Mostrar todas (${Object.keys(vals).length})`;
}

// ------------------------------------------------------------------ filtros
function montarFiltros() {
  const fr = document.getElementById("f-rodada");
  const grupos = new Map();
  for (const [nome, r] of Object.entries(D.rodadas)) {
    const g = (r.sufixo ? "Sensibilidade a = 0,8; b = 4,7 — " : "Parâmetros-base — ") + (r.cenario ? (FAMILIAS[r.cenario.familia] || "Cenários") : "situação atual");
    if (!grupos.has(g)) grupos.set(g, []); grupos.get(g).push([nome, r]);
  }
  for (const [g, itens] of grupos) { const og = el("optgroup", {label: g});
    for (const [nome, r] of itens) og.append(el("option", {value: nome}, nomeCurto(r))); fr.append(og); }
  fr.value = estado.rodada;
  fr.onchange = () => trocarRodada(fr.value);
  const fn = document.getElementById("f-nivel");
  for (const n of NIVEIS) { const b = el("button", {type: "button", "aria-pressed": String(n === estado.nivel)}, n);
    b.onclick = () => { estado.nivel = n; [...fn.children].forEach(c => c.setAttribute("aria-pressed", String(c === b))); tudo(); }; fn.append(b); }
  document.getElementById("f-gargalo").onchange = e => { estado.gargalo = e.target.checked; desenharMapa(); };
  document.getElementById("f-busca").oninput = e => { estado.busca = e.target.value; tabelaArestas(); };
  document.getElementById("b-todas").onclick = () => { estado.todas = !estado.todas; tabelaArestas(); };
}
function trocarRodada(nome, metrica) {
  const cenarioAntes = !!rodadaAtual().cenario;
  estado.rodada = nome; estado.ordem = null;
  document.getElementById("f-rodada").value = nome;
  if (metrica) estado.metrica = metrica;
  else if (!cenarioAntes && rodadaAtual().cenario && ["vc", "fluxo"].includes(estado.metrica)) estado.metrica = "delta_fluxo";
  tudo();
}
function opcoesMetrica() {
  const fm = document.getElementById("f-metrica"); fm.replaceChildren();
  const cen = !!rodadaAtual().cenario;
  for (const [k, c] of Object.entries(METRICAS)) {
    if (c.cen && !cen) continue;
    if (c.varredura && (cen || !varreduraAtual(c.varredura))) continue;
    fm.append(el("option", {value: k}, c.rot));
  }
  if (!fm.querySelector(`option[value="${estado.metrica}"]`)) estado.metrica = cen ? "delta_fluxo" : "vc";
  fm.value = estado.metrica;
  fm.onchange = () => { estado.metrica = fm.value; estado.ordem = null; desenharMapa(); tabelaArestas(); };
}
function tudo() {
  const r = rodadaAtual();
  opcoesMetrica();
  document.getElementById("sub").textContent = `Equilíbrio do usuário (Frank-Wolfe) · BPR a = ${fmt(r.bpr.alpha, 2)}, b = ${fmt(r.bpr.beta, 1)} · pico 18–19h de dia útil, julho/2026`;
  document.getElementById("t-mapa").textContent = `Mapa — ${nomeCurto(r)} · demanda ${estado.nivel}`;
  ficha(); tiles(); desenharMapa(); graficoDelta(); graficoKT(); varreduras(); graficoConvergencia(); tabelaRodadas(); tabelaConferencia(); tabelaArestas();
}
document.getElementById("rodape").textContent = "Gerado por scripts/visualizar_resultados.py a partir de resultados/. Cenários: cenarios/*.json (scripts/gerar_cenarios.py). Unidades: fluxo e capacidade em veículos por hora por sentido; tempos em minutos; TSTT em veículo·hora no pico. Relatório: research/relatorio_cenarios.md.";
montarFiltros(); tudo();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { fundoDoTema(); tudo(); });
</script>
</body>
</html>
"""


def gerar_painel(G: nx.DiGraph, rodadas: dict, varreduras: dict) -> Path:
    dados = json.dumps(dados_painel(G, rodadas, varreduras), ensure_ascii=False, separators=(",", ":"))
    dados = dados.replace("</", "<\\/")
    destino = RESULTADOS / "painel.html"
    destino.write_text(PAINEL.replace("__DADOS__", dados), encoding="utf-8")
    return destino


# ---------------------------------------------------------------------------
# Figuras estaticas (artigo)
# ---------------------------------------------------------------------------
def _estilo(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(BASE_LINHA)
    ax.tick_params(colors=MUDO, labelsize=9)
    ax.grid(True, color=GRADE, linewidth=0.6)
    ax.set_axisbelow(True)


def _larguras(f, maxf):
    return 0.6 + 3 * np.sqrt(np.maximum(f, 0) / maxf)


def _mapa(ax, G, t: pd.DataFrame, valores: pd.Series, cmap, norm, gargalos: bool, titulo: str, rotulo: str, fig,
          destacar: set | None = None, tracejadas: list | None = None):
    geoms = geometrias(G)
    maxf = t["fluxo_veic_h"].max() or 1
    t = t.assign(_v=valores.values).sort_values("fluxo_veic_h")
    for u, v in tracejadas or []:
        g = np.asarray(geometria(geoms, u, v).coords)
        ax.plot(g[:, 0], g[:, 1], color=MUDO, linewidth=1, linestyle=(0, (3, 3)))
    if destacar:
        sel = t[t["aresta"].isin(destacar)]
        ax.add_collection(LineCollection([np.asarray(geometria(geoms, r.u, r.v).coords) for r in sel.itertuples()],
                                         colors=SERIE[1], linewidths=_larguras(sel["fluxo_veic_h"], maxf) + 5, alpha=0.45,
                                         capstyle="round"))
    if gargalos:
        sel = t[t["gargalo"]]
        ax.add_collection(LineCollection([np.asarray(geometria(geoms, r.u, r.v).coords) for r in sel.itertuples()],
                                         colors=TINTA, linewidths=_larguras(sel["fluxo_veic_h"], maxf) + 1.8, alpha=0.35))
    segs = [np.asarray(geometria(geoms, r.u, r.v).coords) for r in t.itertuples()]
    cores = [cmap(norm(v)) if pd.notna(v) else MUDO for v in t["_v"]]
    ax.add_collection(LineCollection(segs, colors=cores, linewidths=_larguras(t["fluxo_veic_h"], maxf), capstyle="round"))
    ax.autoscale()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(titulo, loc="left", fontsize=10, color=TINTA)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.01)
    cb.set_label(rotulo, color=TINTA_2, fontsize=9)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=MUDO, labelsize=8)


def _salvar(fig, nome: str, feitas: list) -> None:
    feitas.append(FIGURAS / nome)
    fig.savefig(feitas[-1], bbox_inches="tight")
    plt.close(fig)


def gerar_figuras(G: nx.DiGraph, rodadas: dict, varreduras: dict) -> list[Path]:
    FIGURAS.mkdir(parents=True, exist_ok=True)
    for antiga in FIGURAS.glob("*.png"):
        antiga.unlink()
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "text.color": TINTA,
                         "axes.labelcolor": TINTA_2, "figure.facecolor": "white"})
    seq = LinearSegmentedColormap.from_list("seq", AZUL_SEQ)
    div = LinearSegmentedColormap.from_list("div", DIVERGENTE)
    feitas = []
    for nome, r in sorted(rodadas.items(), key=lambda kv: ordem_cenario(kv[1])):
        t = r["tabelas"]["adotada"]
        base = base_de(rodadas, r)
        suf = sufixo_bpr(G, r["bpr"])
        if base is None:
            fig, ax = plt.subplots(figsize=(8, 8), dpi=160)
            _mapa(ax, G, t, t["vc"], seq, Normalize(0, 1.5), True,
                  f"{nome}: V/C no equilíbrio, demanda adotada (espessura = fluxo; contorno = gargalo calibrado)",
                  "volume ÷ capacidade", fig)
            _salvar(fig, f"mapa_vc_{nome}_adotada.png", feitas)
            fig, ax = plt.subplots(figsize=(8, 8), dpi=160)
            _mapa(ax, G, t, t["k_modelado"], seq.reversed(), Normalize(0, 1), False,
                  f"{nome}: K modelado, demanda adotada (mais escuro = mais lento)", "K = velocidade ÷ limite", fig)
            _salvar(fig, f"mapa_k_{nome}_adotada.png", feitas)
            if suf == "":
                ok = t[t["t_obs_min"].notna()].copy()
                calib = ok["gargalo"] | np.isclose(ok["v0_kmh"], ok["vmed_obs_kmh"], atol=0.05)
                fig, ax = plt.subplots(figsize=(5.5, 5), dpi=160)
                lim = max(ok["t_obs_min"].max(), ok["tempo_min"].max()) * 1.05
                ax.plot([0, lim], [0, lim], color=BASE_LINHA, linewidth=1)
                for (rot, msk), cor in zip([("não calibradas", ~calib), ("calibradas (gargalo ou t0 do pico)", calib)], SERIE):
                    ax.scatter(ok.loc[msk, "t_obs_min"], ok.loc[msk, "tempo_min"], s=18, color=cor, edgecolor="white",
                               linewidth=0.6, label=f"{rot} ({int(msk.sum())})")
                ax.set_xlim(0, lim); ax.set_ylim(0, lim)
                ax.set_xlabel("tempo observado no pico (min)"); ax.set_ylabel("tempo modelado (min)")
                ax.set_title(f"{nome}: tempo por aresta, modelado × observado", loc="left", fontsize=11)
                _estilo(ax); ax.legend(frameon=False, fontsize=9)
                _salvar(fig, f"tempo_modelado_x_observado_{nome}.png", feitas)
            fig, ax = plt.subplots(figsize=(6, 3.6), dpi=160)
            for n in NIVEIS:
                h = pd.DataFrame(r["niveis"][n]["convergencia"])
                h = h[h["gap"] > 0]
                ax.semilogy(h["iteracao"], h["gap"], color=ORDINAL_NIVEIS[n], linewidth=2, marker="o", markersize=3,
                            label=f"demanda {n} (fator {r['niveis'][n]['fator']:.2f})")
            ax.axhline(1e-4, color=MUDO, linewidth=1, linestyle=(0, (4, 4)))
            ax.set_xlabel("iteração"); ax.set_ylabel("gap relativo")
            ax.set_title(f"{nome}: convergência do Frank-Wolfe", loc="left", fontsize=11)
            _estilo(ax); ax.legend(frameon=False, fontsize=8)
            _salvar(fig, f"convergencia_{nome}.png", feitas)
        elif suf == "":
            tb = base["tabelas"]["adotada"].set_index("aresta")
            delta = t.set_index("aresta")["fluxo_veic_h"] - tb["fluxo_veic_h"].reindex(t["aresta"]).fillna(0).values
            ext = max(abs(delta).max(), 1)
            alteradas = {e for a in r["cenario"]["alteracoes"] for e in a["arestas"]}
            alteradas |= {"->".join(e.split("->")[::-1]) for a in r["cenario"]["alteracoes"] if a["tipo"] == "inverter" for e in a["arestas"]}
            saiu = [tuple(e.split("->")) for e in tb.index if e not in set(t["aresta"])]
            fig, ax = plt.subplots(figsize=(8, 8), dpi=160)
            _mapa(ax, G, t, delta.reset_index(drop=True), div, TwoSlopeNorm(0, -ext, ext), False,
                  f"{r['cenario'].get('codigo', '')} {nome}: Δ fluxo vs situação atual, demanda adotada\n"
                  f"(laranja = aresta alterada; tracejado = saiu do grafo)", "Δ fluxo (veíc/h)", fig,
                  destacar=alteradas, tracejadas=saiu)
            _salvar(fig, f"mapa_delta_fluxo_{nome}_adotada.png", feitas)

    for suf in sorted({sufixo_bpr(G, r["bpr"]) for r in rodadas.values()}):
        cens = sorted([r for r in rodadas.values() if r.get("cenario") and sufixo_bpr(G, r["bpr"]) == suf], key=ordem_cenario)
        if not cens:
            continue
        rotulos = [f"{r['cenario'].get('codigo', '')} {r['cenario']['descricao'][:44]}" for r in cens]
        fig, ax = plt.subplots(figsize=(8, 1.2 + 0.55 * len(cens)), dpi=160)
        altura = 0.26
        for i, r in enumerate(cens):
            for j, n in enumerate(NIVEIS):
                v = r["niveis"][n]["comparacao_com_base"]["delta_tstt_pct"]
                y = i + (j - 1) * (altura + 0.02)
                ax.barh(y, v, height=altura, color=ORDINAL_NIVEIS[n], label=f"demanda {n}" if i == 0 else None)
            v = r["niveis"]["adotada"]["comparacao_com_base"]["delta_tstt_pct"]
            ax.text(v + (0.15 if v >= 0 else -0.15), i, f"{v:+.2f}%", va="center", ha="left" if v >= 0 else "right",
                    fontsize=7, color=TINTA_2)
        ax.axvline(0, color=BASE_LINHA, linewidth=1)
        ax.set_yticks(range(len(cens)), rotulos, fontsize=7)
        ax.invert_yaxis()
        ax.set_xlabel("Δ TSTT em relação à situação atual (%)")
        ax.set_title("Variação do tempo total no sistema por cenário" + (" (a = 0,8; b = 4,7)" if suf else ""), loc="left", fontsize=11)
        _estilo(ax); ax.grid(axis="y", visible=False); ax.legend(frameon=False, fontsize=8, loc="lower right")
        _salvar(fig, f"delta_tstt_cenarios{suf}.png", feitas)

        fig, ax = plt.subplots(figsize=(6.5, 5), dpi=160)
        xs = [r["niveis"][n]["comparacao_com_base"]["delta_tstt_pct"] for r in cens for n in NIVEIS]
        ys = [r["niveis"][n]["comparacao_com_base"]["delta_k_rede"] for r in cens for n in NIVEIS]
        ex, ey = max(map(abs, xs)) * 1.1, max(map(abs, ys)) * 1.15 or 0.01
        ax.add_patch(plt.Rectangle((0, 0), ex, ey, color=SERIE[1], alpha=0.08, linewidth=0))
        ax.text(ex * 0.97, ey * 0.92, "K melhora, TSTT piora", ha="right", fontsize=8, color=TINTA_2)
        for n in NIVEIS:
            ax.scatter([r["niveis"][n]["comparacao_com_base"]["delta_tstt_pct"] for r in cens],
                       [r["niveis"][n]["comparacao_com_base"]["delta_k_rede"] for r in cens],
                       s=30, color=ORDINAL_NIVEIS[n], edgecolor="white", linewidth=0.8, label=f"demanda {n}", zorder=3)
        for r in cens:
            c = r["niveis"]["adotada"]["comparacao_com_base"]
            if abs(c["delta_tstt_pct"]) > DESPREZIVEL_PCT:
                ax.annotate(r["cenario"].get("codigo", ""), (c["delta_tstt_pct"], c["delta_k_rede"]), xytext=(5, 4),
                            textcoords="offset points", fontsize=8, color=TINTA_2)
        ax.axhline(0, color=BASE_LINHA, linewidth=1); ax.axvline(0, color=BASE_LINHA, linewidth=1)
        ax.set_xlim(-ex, ex); ax.set_ylim(-ey, ey)
        ax.set_xlabel("Δ TSTT (%)  →  piora"); ax.set_ylabel("Δ K da rede  →  melhora")
        ax.set_title("K da rede × TSTT por cenário" + (" (a = 0,8; b = 4,7)" if suf else ""), loc="left", fontsize=11)
        _estilo(ax); ax.legend(frameon=False, fontsize=8, loc="lower left")
        _salvar(fig, f"k_x_tstt_cenarios{suf}.png", feitas)

    base = rodadas.get("base")
    if base is not None and "" in varreduras:
        t = base["tabelas"]["adotada"]
        for modo, rot, tit in (("remocao", "Δ TSTT ao fechar (%)", "efeito no TSTT de fechar cada aresta"),
                               ("faixa", "Δ TSTT com +1 faixa (%)", "efeito no TSTT de +1 faixa em cada aresta")):
            if modo not in varreduras[""]:
                continue
            vt = varreduras[""][modo]["tabela"]
            vt = vt[vt["nivel"] == "adotada"].set_index("aresta")
            val = t["aresta"].map(lambda e: np.nan if vt.loc[e, "desconecta"] else vt.loc[e, "delta_tstt_pct"])
            corta = [tuple(e.split("->")) for e in vt.index[vt["desconecta"]]]
            fig, ax = plt.subplots(figsize=(8, 8), dpi=160)
            _mapa(ax, G, t, val, div, TwoSlopeNorm(0, -10, 10), False,
                  f"Varredura: {tit}, demanda adotada\n(cor saturada além de ±10%; tracejado cinza = fechar desconecta pares OD)",
                  rot, fig, tracejadas=corta if modo == "remocao" else None)
            _salvar(fig, f"mapa_varredura_{modo}_adotada.png", feitas)
    return feitas


def main() -> None:
    G = nx.read_graphml(GRAFO)
    rodadas = carregar_rodadas()
    varreduras = carregar_varreduras(G)
    painel = gerar_painel(G, rodadas, varreduras)
    figuras = gerar_figuras(G, rodadas, varreduras)
    print(f"Rodadas: {len(rodadas)} ({', '.join(sorted(rodadas))})")
    print(f"Varreduras: {', '.join(f'{m}{s}' for s, ms in varreduras.items() for m in ms) or 'nenhuma'}")
    print(f"Painel: {painel.relative_to(RAIZ)}")
    print(f"Figuras: {len(figuras)} em {FIGURAS.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
