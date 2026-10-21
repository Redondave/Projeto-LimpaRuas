"""
Visualizacao dos resultados do Frank-Wolfe (scripts/frank_wolfe.py).

Le todas as rodadas em resultados/*/resumo.json (situacao atual e cenarios, em
cada nivel de demanda) e gera:

    resultados/painel.html     painel interativo: mapa com fluxo, V/C, K e
                               diferencas para a situacao atual; indicadores;
                               convergencia; comparacao entre rodadas; tabela
                               de arestas. Abre direto no navegador (precisa de
                               internet so para o fundo do mapa e as bibliotecas).
    resultados/figuras/*.png   figuras estaticas para o artigo

Uso (da raiz do repositorio):
    python scripts/visualizar_resultados.py
"""

from __future__ import annotations

import json
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


def carregar_rodadas() -> dict:
    rodadas = {}
    for resumo in sorted(RESULTADOS.glob("*/resumo.json")):
        r = json.loads(resumo.read_text(encoding="utf-8"))
        r["tabelas"] = {n: pd.read_csv(resumo.parent / f"arestas_{n}.csv", encoding="utf-8-sig",
                                       dtype={"u": str, "v": str}) for n in NIVEIS}
        rodadas[r["rodada"]] = r
    if not rodadas:
        sys.exit("Nenhum resultado em resultados/. Rode antes: python scripts/frank_wolfe.py")
    return rodadas


def base_de(rodadas: dict, r: dict) -> dict | None:
    if r.get("cenario") is None:
        return None
    return rodadas.get(Path(r["base"]).name)


# ---------------------------------------------------------------------------
# Painel interativo
# ---------------------------------------------------------------------------
def dados_painel(G: nx.DiGraph, rodadas: dict) -> dict:
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
    saida = {"arestas": arestas, "rodadas": {}}
    for nome, r in rodadas.items():
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
        saida["rodadas"][nome] = {
            "cenario": r.get("cenario"), "base": Path(r["base"]).name if base else None,
            "bpr": r["bpr"], "gerado_em": r["gerado_em"], "niveis": niveis}
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
  --serie-1: #2a78d6; --serie-2: #eb6834;
  --removida: #898781;
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
    --serie-1: #3987e5; --serie-2: #d95926;
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
  --serie-1: #3987e5; --serie-2: #d95926;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text-primary);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1240px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; font-weight: 650; }
h2 { font-size: 15px; margin: 0 0 12px; font-weight: 600; }
.sub { color: var(--text-secondary); margin: 0 0 20px; }
.filtros { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: end; margin-bottom: 16px; }
.filtros label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
select, button { font: inherit; color: var(--text-primary); background: var(--surface-1);
  border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; }
.segmentado { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.segmentado button { border: 0; border-radius: 0; padding: 6px 12px; background: var(--surface-1); cursor: pointer; }
.segmentado button[aria-pressed="true"] { background: var(--text-primary); color: var(--surface-1); }
.check { flex-direction: row !important; align-items: center; gap: 6px !important; font-size: 13px !important; color: var(--text-primary) !important; }
.cartao { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile .rot { font-size: 12px; color: var(--text-secondary); }
.tile .val { font-size: 24px; font-weight: 600; margin-top: 2px; }
.tile .det { font-size: 12px; color: var(--text-secondary); margin-top: 2px; min-height: 18px; }
.melhor { color: var(--good); } .pior { color: var(--critical); }
#mapa { height: 540px; border-radius: 8px; }
.legenda { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: center; font-size: 12px; color: var(--text-secondary); }
.legenda svg text { fill: var(--text-secondary); font-size: 11px; }
.grade2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
@media (max-width: 860px) { .grade2 { grid-template-columns: 1fr; } #mapa { height: 400px; } }
.grafico svg { width: 100%; height: auto; display: block; overflow: visible; }
.grafico text { fill: var(--muted); font-size: 11px; }
.grafico .rotulo { fill: var(--text-secondary); font-size: 12px; }
.tip { position: fixed; pointer-events: none; background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,.12); display: none; z-index: 1000; max-width: 280px; }
.tip strong { font-size: 13px; }
.tip .linha { display: flex; align-items: center; gap: 6px; }
.tip .chave { width: 14px; height: 2px; display: inline-block; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: right; padding: 6px 8px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; white-space: nowrap; }
th:first-child, td:first-child, th.txt, td.txt { text-align: left; }
th { color: var(--text-secondary); font-weight: 600; cursor: pointer; user-select: none; }
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
    <label class="check"><input type="checkbox" id="f-gargalo" checked> destacar os 25 gargalos calibrados</label>
  </div>

  <div class="tiles" id="tiles"></div>

  <div class="cartao">
    <h2 id="t-mapa">Mapa</h2>
    <div id="mapa" role="img" aria-label="Mapa da rede com as arestas coloridas pela métrica escolhida"></div>
    <div class="legenda" id="legenda"></div>
    <p class="nota">Espessura proporcional ao fluxo. Passe o mouse ou toque numa aresta para ver os valores; a tabela no fim da página traz os mesmos números.</p>
  </div>

  <div class="grade2">
    <div class="cartao grafico"><h2>Convergência (gap relativo por iteração)</h2><div id="g-conv"></div>
      <p class="nota">Critério de parada: gap relativo &lt; 10⁻⁴ ou 500 iterações.</p></div>
    <div class="cartao grafico"><h2 id="t-delta">Variação do TSTT em relação à situação atual</h2><div id="g-delta"></div></div>
  </div>

  <div class="cartao" style="margin-top:16px">
    <h2>Comparação entre rodadas</h2>
    <div class="tabela"><table id="tab-rodadas"></table></div>
  </div>

  <div class="cartao" style="margin-top:16px" id="c-conf">
    <h2>Conferência da situação atual com o observado (demanda adotada)</h2>
    <div class="tabela"><table id="tab-conf"></table></div>
    <p class="nota">Não é validação independente: as passagens vêm da mesma amostra TomTom da matriz, os contadores do DETRAN calibram o fator de expansão e o tempo observado calibra os gargalos (research/problemas_do_modelo.md, problema 2).</p>
  </div>

  <div class="cartao" style="margin-top:16px">
    <h2>Arestas</h2>
    <div class="filtros" style="margin-bottom:8px">
      <label>Buscar por nome ou aresta<input id="f-busca" type="search" placeholder="ex.: Contorno, 63->102" style="font:inherit;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface-1);color:var(--text-primary)"></label>
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
const NOME_NIVEL = {baixa: "baixa", adotada: "adotada", alta: "alta"};
const fmt = (v, d = 0) => v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", {minimumFractionDigits: d, maximumFractionDigits: d});
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const el = (tag, attrs = {}, ...filhos) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else e.setAttribute(k, v); }
  for (const f of filhos) e.append(f instanceof Node ? f : document.createTextNode(String(f))); return e; };
const I = {fluxo: 0, vc: 1, tempo: 2, vel: 3, k: 4, cap: 5, faixas: 6};

const estado = {rodada: Object.keys(D.rodadas).find(r => !D.rodadas[r].cenario) || Object.keys(D.rodadas)[0],
                nivel: "adotada", metrica: "vc", gargalo: true, todas: false, busca: "", ordem: null};

const METRICAS = {
  vc:          {rot: "V/C (volume ÷ capacidade)", tipo: "seq", dom: [0, 1.5], fmt: v => fmt(v, 2), tick: 1},
  k:           {rot: "K modelado (velocidade ÷ limite)", tipo: "seq-inv", dom: [0, 1], fmt: v => fmt(v, 2), tick: 1},
  fluxo:       {rot: "Fluxo (veíc/h)", tipo: "seq", dom: null, fmt: v => fmt(v, 0), tick: 0},
  k_obs:       {rot: "K observado no pico (TomTom)", tipo: "seq-inv", dom: [0, 1], fmt: v => fmt(v, 2), tick: 1, base: true},
  razao_tempo: {rot: "Tempo modelado ÷ observado", tipo: "div", dom: [0.5, 1, 1.5], fmt: v => fmt(v, 2), tick: 1, base: true},
  delta_fluxo: {rot: "Δ fluxo vs situação atual (veíc/h)", tipo: "div", dom: null, fmt: v => (v > 0 ? "+" : "") + fmt(v, 0), tick: 0, cen: true, abs: true},
  delta_k:     {rot: "Δ K vs situação atual", tipo: "div-inv", dom: null, fmt: v => (v > 0 ? "+" : "") + fmt(v, 3), tick: 2, cen: true, abs: true},
};

function rodadaAtual() { return D.rodadas[estado.rodada]; }
function nivelAtual() { return rodadaAtual().niveis[estado.nivel]; }
function baseAtual() { const r = rodadaAtual(); return r.base ? D.rodadas[r.base] : null; }

function valorMetrica(id, m) {
  const val = nivelAtual().valores[id], a = D.arestas[id];
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

function escala(m) {
  const cfg = METRICAS[m];
  const ids = Object.keys(nivelAtual().valores);
  const vals = ids.map(id => valorMetrica(id, m)).filter(v => v != null);
  if (cfg.tipo.startsWith("seq")) {
    const dom = cfg.dom || [0, d3.max(vals) || 1];
    const cores = [css("--seq-0"), css("--seq-1"), css("--seq-2")];
    const interp = d3.interpolateRgbBasis(cfg.tipo === "seq-inv" ? cores.slice().reverse() : cores);
    const s = d3.scaleSequential(interp).domain(dom).clamp(true);
    return {s, dom, cfg};
  }
  let dom = cfg.dom;
  if (!dom) { const mx = d3.max(vals, v => Math.abs(v)) || 1; dom = [-mx, 0, mx]; }
  const cores = cfg.tipo === "div-inv" ? [css("--div-pos"), css("--div-mid"), css("--div-neg")]
                                        : [css("--div-neg"), css("--div-mid"), css("--div-pos")];
  const s = d3.scaleDiverging(d3.interpolateRgbBasis(cores)).domain(dom).clamp(true);
  return {s, dom, cfg};
}

// ------------------------------------------------------------------ mapa
const mapa = L.map("mapa", {zoomControl: true, attributionControl: true});
let fundo = null;
function fundoDoTema() {
  const escuro = matchMedia("(prefers-color-scheme: dark)").matches && document.documentElement.dataset.theme !== "light"
                 || document.documentElement.dataset.theme === "dark";
  if (fundo) mapa.removeLayer(fundo);
  const servico = escuro ? "Canvas/World_Dark_Gray_Base" : "Canvas/World_Light_Gray_Base";
  fundo = L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/${servico}/MapServer/tile/{z}/{y}/{x}`,
    {attribution: "Fundo © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors", maxZoom: 16}).addTo(mapa);
}
fundoDoTema();
const camada = L.layerGroup().addTo(mapa);
const todosPontos = Object.values(D.arestas).flatMap(a => a.coords);
const enquadrar = () => { mapa.invalidateSize(); mapa.fitBounds(L.latLngBounds(todosPontos), {padding: [16, 16]}); };
mapa.setView(L.latLngBounds(todosPontos).getCenter(), 14);
// reenquadra quando o mapa muda de tamanho, ate a pessoa mexer nele
let mexeu = false;
for (const ev of ["mousedown", "wheel", "touchstart", "keydown"])
  document.getElementById("mapa").addEventListener(ev, () => { mexeu = true; }, {passive: true});
new ResizeObserver(() => { if (!mexeu) enquadrar(); else mapa.invalidateSize(); }).observe(document.getElementById("mapa"));

function tooltipAresta(id, removida) {
  const a = D.arestas[id], val = nivelAtual().valores[id];
  const box = el("div");
  box.append(el("strong", {}, a.nome || "(sem nome)"), el("div", {style: "color:var(--text-secondary)"}, `${id} · ${a.classe} · ${fmt(a.L, 0)} m${a.gargalo ? " · gargalo calibrado" : ""}`));
  if (removida) { box.append(el("div", {}, "Removida neste cenário")); return box; }
  const linhas = [["Fluxo", `${fmt(val[I.fluxo], 0)} veíc/h`], ["Capacidade", `${fmt(val[I.cap], 0)} veíc/h (${val[I.faixas]} faixa${val[I.faixas] > 1 ? "s" : ""})`],
    ["V/C", fmt(val[I.vc], 2)], ["Velocidade modelada", `${fmt(val[I.vel], 1)} km/h (limite ${fmt(a.lim, 0)})`],
    ["K modelado", fmt(val[I.k], 2)], ["K observado", fmt(a.k_obs, 2)]];
  const m = estado.metrica;
  if (!["vc", "k", "fluxo", "k_obs"].includes(m)) linhas.push([METRICAS[m].rot, METRICAS[m].fmt(valorMetrica(id, m))]);
  for (const [k, v] of linhas) box.append(el("div", {}, el("span", {style: "color:var(--text-secondary)"}, k + ": "), v));
  return box;
}

function desenharMapa() {
  camada.clearLayers();
  const {s} = escala(estado.metrica);
  const vals = nivelAtual().valores;
  const maxF = d3.max(Object.values(vals), v => v[I.fluxo]) || 1;
  const largura = f => 1.5 + 7 * Math.sqrt(Math.max(f, 0) / maxF);
  const b = baseAtual();
  if (b) for (const id of Object.keys(b.niveis[estado.nivel].valores)) if (!vals[id]) {
    L.polyline(D.arestas[id].coords, {color: css("--removida"), weight: 2, dashArray: "4 4"})
      .bindTooltip(() => tooltipAresta(id, true), {sticky: true}).addTo(camada);
  }
  const ordem = Object.keys(vals).sort((x, y) => vals[x][I.fluxo] - vals[y][I.fluxo]);
  for (const id of ordem) {
    const v = valorMetrica(id, estado.metrica), a = D.arestas[id];
    if (estado.gargalo && a.gargalo)
      L.polyline(a.coords, {color: css("--text-primary"), weight: largura(vals[id][I.fluxo]) + 4, opacity: .55}).addTo(camada);
    L.polyline(a.coords, {color: v == null ? css("--muted") : s(v), weight: largura(vals[id][I.fluxo]), opacity: .95, lineCap: "round"})
      .bindTooltip(() => tooltipAresta(id, false), {sticky: true}).addTo(camada);
  }
  legenda(maxF);
}

function legenda(maxF) {
  const box = document.getElementById("legenda"); box.replaceChildren();
  const {s, dom, cfg} = escala(estado.metrica);
  const w = 240, h = 34, svg = d3.create("svg").attr("width", w + 20).attr("height", h);
  const id = "grad" + Math.random().toString(36).slice(2);
  const g = svg.append("defs").append("linearGradient").attr("id", id);
  d3.range(0, 1.0001, 0.1).forEach(t => g.append("stop").attr("offset", t).attr("stop-color", s(dom[0] + t * (dom[dom.length - 1] - dom[0]))));
  svg.append("rect").attr("x", 10).attr("y", 2).attr("width", w).attr("height", 10).attr("rx", 2).attr("fill", `url(#${id})`);
  const x = d3.scaleLinear().domain([dom[0], dom[dom.length - 1]]).range([10, 10 + w]);
  x.ticks(4).forEach(t => svg.append("text").attr("x", x(t)).attr("y", 28).attr("text-anchor", "middle")
    .text((cfg.cen && t > 0 ? "+" : "") + fmt(t, cfg.tick)));
  box.append(el("span", {}, cfg.rot + (cfg.tipo === "seq-inv" ? " — mais escuro = mais lento" : "")), svg.node());
  if (estado.gargalo) box.append(el("span", {}, "Contorno escuro = gargalo com capacidade efetiva"));
  box.append(el("span", {}, `Espessura: fluxo de 0 a ${fmt(maxF, 0)} veíc/h`));
}

// ------------------------------------------------------------------ indicadores
function tiles() {
  const box = document.getElementById("tiles"); box.replaceChildren();
  const ind = nivelAtual().indicadores, comp = nivelAtual().comparacao;
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
      const d = ind[chave] - ib[chave];
      const pct = ib[chave] ? 100 * d / ib[chave] : 0;
      if (Math.abs(d) < 1e-9) det.append("igual à situação atual");
      else { const bom = menorMelhor ? d < 0 : d > 0;
        det.append(el("span", {class: bom ? "melhor" : "pior"}, `${d < 0 ? "▼" : "▲"} ${fmt(Math.abs(pct), 2)}% (${bom ? "melhor" : "pior"})`), " vs situação atual"); }
    } else if (chave === null) det.append(`fator de expansão ${fmt(nivelAtual().fator, 2)}`);
    box.append(el("div", {class: "cartao tile"}, el("div", {class: "rot"}, rot), el("div", {class: "val"}, val), det));
  }
  const conv = el("div", {class: "det"}, `gap ${ind.gap_relativo.toExponential(1).replace(".", ",")} · ${ind.convergiu ? "convergiu" : "NÃO convergiu"}`);
  box.append(el("div", {class: "cartao tile"}, el("div", {class: "rot"}, "Iterações do Frank-Wolfe"), el("div", {class: "val"}, fmt(ind.iteracoes)), conv));
}

// ------------------------------------------------------------------ tooltip comum
const tip = document.getElementById("tip");
function mostrarTip(ev, nodes) { tip.replaceChildren(...nodes); tip.style.display = "block";
  const r = tip.getBoundingClientRect(); let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14; if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
  tip.style.left = x + "px"; tip.style.top = y + "px"; }
function esconderTip() { tip.style.display = "none"; }

// ------------------------------------------------------------------ convergencia
function graficoConvergencia() {
  const box = document.getElementById("g-conv"); box.replaceChildren();
  const r = rodadaAtual(), W = 520, H = 260, m = {t: 12, r: 70, b: 34, l: 52};
  const series = NIVEIS.map(n => ({n, pts: r.niveis[n].convergencia.filter(p => p[1] > 0)}));
  const maxIt = d3.max(series, s => d3.max(s.pts, p => p[0])) || 1;
  const x = d3.scaleLinear().domain([1, Math.max(2, maxIt)]).range([m.l, W - m.r]);
  const ys = series.flatMap(s => s.pts.map(p => p[1]));
  const y = d3.scaleLog().domain([Math.min(1e-5, d3.min(ys)), Math.max(1, d3.max(ys))]).range([H - m.b, m.t]).nice();
  const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
    .attr("aria-label", "Gap relativo por iteração nos três níveis de demanda");
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
    if (ult) svg.append("text").attr("x", x(ult[0]) + 6).attr("y", y(ult[1]) + 4).attr("class", "rotulo").text(NOME_NIVEL[s.n]);
  }
  const cruz = svg.append("line").attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--axis")).style("display", "none");
  svg.append("rect").attr("x", m.l).attr("y", m.t).attr("width", W - m.r - m.l).attr("height", H - m.b - m.t).attr("fill", "transparent")
    .on("pointermove", ev => { const [px] = d3.pointer(ev); const it = Math.max(1, Math.min(maxIt, Math.round(x.invert(px))));
      cruz.attr("x1", x(it)).attr("x2", x(it)).style("display", null);
      const nodes = [el("div", {}, `iteração ${it}`)];
      for (const s of series) { const p = s.pts.find(q => q[0] === it);
        nodes.push(el("div", {class: "linha"}, el("span", {class: "chave", style: `background:${css(`--ord-${s.n}`)}`}),
          el("strong", {}, p ? p[1].toExponential(2).replace(".", ",") : "convergiu antes"), ` demanda ${NOME_NIVEL[s.n]}`)); }
      mostrarTip(ev, nodes); })
    .on("pointerleave", () => { cruz.style("display", "none"); esconderTip(); });
  legendaNiveis(box);
}
function sup(n) { return String(n).replace("-", "⁻").replace(/\d/g, d => "⁰¹²³⁴⁵⁶⁷⁸⁹"[d]); }
function legendaNiveis(box) {
  const lg = el("div", {class: "legenda"});
  for (const n of NIVEIS) lg.append(el("span", {}, el("span", {style: `display:inline-block;width:16px;height:2px;vertical-align:middle;margin-right:6px;background:${css(`--ord-${n}`)}`}),
    `demanda ${NOME_NIVEL[n]} (fator ${fmt(rodadaAtual().niveis[n].fator, 2)})`));
  box.append(lg);
}

// ------------------------------------------------------------------ delta TSTT
function graficoDelta() {
  const box = document.getElementById("g-delta"); box.replaceChildren();
  const cens = Object.entries(D.rodadas).filter(([, r]) => r.cenario);
  if (!cens.length) { box.append(el("p", {class: "nota"}, "Nenhum cenário rodado ainda. Rode python scripts/frank_wolfe.py --cenario cenarios/<arquivo>.json e gere o painel de novo.")); return; }
  const linhas = cens.flatMap(([nome, r]) => NIVEIS.map(n => ({nome, n, v: r.niveis[n].comparacao.delta_tstt_pct})));
  const W = 520, bandaH = 14, gap = 2, grupo = NIVEIS.length * (bandaH + gap) + 14, m = {t: 8, r: 64, b: 30, l: 170};
  const H = m.t + m.b + cens.length * grupo;
  const ext = d3.max(linhas, d => Math.abs(d.v)) || 1;
  const x = d3.scaleLinear().domain([-ext, ext]).nice().range([m.l, W - m.r]);
  const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", "Variação percentual do TSTT por cenário e nível de demanda");
  x.ticks(5).forEach(t => { svg.append("line").attr("x1", x(t)).attr("x2", x(t)).attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--grid"));
    svg.append("text").attr("x", x(t)).attr("y", H - m.b + 16).attr("text-anchor", "middle").text(`${fmt(t, 0)}%`); });
  svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", m.t).attr("y2", H - m.b).attr("stroke", css("--axis"));
  cens.forEach(([nome], i) => {
    const y0 = m.t + i * grupo;
    svg.append("text").attr("x", m.l - 8).attr("y", y0 + grupo / 2).attr("text-anchor", "end").attr("class", "rotulo").text(nome.length > 26 ? nome.slice(0, 25) + "…" : nome);
    NIVEIS.forEach((n, j) => { const d = linhas.find(l => l.nome === nome && l.n === n), yy = y0 + 7 + j * (bandaH + gap);
      const x1 = Math.min(x(0), x(d.v)), w = Math.max(1, Math.abs(x(d.v) - x(0)));
      svg.append("rect").attr("x", x1).attr("y", yy).attr("width", w).attr("height", bandaH).attr("rx", 2).attr("fill", css(`--ord-${n}`))
        .on("pointermove", ev => mostrarTip(ev, [el("strong", {}, `${d.v > 0 ? "+" : ""}${fmt(d.v, 2)}%`), el("div", {}, `${nome} · demanda ${NOME_NIVEL[n]}`)]))
        .on("pointerleave", esconderTip);
      svg.append("text").attr("x", d.v < 0 ? x1 - 4 : x1 + w + 4).attr("y", yy + bandaH - 3).attr("text-anchor", d.v < 0 ? "end" : "start").text(`${d.v > 0 ? "+" : ""}${fmt(d.v, 1)}%`);
    });
  });
  legendaNiveis(box);
  box.append(el("p", {class: "nota"}, "Negativo = o sistema inteiro gasta menos tempo que na situação atual."));
}

// ------------------------------------------------------------------ tabelas
function tabelaRodadas() {
  const t = document.getElementById("tab-rodadas"); t.replaceChildren();
  const cab = ["Rodada", "Demanda", "Veíc/h", "TSTT (veíc·h)", "Δ TSTT", "K da rede", "Δ K", "Vel. média (km/h)", "V/C > 1", "Iterações", "Gap"];
  t.append(el("thead", {}, el("tr", {}, ...cab.map((c, i) => el("th", {class: i < 2 ? "txt" : ""}, c)))));
  const tb = el("tbody");
  for (const [nome, r] of Object.entries(D.rodadas)) for (const n of NIVEIS) {
    const ind = r.niveis[n].indicadores, c = r.niveis[n].comparacao;
    const celulas = [nome, NOME_NIVEL[n], fmt(ind.demanda_veic_h), fmt(ind.tstt_veic_h, 1),
      c ? `${c.delta_tstt_pct > 0 ? "+" : ""}${fmt(c.delta_tstt_pct, 2)}%` : "—", fmt(ind.k_rede, 3),
      c ? `${c.delta_k_rede > 0 ? "+" : ""}${fmt(c.delta_k_rede, 4)}` : "—", fmt(ind.velocidade_media_rede_kmh, 1),
      fmt(ind.arestas_vc_acima_1), fmt(ind.iteracoes), ind.gap_relativo.toExponential(1).replace(".", ",")];
    tb.append(el("tr", {}, ...celulas.map((v, i) => el("td", {class: i < 2 ? "txt" : ""}, v))));
  }
  t.append(tb);
}

function tabelaConferencia() {
  const t = document.getElementById("tab-conf"), card = document.getElementById("c-conf"); t.replaceChildren();
  const b = D.rodadas[estado.rodada].cenario ? D.rodadas[D.rodadas[estado.rodada].base] : D.rodadas[estado.rodada];
  const c = b && b.niveis.adotada.conferencias; if (!c) { card.style.display = "none"; return; } card.style.display = "";
  const p = c.fluxo_x_passagens_tomtom, tm = c.tempo_x_observado;
  const linhas = [
    ["Fluxo × passagens TomTom", "escolha de rota", `${p.arestas} arestas`, `correlação ${fmt(p.correlacao, 2)}; modelo/obs. ${fmt(p.razao_mediana_modelo_obs, 2)} (mediana); GEH mediano ${fmt(p.geh_mediano, 1)}; ${fmt(100 * p.fracao_geh_abaixo_5, 0)}% com GEH < 5`],
    ["Tempo × observado, arestas não calibradas", "VDF e t0", `${tm.nao_calibradas.arestas} arestas`, `modelo/obs. ${fmt(tm.nao_calibradas.razao_mediana_modelo_obs, 2)} (mediana); ${fmt(100 * tm.nao_calibradas.fracao_dentro_10pct, 0)}% dentro de ±10%`],
    ["Tempo × observado, arestas calibradas", "nada (calibradas)", `${tm.calibradas_gargalo_ou_v0_do_pico.arestas} arestas`, `modelo/obs. ${fmt(tm.calibradas_gargalo_ou_v0_do_pico.razao_mediana_modelo_obs, 2)}`],
    ["Tempo total ponderado pelo fluxo", "—", "", `modelo/obs. ${fmt(tm.tempo_total_modelo_sobre_obs, 3)}`],
  ];
  for (const d of c.fluxo_x_detran.pistas) linhas.push([`DETRAN ${d.trecho} ${d.sentido}`, "nada (calibra o fator)", `${fmt(d.detran_veic_h)} contados`, `modelo ${fmt(d.modelo_veic_h)}; esperado só pelo fator único ${fmt(d.esperado_pelo_fator_veic_h)}`]);
  t.append(el("thead", {}, el("tr", {}, el("th", {class: "txt"}, "Comparação"), el("th", {class: "txt"}, "O que testa"), el("th", {class: "txt"}, "Base"), el("th", {class: "txt"}, "Resultado"))));
  const tb = el("tbody"); for (const l of linhas) tb.append(el("tr", {}, ...l.map(v => el("td", {class: "txt"}, v)))); t.append(tb);
}

function tabelaArestas() {
  const t = document.getElementById("tab-arestas"); t.replaceChildren();
  const m = estado.metrica, cfg = METRICAS[m], vals = nivelAtual().valores;
  const cols = [["Aresta", r => r.id, true], ["Nome", r => r.a.nome, true], ["Classe", r => r.a.classe, true],
    ["Fluxo (veíc/h)", r => r.v[I.fluxo]], ["Capacidade", r => r.v[I.cap]], ["V/C", r => r.v[I.vc]],
    ["Vel. (km/h)", r => r.v[I.vel]], ["K modelado", r => r.v[I.k]], ["K obs.", r => r.a.k_obs]];
  if (!["vc", "k", "fluxo", "k_obs"].includes(m)) cols.push([cfg.rot, r => valorMetrica(r.id, m)]);
  let linhas = Object.keys(vals).map(id => ({id, a: D.arestas[id], v: vals[id]}));
  const q = estado.busca.toLowerCase();
  if (q) linhas = linhas.filter(r => r.id.includes(q) || (r.a.nome || "").toLowerCase().includes(q));
  const [ci, dir] = estado.ordem || [cols.length - 1 > 8 ? cols.length - 1 : (m === "k" || m === "k_obs" ? 7 : m === "fluxo" ? 3 : 5), m === "k" || m === "k_obs" ? 1 : -1];
  const absoluto = !estado.ordem && cfg.abs;
  linhas.sort((x, y) => { let a = cols[ci][1](x), b = cols[ci][1](y);
    if (absoluto) { a = a == null ? null : Math.abs(a); b = b == null ? null : Math.abs(b); }
    if (a == null) return 1; if (b == null) return -1; return (a > b ? 1 : a < b ? -1 : 0) * dir; });
  t.append(el("thead", {}, el("tr", {}, ...cols.map(([c, , txt], i) => { const th = el("th", {class: txt ? "txt" : "", tabindex: "0"}, c + (i === ci ? (dir > 0 ? " ▲" : " ▼") : ""));
    const ordenar = () => { estado.ordem = [i, i === ci ? -dir : (txt ? 1 : -1)]; tabelaArestas(); };
    th.addEventListener("click", ordenar); th.addEventListener("keydown", e => { if (e.key === "Enter") ordenar(); }); return th; }))));
  const tb = el("tbody");
  for (const r of (estado.todas || q ? linhas : linhas.slice(0, 25))) tb.append(el("tr", {}, ...cols.map(([, f, txt], i) => {
    const v = f(r); const s = v == null ? "—" : txt ? v : (i === 3 || i === 4 ? fmt(v, 0) : i === 6 ? fmt(v, 1) : cfg && i === 9 ? cfg.fmt(v) : fmt(v, 2));
    return el("td", {class: txt ? "txt" : ""}, s || "—"); })));
  t.append(tb);
  document.getElementById("b-todas").textContent = estado.todas ? "Mostrar só as 25 primeiras" : `Mostrar todas (${Object.keys(vals).length})`;
}

// ------------------------------------------------------------------ filtros
function montarFiltros() {
  const fr = document.getElementById("f-rodada");
  for (const nome of Object.keys(D.rodadas)) fr.append(el("option", {value: nome}, nome + (D.rodadas[nome].cenario ? " (cenário)" : " (situação atual)")));
  fr.value = estado.rodada;
  fr.onchange = () => { estado.rodada = fr.value; estado.ordem = null; opcoesMetrica(); tudo(); };
  const fn = document.getElementById("f-nivel");
  for (const n of NIVEIS) { const b = el("button", {type: "button", "aria-pressed": String(n === estado.nivel)}, NOME_NIVEL[n]);
    b.onclick = () => { estado.nivel = n; [...fn.children].forEach(c => c.setAttribute("aria-pressed", String(c === b))); tudo(); }; fn.append(b); }
  document.getElementById("f-gargalo").onchange = e => { estado.gargalo = e.target.checked; desenharMapa(); };
  document.getElementById("f-busca").oninput = e => { estado.busca = e.target.value; tabelaArestas(); };
  document.getElementById("b-todas").onclick = () => { estado.todas = !estado.todas; tabelaArestas(); };
  opcoesMetrica();
}
function opcoesMetrica() {
  const fm = document.getElementById("f-metrica"); fm.replaceChildren();
  const cen = !!rodadaAtual().cenario;
  for (const [k, c] of Object.entries(METRICAS)) { if (c.cen && !cen) continue; fm.append(el("option", {value: k}, c.rot)); }
  if (!fm.querySelector(`option[value="${estado.metrica}"]`)) estado.metrica = cen ? "delta_fluxo" : "vc";
  fm.value = estado.metrica;
  fm.onchange = () => { estado.metrica = fm.value; estado.ordem = null; desenharMapa(); tabelaArestas(); };
}
function tudo() {
  const r = rodadaAtual();
  document.getElementById("sub").textContent = `Equilíbrio do usuário (Frank-Wolfe) · BPR α = ${fmt(r.bpr.alpha, 2)}, β = ${fmt(r.bpr.beta, 1)} · pico 18–19h de dia útil, julho/2026` +
    (r.cenario ? ` · cenário: ${r.cenario.descricao || r.cenario.nome}` : " · situação atual");
  document.getElementById("t-mapa").textContent = `Mapa — ${r.cenario ? r.cenario.nome : "situação atual"}, demanda ${NOME_NIVEL[estado.nivel]}`;
  tiles(); desenharMapa(); graficoConvergencia(); graficoDelta(); tabelaRodadas(); tabelaConferencia(); tabelaArestas();
}
document.getElementById("rodape").textContent = "Gerado por scripts/visualizar_resultados.py a partir de resultados/*/resumo.json. Unidades: fluxo e capacidade em veículos por hora por sentido; tempos em minutos; TSTT em veículo·hora no pico.";
montarFiltros(); tudo();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { fundoDoTema(); tudo(); });
</script>
</body>
</html>
"""


def gerar_painel(G: nx.DiGraph, rodadas: dict) -> Path:
    dados = json.dumps(dados_painel(G, rodadas), ensure_ascii=False, separators=(",", ":"))
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


def _mapa(ax, G, t: pd.DataFrame, valores: pd.Series, cmap, norm, gargalos: bool, titulo: str, rotulo: str, fig):
    geoms = geometrias(G)
    maxf = t["fluxo_veic_h"].max() or 1
    t = t.assign(_v=valores.values).sort_values("fluxo_veic_h")
    if gargalos:
        segs = [np.asarray(geometria(geoms, r.u, r.v).coords) for r in t.itertuples() if r.gargalo]
        ax.add_collection(LineCollection(segs, colors=TINTA, linewidths=[0.8 + 5 * np.sqrt(f / maxf) + 2.4
                                         for f in t.loc[t["gargalo"], "fluxo_veic_h"]], alpha=0.5, capstyle="round"))
    segs = [np.asarray(geometria(geoms, r.u, r.v).coords) for r in t.itertuples()]
    cores = [cmap(norm(v)) if pd.notna(v) else MUDO for v in t["_v"]]
    ax.add_collection(LineCollection(segs, colors=cores, linewidths=0.8 + 5 * np.sqrt(t["fluxo_veic_h"] / maxf),
                                     capstyle="round"))
    ax.autoscale()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(titulo, loc="left", fontsize=11, color=TINTA)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm, ax=ax, shrink=0.55, pad=0.01)
    cb.set_label(rotulo, color=TINTA_2, fontsize=9)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=MUDO, labelsize=8)


def gerar_figuras(G: nx.DiGraph, rodadas: dict) -> list[Path]:
    FIGURAS.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "text.color": TINTA,
                         "axes.labelcolor": TINTA_2, "figure.facecolor": "white"})
    seq = LinearSegmentedColormap.from_list("seq", AZUL_SEQ)
    div = LinearSegmentedColormap.from_list("div", DIVERGENTE)
    feitas = []
    for nome, r in rodadas.items():
        t = r["tabelas"]["adotada"]
        base = base_de(rodadas, r)
        if base is None:
            fig, ax = plt.subplots(figsize=(8, 8), dpi=160)
            _mapa(ax, G, t, t["vc"], seq, Normalize(0, 1.5), True,
                  f"{nome}: V/C no equilíbrio, demanda adotada (espessura = fluxo; contorno = gargalo calibrado)",
                  "volume ÷ capacidade", fig)
            feitas.append(FIGURAS / f"mapa_vc_{nome}_adotada.png")
            fig.savefig(feitas[-1], bbox_inches="tight"); plt.close(fig)

            fig, ax = plt.subplots(figsize=(8, 8), dpi=160)
            _mapa(ax, G, t, t["k_modelado"], seq.reversed(), Normalize(0, 1), False,
                  f"{nome}: K modelado, demanda adotada (mais escuro = mais lento)", "K = velocidade ÷ limite", fig)
            feitas.append(FIGURAS / f"mapa_k_{nome}_adotada.png")
            fig.savefig(feitas[-1], bbox_inches="tight"); plt.close(fig)

            ok = t[t["t_obs_min"].notna()].copy()
            calib = ok["gargalo"] | np.isclose(ok["v0_kmh"], ok["vmed_obs_kmh"], atol=0.05)
            fig, ax = plt.subplots(figsize=(5.5, 5), dpi=160)
            lim = max(ok["t_obs_min"].max(), ok["tempo_min"].max()) * 1.05
            ax.plot([0, lim], [0, lim], color=BASE_LINHA, linewidth=1)
            for (rot, m), cor in zip([("não calibradas", ~calib), ("calibradas (gargalo ou t0 do pico)", calib)], SERIE):
                ax.scatter(ok.loc[m, "t_obs_min"], ok.loc[m, "tempo_min"], s=18, color=cor, edgecolor="white",
                           linewidth=0.6, label=f"{rot} ({int(m.sum())})")
            ax.set_xlim(0, lim); ax.set_ylim(0, lim)
            ax.set_xlabel("tempo observado no pico (min)"); ax.set_ylabel("tempo modelado (min)")
            ax.set_title(f"{nome}: tempo por aresta, modelado × observado", loc="left", fontsize=11)
            _estilo(ax); ax.legend(frameon=False, fontsize=9)
            feitas.append(FIGURAS / f"tempo_modelado_x_observado_{nome}.png")
            fig.savefig(feitas[-1], bbox_inches="tight"); plt.close(fig)
        else:
            tb = base["tabelas"]["adotada"].set_index("aresta")
            delta = t.set_index("aresta")["fluxo_veic_h"] - tb["fluxo_veic_h"].reindex(t["aresta"]).fillna(0).values
            ext = max(abs(delta).max(), 1)
            fig, ax = plt.subplots(figsize=(8, 8), dpi=160)
            _mapa(ax, G, t, delta.reset_index(drop=True), div, TwoSlopeNorm(0, -ext, ext), False,
                  f"{nome}: diferença de fluxo para a situação atual, demanda adotada", "Δ fluxo (veíc/h)", fig)
            feitas.append(FIGURAS / f"mapa_delta_fluxo_{nome}_adotada.png")
            fig.savefig(feitas[-1], bbox_inches="tight"); plt.close(fig)

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
        feitas.append(FIGURAS / f"convergencia_{nome}.png")
        fig.savefig(feitas[-1], bbox_inches="tight"); plt.close(fig)

    cens = [(n, r) for n, r in rodadas.items() if r.get("cenario")]
    if cens:
        fig, ax = plt.subplots(figsize=(7, 1.2 + 0.9 * len(cens)), dpi=160)
        altura = 0.26
        for i, (nome, r) in enumerate(cens):
            for j, n in enumerate(NIVEIS):
                v = r["niveis"][n]["comparacao_com_base"]["delta_tstt_pct"]
                y = i + (j - 1) * (altura + 0.03)
                ax.barh(y, v, height=altura, color=ORDINAL_NIVEIS[n], label=f"demanda {n}" if i == 0 else None)
                ax.text(v + (0.1 if v >= 0 else -0.1), y, f"{v:+.1f}%", va="center", ha="left" if v >= 0 else "right",
                        fontsize=8, color=TINTA_2)
        ax.axvline(0, color=BASE_LINHA, linewidth=1)
        ax.set_yticks(range(len(cens)), [n for n, _ in cens])
        ax.set_xlabel("Δ TSTT em relação à situação atual (%)")
        ax.set_title("Variação do tempo total no sistema por cenário", loc="left", fontsize=11)
        _estilo(ax); ax.grid(axis="y", visible=False); ax.legend(frameon=False, fontsize=8)
        feitas.append(FIGURAS / "delta_tstt_cenarios.png")
        fig.savefig(feitas[-1], bbox_inches="tight"); plt.close(fig)
    return feitas


def main() -> None:
    G = nx.read_graphml(GRAFO)
    rodadas = carregar_rodadas()
    painel = gerar_painel(G, rodadas)
    figuras = gerar_figuras(G, rodadas)
    print(f"Rodadas: {', '.join(rodadas)}")
    print(f"Painel: {painel.relative_to(RAIZ)}")
    print("Figuras:")
    for f in figuras:
        print(f"  {f.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
