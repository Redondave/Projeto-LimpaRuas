# -*- coding: utf-8 -*-
"""
exportar_para_render.py - Converte o .graphml do OSMnx em formatos que as
ferramentas de visualizacao realmente conseguem abrir.

Por que isso e necessario: o .graphml que o OSMnx grava e otimo para *recarregar
no OSMnx* e pessimo para *desenhar em outra ferramenta*.

  1. Todas as arestas saem com o mesmo `id` (a chave do MultiDiGraph: 0, 0, 0...).
     O XSD oficial do GraphML declara <xs:unique name="edge_id_unique">, entao
     importadores que validam o esquema rejeitam o arquivo ou deduplicam arestas.
  2. Nenhum atributo e declarado numerico - x e y saem como attr.type="string".
     O Gephi so usa x/y como posicao quando sao double; como texto, viram coluna
     de dados e o grafo cai num layout aleatorio.
  3. As coordenadas sao graus: o Plano Piloto inteiro cabe num quadrado de
     0,13 x 0,16 unidades. Quem usa x/y direto ve tudo empilhado num ponto.
  4. O atributo `geometry` (WKT da curva de cada via) e 14-18% do arquivo e nao
     serve para nada num desenhador de grafos - so pesa o parse.

Uso:
    python grafo_brasilia/exportar_para_render.py --grafo plano_piloto_drive
    python grafo_brasilia/exportar_para_render.py --grafo brasilia_df_drive --simplificar 15
    python grafo_brasilia/exportar_para_render.py --grafo brasilia_df_drive --so-arteriais

Gera em saida/:
    <nome>_render.graphml   grafo enxuto, ids validos, x/y numericos em metros
                            -> Gephi, yEd, Cytoscape, igraph
    <nome>_arestas.geojson  geometria real das vias  -> QGIS, kepler.gl
    <nome>_mapa.html        mapa interativo autocontido -> qualquer navegador
"""

import argparse
import json
import sys
from pathlib import Path

import networkx as nx
import osmnx as ox

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "saida"

# cores por classe de via (mesma familia usada nas figuras do projeto)
CORES = {
    "motorway": "#ff5a36", "trunk": "#ff8c42", "primary": "#ffc145",
    "secondary": "#7fd1b9", "tertiary": "#4da6ff", "residential": "#5b7fa6",
    "unclassified": "#5b7fa6", "living_street": "#7a6fa6", "outro": "#44566b",
}
ARTERIAIS = {"motorway", "trunk", "primary", "secondary",
             "motorway_link", "trunk_link", "primary_link", "secondary_link"}


# --------------------------------------------------------------------------- #
def texto(v) -> str:
    """Atributo do OSM pode vir como lista quando a simplificacao funde ways."""
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return "" if v is None else str(v)


def classe(v) -> str:
    v = v[0] if isinstance(v, list) else v
    return v if v in CORES else "outro"


def numero(v, padrao=0.0) -> float:
    v = v[0] if isinstance(v, list) else v
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


# --------------------------------------------------------------------------- #
# 1. GraphML enxuto (Gephi / yEd / Cytoscape)
# --------------------------------------------------------------------------- #
def exportar_graphml(G, destino: Path) -> None:
    """
    Constroi um DiGraph simples e grava GraphML valido.

    - DiGraph em vez de MultiDiGraph: o networkx deixa de escrever o atributo
      `id` repetido nas arestas, e o arquivo passa a valer contra o XSD.
      As 70 arestas paralelas do Plano Piloto viram uma so (fica registrado em
      `n_paralelas`), o que nao muda nada para desenho.
    - x/y projetados em UTM e centrados na origem: as unidades viram METROS, e o
      Gephi/yEd aceitam direto como posicao dos nos.
    - Sem `geometry`: quem desenha grafo nao usa a curva da via.
    """
    print("[1/3] GraphML enxuto...")
    Gp = ox.projection.project_graph(G)          # WGS84 -> UTM, x/y em metros
    xs = [d["x"] for _, d in Gp.nodes(data=True)]
    ys = [d["y"] for _, d in Gp.nodes(data=True)]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)

    H = nx.DiGraph()
    H.graph["crs"] = str(Gp.graph.get("crs"))
    H.graph["fonte"] = "OpenStreetMap via OSMnx"
    for n, d in Gp.nodes(data=True):
        H.add_node(
            int(n),
            x=round(d["x"] - cx, 2),             # metros a partir do centro
            y=round(d["y"] - cy, 2),
            lon=round(G.nodes[n]["x"], 6),       # graus, para referencia
            lat=round(G.nodes[n]["y"], 6),
            street_count=int(numero(d.get("street_count"), 0)),
        )

    for u, v, d in Gp.edges(data=True):
        t = numero(d.get("travel_time"), 1e9)
        paralelas = 1
        if H.has_edge(u, v):                     # aresta paralela: fica a mais rapida
            paralelas = H.edges[u, v]["n_paralelas"] + 1
            if t >= H.edges[u, v]["travel_time"]:
                H.edges[u, v]["n_paralelas"] = paralelas
                continue
        attrs = {
            "highway": classe(d.get("highway")),
            "length": round(numero(d.get("length")), 2),
            "speed_kph": round(numero(d.get("speed_kph")), 1),
            "travel_time": round(t, 2),
            "n_paralelas": paralelas,
        }
        # so grava texto quando existe: atributo vazio vira <data/> inutil no XML
        for campo in ("name", "ref"):
            valor = texto(d.get(campo))
            if valor:
                attrs[campo] = valor
        H.add_edge(int(u), int(v), **attrs)

    nx.write_graphml(H, destino, named_key_ids=True)
    mb = destino.stat().st_size / 1e6
    print(f"      {H.number_of_nodes():,} nos, {H.number_of_edges():,} arestas -> "
          f"{destino.name} ({mb:.1f} MB)")


# --------------------------------------------------------------------------- #
# 2. GeoJSON (QGIS / kepler.gl)
# --------------------------------------------------------------------------- #
def exportar_geojson(arestas, destino: Path) -> None:
    print("[2/3] GeoJSON das arestas...")
    gdf = arestas.copy()
    for c in gdf.columns:
        if c != "geometry":
            gdf[c] = gdf[c].map(texto)           # GeoJSON nao aceita lista
    gdf = gdf.reset_index()[["u", "v", "name", "ref", "highway", "length",
                             "speed_kph", "travel_time", "geometry"]]
    gdf.to_file(destino, driver="GeoJSON")
    print(f"      {len(gdf):,} feicoes -> {destino.name} "
          f"({destino.stat().st_size/1e6:.1f} MB)")


# --------------------------------------------------------------------------- #
# 3. Mapa interativo autocontido
# --------------------------------------------------------------------------- #
def exportar_mapa(arestas, destino: Path, titulo: str) -> None:
    """
    Desenha as vias num <canvas>. O truque de performance e nao criar um elemento
    por aresta (SVG/DOM morre com 14 mil): e um unico canvas, um path por classe
    de via, redesenhado a cada zoom. 200 mil segmentos saem em milissegundos.

    As coordenadas vao delta-codificadas em inteiros de 1e-5 grau (~1,1 m), o que
    encolhe o JSON em cerca de 4x em relacao a texto decimal.
    """
    print("[3/3] Mapa interativo...")
    ordem = list(CORES.keys())
    linhas, nomes = [], []
    for (_, _, _), row in arestas.iterrows():
        g = row.geometry
        if g is None or g.geom_type != "LineString":
            continue
        cls = ordem.index(classe(row.get("highway")))
        pts = [(round(x * 1e5), round(y * 1e5)) for x, y in g.coords]
        seq, px, py = [], 0, 0
        for i, (x, y) in enumerate(pts):
            seq += [x, y] if i == 0 else [x - px, y - py]
            px, py = x, y
        linhas.append([cls] + seq)
        nomes.append(texto(row.get("name"))[:60])

    dados = {"titulo": titulo, "classes": ordem,
             "cores": [CORES[c] for c in ordem],
             "linhas": linhas, "nomes": nomes}
    payload = json.dumps(dados, separators=(",", ":"), ensure_ascii=False)
    destino.write_text(MAPA_HTML.replace("__DADOS__", payload), encoding="utf-8")
    print(f"      {len(linhas):,} vias -> {destino.name} "
          f"({destino.stat().st_size/1e6:.1f} MB)")


MAPA_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rede viaria</title>
<style>
  html,body{margin:0;height:100%;background:#0b0f14;color:#c9d6e0;
    font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;overflow:hidden}
  canvas{display:block;cursor:grab}canvas.arrasta{cursor:grabbing}
  .hud{position:fixed;top:14px;left:14px;background:rgba(11,15,20,.86);
    border:1px solid #24313d;border-radius:6px;padding:12px 14px;max-width:270px}
  .hud h1{margin:0 0 8px;font-size:13px;font-weight:600;color:#e8f0f6}
  .hud p{margin:0 0 8px;color:#8b9caa}
  .leg{display:grid;grid-template-columns:auto 1fr;gap:3px 8px;align-items:center}
  .sw{width:16px;height:3px;border-radius:2px}
  .via{position:fixed;bottom:14px;left:14px;background:rgba(11,15,20,.86);
    border:1px solid #24313d;border-radius:6px;padding:8px 12px;min-height:17px;color:#e8f0f6}
  .aj{position:fixed;bottom:14px;right:14px;color:#5d6f7e}
</style></head><body>
<canvas id="c"></canvas>
<div class="hud"><h1 id="t"></h1><p id="n"></p><div class="leg" id="l"></div></div>
<div class="via" id="v">passe o mouse sobre uma via</div>
<div class="aj">arraste para mover &middot; roda do mouse para zoom &middot; R ou duplo clique reenquadra</div>
<script>
const D = __DADOS__;
const cv = document.getElementById('c'), cx = cv.getContext('2d');

// descompacta o delta-encoding para coordenadas absolutas em graus
const vias = D.linhas.map(l => {
  const cls = l[0], pts = [];
  let x = 0, y = 0;
  for (let i = 1; i < l.length; i += 2) {
    x = (i === 1) ? l[i] : x + l[i];
    y = (i === 1) ? l[i+1] : y + l[i+1];
    pts.push(x / 1e5, y / 1e5);
  }
  return {cls, pts};
});

// projecao equirretangular corrigida pela latitude (fiel nesta escala)
let minx =  1e9, miny =  1e9, maxx = -1e9, maxy = -1e9;
for (const v of vias) for (let i = 0; i < v.pts.length; i += 2) {
  if (v.pts[i] < minx) minx = v.pts[i];
  if (v.pts[i] > maxx) maxx = v.pts[i];
  if (v.pts[i+1] < miny) miny = v.pts[i+1];
  if (v.pts[i+1] > maxy) maxy = v.pts[i+1];
}
const k = Math.cos((miny + maxy) / 2 * Math.PI / 180);
const proj = (lon, lat) => [lon * k, -lat];
const [px0, py0] = proj(minx, maxy), [px1, py1] = proj(maxx, miny);

let esc = 1, offx = 0, offy = 0, tocado = false;
function enquadrar() {
  const m = 24;
  if (cv.width <= 2*m || cv.height <= 2*m) return false;   // painel ainda sem tamanho
  esc = Math.min((cv.width - 2*m) / (px1 - px0), (cv.height - 2*m) / (py1 - py0));
  offx = (cv.width - (px1 - px0) * esc) / 2 - px0 * esc;
  offy = (cv.height - (py1 - py0) * esc) / 2 - py0 * esc;
  return true;
}
function dimensionar() {
  const r = window.devicePixelRatio || 1;
  const w = Math.max(innerWidth, 1), h = Math.max(innerHeight, 1);
  cv.width = w * r; cv.height = h * r;
  cv.style.width = w + 'px'; cv.style.height = h + 'px';
}
// Reenquadra sozinho enquanto ninguem mexeu no mapa - isso cobre o painel que
// abre com largura zero e a densidade de pixels que muda depois do load. Assim
// que a pessoa arrasta ou da zoom, o enquadramento passa a ser dela.
function atualizar() {
  dimensionar();
  if (!tocado) enquadrar();
  desenhar();
}

function desenhar() {
  cx.fillStyle = '#0b0f14';
  cx.fillRect(0, 0, cv.width, cv.height);
  cx.lineCap = 'round'; cx.lineJoin = 'round';
  // um Path2D por classe: 9 chamadas de stroke no lugar de milhares
  const paths = D.classes.map(() => new Path2D());
  for (const v of vias) {
    const p = paths[v.cls];
    for (let i = 0; i < v.pts.length; i += 2) {
      const [a, b] = proj(v.pts[i], v.pts[i+1]);
      const X = a * esc + offx, Y = b * esc + offy;
      if (i === 0) p.moveTo(X, Y); else p.lineTo(X, Y);
    }
  }
  const base = Math.max(0.35, Math.min(2.6, esc / 9000));
  const peso = [2.4, 2.2, 1.9, 1.5, 1.1, .7, .7, .7, .7];
  paths.forEach((p, i) => {
    cx.strokeStyle = D.cores[i];
    cx.lineWidth = base * (peso[i] || .7) * (window.devicePixelRatio || 1);
    cx.stroke(p);
  });
}

// ---- interacao ----
let arrastando = false, ax = 0, ay = 0;
cv.addEventListener('mousedown', e => {
  arrastando = true; ax = e.clientX; ay = e.clientY; cv.classList.add('arrasta');
});
addEventListener('mouseup', () => { arrastando = false; cv.classList.remove('arrasta'); });
cv.addEventListener('mousemove', e => {
  const r = window.devicePixelRatio || 1;
  if (arrastando) {
    tocado = true;
    offx += (e.clientX - ax) * r; offy += (e.clientY - ay) * r;
    ax = e.clientX; ay = e.clientY; desenhar();
  } else {
    achar(e.clientX * r, e.clientY * r);
  }
});
cv.addEventListener('wheel', e => {
  e.preventDefault();
  const r = window.devicePixelRatio || 1, mx = e.clientX * r, my = e.clientY * r;
  const f = e.deltaY < 0 ? 1.18 : 1/1.18;
  tocado = true;
  offx = mx - (mx - offx) * f; offy = my - (my - offy) * f; esc *= f;
  desenhar();
}, {passive: false});

// busca da via sob o cursor: grade uniforme sobre os vertices
const GRADE = 140, celulas = new Map();
function chave(i, j) { return i * 100000 + j; }
vias.forEach((v, idx) => {
  for (let i = 0; i < v.pts.length; i += 2) {
    const gi = Math.floor((v.pts[i]   - minx) / (maxx - minx) * GRADE);
    const gj = Math.floor((v.pts[i+1] - miny) / (maxy - miny) * GRADE);
    const c = chave(gi, gj);
    if (!celulas.has(c)) celulas.set(c, new Set());
    celulas.get(c).add(idx);
  }
});
const elVia = document.getElementById('v');
function achar(X, Y) {
  const lon = ((X - offx) / esc) / k, lat = -((Y - offy) / esc);
  const gi = Math.floor((lon - minx) / (maxx - minx) * GRADE);
  const gj = Math.floor((lat - miny) / (maxy - miny) * GRADE);
  let melhor = null, dmin = Infinity;
  for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
    const s = celulas.get(chave(gi + a, gj + b));
    if (!s) continue;
    for (const idx of s) {
      const v = vias[idx];
      for (let i = 0; i < v.pts.length; i += 2) {
        const dx = (v.pts[i] - lon) * k, dy = v.pts[i+1] - lat;
        const d = dx*dx + dy*dy;
        if (d < dmin) { dmin = d; melhor = idx; }
      }
    }
  }
  const limite = Math.pow(12 / esc, 2);
  elVia.textContent = (melhor !== null && dmin < limite)
    ? (D.nomes[melhor] || '(via sem nome)') + '  \\u00b7  ' + D.classes[vias[melhor].cls]
    : 'passe o mouse sobre uma via';
}

document.getElementById('t').textContent = D.titulo;
document.getElementById('n').textContent = D.linhas.length.toLocaleString('pt-BR') + ' trechos de via';
document.getElementById('l').innerHTML = D.classes.map((c, i) =>
  '<div class="sw" style="background:' + D.cores[i] + '"></div><div>' + c + '</div>').join('');
// reenquadrar sob demanda: tecla R ou duplo clique
function reenquadrar() { tocado = false; if (enquadrar()) desenhar(); }
addEventListener('keydown', e => { if (e.key === 'r' || e.key === 'R') reenquadrar(); });
cv.addEventListener('dblclick', reenquadrar);
addEventListener('resize', atualizar);
// o painel pode comecar oculto (largura 0); observar o body pega o momento em
// que ele ganha tamanho e enquadra ai
if (window.ResizeObserver) new ResizeObserver(atualizar).observe(document.body);
atualizar();
</script></body></html>
"""


# --------------------------------------------------------------------------- #
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--grafo", default="plano_piloto_drive")
    p.add_argument("--so-arteriais", action="store_true",
                   help="manter so a malha arterial (recomendado no DF inteiro)")
    p.add_argument("--simplificar", type=float, default=0.0,
                   help="tolerancia em metros para simplificar a curva das vias")
    p.add_argument("--sem-mapa", action="store_true")
    p.add_argument("--sem-geojson", action="store_true")
    args = p.parse_args()

    origem = SAIDA / f"{args.grafo}.graphml"
    if not origem.exists():
        sys.exit(f"Nao encontrei {origem}")

    print(f"Carregando {origem.name} ({origem.stat().st_size/1e6:.1f} MB)...")
    G = ox.io.load_graphml(origem)
    print(f"  {G.number_of_nodes():,} nos, {G.number_of_edges():,} arestas")

    nome = args.grafo
    if args.so_arteriais:
        E = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True)
             if ARTERIAIS.intersection(d["highway"] if isinstance(d["highway"], list)
                                       else [d["highway"]])]
        G = G.edge_subgraph(E).copy()
        nome += "_arteriais"
        print(f"  recorte arterial: {G.number_of_nodes():,} nos, {G.number_of_edges():,} arestas")

    _, arestas = ox.convert.graph_to_gdfs(G)
    if args.simplificar > 0:
        # simplify em graus; converte a tolerancia de metros aproximadamente
        tol = args.simplificar / 111_320
        arestas = arestas.assign(geometry=arestas.geometry.simplify(tol))
        nome += f"_s{int(args.simplificar)}"
        print(f"  geometria simplificada com tolerancia de {args.simplificar} m")

    SAIDA.mkdir(exist_ok=True)
    exportar_graphml(G, SAIDA / f"{nome}_render.graphml")
    if not args.sem_geojson:
        exportar_geojson(arestas, SAIDA / f"{nome}_arestas.geojson")
    if not args.sem_mapa:
        exportar_mapa(arestas, SAIDA / f"{nome}_mapa.html", nome.replace("_", " "))

    print(f"\nPronto. Arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
