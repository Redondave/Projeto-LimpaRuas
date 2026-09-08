"""
Mapeia os trechos de rodovias distritais (CÓDIGO-DO-TRECHO) da planilha do
DER/DF para coordenadas geográficas (WGS84), usando a camada geoespacial
oficial "Rodovias no Distrito Federal" publicada no ArcGIS Hub do DER/DF.

Saída: CSV com ponto inicial, final e médio de cada trecho, prontos para
alimentar chamadas à API da TomTom (que espera lat/lon em WGS84).

Requisitos:
    pip install pandas requests

Uso:
    python mapear_trechos_df.py

Ajuste as constantes na seção CONFIG antes de rodar.
"""

import re
import sys

import pandas as pd
import requests

# ----------------------------- CONFIG ------------------------------------

# Caminho do CSV de trechos (o que você já enviou)
CSV_TRECHOS = "Roads.csv"

# Item do ArcGIS Hub / ArcGIS Online com a malha rodoviária do DER/DF.
# Pode ser o ID de qualquer uma das versões (2023, 2025 etc.) — o script
# resolve a URL do FeatureServer dinamicamente a partir do item.
ARCGIS_ITEM_ID = "970d7017c83e4136a69a2622d7cbb5cb"

# Nomes de campo candidatos para o código do trecho dentro da camada do
# DER/DF. O script testa cada um e usa o primeiro que "bater" com os
# códigos do seu CSV. Ajuste/adicione candidatos se nenhum funcionar
# (rode o script uma vez, ele imprime todos os campos disponíveis).
CAMPO_CODIGO_CANDIDATOS = [
    "CODIGO", "CODIGO_TRECHO", "CO_TRECHO", "COD_TRECHO", "SNV",
    "COD_SNV", "SIGLA", "TRECHO", "VL_CODIGO", "CD_TRECHO",
]

ARQUIVO_SAIDA = "trechos_com_coordenadas.csv"
ARQUIVO_NAO_CASADOS = "trechos_sem_geometria.csv"

# ----------------------------- ETAPA 1 ------------------------------------
# Resolve a URL do FeatureServer a partir do item do ArcGIS (sem "chutar"
# a URL do servidor, que muda de organização para organização).


def resolver_feature_server(item_id: str) -> str:
    url_item = f"https://www.arcgis.com/sharing/rest/content/items/{item_id}?f=json"
    r = requests.get(url_item, timeout=30)
    r.raise_for_status()
    meta = r.json()
    if "url" not in meta or not meta["url"]:
        raise RuntimeError(
            f"O item {item_id} não expôs uma URL de serviço diretamente. "
            f"Abra {url_item} manualmente e procure o campo 'url', ou "
            f"acesse a página do dataset no Hub e copie o link 'View API Resource'."
        )
    return meta["url"].rstrip("/")


# ----------------------------- ETAPA 2 ------------------------------------
# Baixa a camada inteira, já reprojetada para WGS84 (EPSG:4326).
#
# Serviços ArcGIS variam bastante no que aceitam: alguns não suportam
# f=geojson (só o esriJSON "nativo"), outros não suportam resultOffset
# para paginação. Em vez de assumir e estourar 400, o código abaixo
# INSPECIONA a camada antes de baixar e se adapta.


def _get_json(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, timeout=60)
    if not r.ok:
        # Mostra o corpo da resposta — é aí que a ArcGIS explica o motivo
        # real do 400 (parâmetro não suportado, camada inexistente etc.)
        raise RuntimeError(
            f"HTTP {r.status_code} em {r.url}\nResposta do servidor: {r.text[:1000]}"
        )
    data = r.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"Erro da API ArcGIS em {r.url}:\n{data['error']}")
    return data


def escolher_layer_de_linhas(feature_server_url: str) -> int:
    """Encontra o layer_id de uma camada de linhas (rodovias) dentro do
    FeatureServer, em vez de assumir que é sempre o layer 0."""
    info = _get_json(f"{feature_server_url}", {"f": "json"})
    layers = info.get("layers", [])
    if not layers:
        raise RuntimeError(
            "O FeatureServer não lista nenhum layer. Verifique a URL manualmente:\n"
            f"{feature_server_url}?f=json"
        )

    print("Layers disponíveis no serviço:")
    for lyr in layers:
        print(f"  id={lyr['id']}  nome={lyr.get('name')}  "
              f"tipo_geometria={lyr.get('geometryType')}")

    candidatos = [l for l in layers if l.get("geometryType") == "esriGeometryPolyline"]
    escolhido = (candidatos or layers)[0]
    print(f"-> Usando layer id={escolhido['id']} ({escolhido.get('name')})")
    return escolhido["id"]


def baixar_camada(feature_server_url: str, layer_id: int) -> list:
    layer_url = f"{feature_server_url}/{layer_id}"
    meta = _get_json(layer_url, {"f": "json"})

    formatos = [f.strip().lower() for f in
                meta.get("supportedQueryFormats", "JSON").split(",")]
    usa_geojson = "geojson" in formatos
    max_record_count = meta.get("maxRecordCount", 1000)
    print(f"Formatos suportados: {formatos} | maxRecordCount={max_record_count}")

    query_url = f"{layer_url}/query"
    base_params = {
        "where": "1=1",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson" if usa_geojson else "json",
    }

    # Descobre se a paginação por resultOffset é suportada; senão, pagina
    # manualmente por objectId.
    suporta_paginacao = meta.get("advancedQueryCapabilities", {}).get(
        "supportsPagination", meta.get("supportsPagination", False)
    )

    features = []
    if suporta_paginacao:
        offset = 0
        while True:
            params = dict(base_params, resultRecordCount=max_record_count,
                          resultOffset=offset)
            data = _get_json(query_url, params)
            batch = data.get("features", [])
            features.extend(batch)
            if len(batch) < max_record_count:
                break
            offset += max_record_count
    else:
        # Pega todos os objectIds primeiro, depois busca em lotes por
        # objectIds explícitos (funciona mesmo sem suporte a resultOffset).
        oid_field = meta.get("objectIdField", "OBJECTID")
        ids_data = _get_json(query_url, {"where": "1=1", "returnIdsOnly": "true",
                                          "f": "json"})
        object_ids = ids_data.get("objectIds", [])
        print(f"{len(object_ids)} objectIds encontrados; buscando em lotes de "
              f"{max_record_count}...")
        for i in range(0, len(object_ids), max_record_count):
            lote = object_ids[i:i + max_record_count]
            params = dict(base_params, objectIds=",".join(map(str, lote)))
            params.pop("where", None)
            data = _get_json(query_url, params)
            features.extend(data.get("features", []))

    print(f"Baixadas {len(features)} feições da camada.")

    if usa_geojson:
        return features
    return [_esri_feature_para_geojson(f) for f in features]


def _esri_feature_para_geojson(feature: dict) -> dict:
    """Converte uma feição esriJSON (paths) para o formato geojson mínimo
    que o resto do script espera (properties + geometry.coordinates)."""
    geom = feature.get("geometry", {})
    paths = geom.get("paths")
    if paths:
        geojson_geom = {
            "type": "MultiLineString" if len(paths) > 1 else "LineString",
            "coordinates": paths if len(paths) > 1 else paths[0],
        }
    else:
        geojson_geom = None
    return {"properties": feature.get("attributes", {}), "geometry": geojson_geom}


# ----------------------------- ETAPA 3 ------------------------------------
# Descobre automaticamente qual campo da camada contém o código do trecho,
# testando os candidatos contra os códigos presentes no CSV.


def identificar_campo_codigo(geojson: dict, codigos_csv: set) -> str:
    if not geojson["features"]:
        raise RuntimeError("A camada baixada não tem feições.")

    campos_disponiveis = list(geojson["features"][0]["properties"].keys())
    print("Campos disponíveis na camada:", campos_disponiveis)

    melhor_campo, melhor_acertos = None, 0
    candidatos = CAMPO_CODIGO_CANDIDATOS + campos_disponiveis
    for campo in dict.fromkeys(candidatos):  # remove duplicados, mantém ordem
        if campo not in campos_disponiveis:
            continue
        valores = {
            str(f["properties"].get(campo, "")).strip().upper()
            for f in geojson["features"]
        }
        acertos = len(valores & codigos_csv)
        if acertos > melhor_acertos:
            melhor_campo, melhor_acertos = campo, acertos

    if melhor_campo is None or melhor_acertos == 0:
        raise RuntimeError(
            "Nenhum campo da camada bateu com os códigos do CSV. "
            "Inspecione 'campos_disponiveis' acima e ajuste "
            "CAMPO_CODIGO_CANDIDATOS, ou trate o join manualmente "
            "(ex.: casando por rodovia + ordem do trecho, e não pelo "
            "código completo)."
        )

    print(f"Campo de junção identificado: '{melhor_campo}' "
          f"({melhor_acertos}/{len(codigos_csv)} códigos casados)")
    return melhor_campo


# ----------------------------- ETAPA 4 ------------------------------------
# Extrai pontos (início, fim, meio) de cada geometria de linha em WGS84,
# sem depender de shapely — só aritmética simples sobre a lista de
# coordenadas (lon, lat) que vem no GeoJSON.


def _distancia(p1, p2):
    # distância planar em graus (aproximação suficiente para achar o
    # ponto médio por proporção de comprimento; não é a distância
    # geodésica real).
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


def pontos_da_geometria(geom_geojson: dict):
    if not geom_geojson:
        return None
    tipo = geom_geojson.get("type")
    coords = geom_geojson.get("coordinates")
    if not coords:
        return None

    if tipo == "MultiLineString":
        pontos = [pt for parte in coords for pt in parte]
    elif tipo == "LineString":
        pontos = coords
    else:
        return None

    if len(pontos) < 2:
        return None

    # comprimento acumulado ao longo da linha
    acumulado = [0.0]
    for a, b in zip(pontos, pontos[1:]):
        acumulado.append(acumulado[-1] + _distancia(a, b))
    comprimento_total = acumulado[-1]

    inicio = pontos[0]
    fim = pontos[-1]

    if comprimento_total == 0:
        meio = pontos[len(pontos) // 2]
    else:
        alvo = comprimento_total / 2
        meio = pontos[-1]
        for i in range(1, len(acumulado)):
            if acumulado[i] >= alvo:
                # interpola linearmente entre pontos[i-1] e pontos[i]
                falta = alvo - acumulado[i - 1]
                trecho = acumulado[i] - acumulado[i - 1]
                frac = 0 if trecho == 0 else falta / trecho
                x = pontos[i - 1][0] + frac * (pontos[i][0] - pontos[i - 1][0])
                y = pontos[i - 1][1] + frac * (pontos[i][1] - pontos[i - 1][1])
                meio = (x, y)
                break

    return {
        "lat_inicio": inicio[1], "lon_inicio": inicio[0],
        "lat_fim": fim[1], "lon_fim": fim[0],
        "lat_meio": meio[1], "lon_meio": meio[0],
        "extensao_geom_km": comprimento_total * 111.32,  # aproximação grosseira (graus -> km)
    }


# ----------------------------- ETAPA 5 ------------------------------------
# Parser do código SNV (ex.: 001EDF0010 -> rodovia DF-001, jurisdição
# estadual/distrital, sequencial 0010). Útil para relatórios e para casos
# em que o join direto por código completo falhar mas um join por rodovia
# ainda fizer sentido.

PADRAO_SNV = re.compile(r"^(\d{3})([A-Z])([A-Z]{2})(\d{4})$")


def parse_codigo_snv(codigo: str):
    m = PADRAO_SNV.match(codigo.strip())
    if not m:
        return None
    num_rodovia, jurisdicao, uf, sequencial = m.groups()
    prefixo = "BR" if jurisdicao == "B" else uf
    return {
        "rodovia": f"{prefixo}-{num_rodovia}",
        "jurisdicao": jurisdicao,
        "uf": uf,
        "sequencial": sequencial,
    }


# ----------------------------- MAIN ---------------------------------------


def main():
    df = pd.read_csv(CSV_TRECHOS, dtype=str)
    df["CÓDIGO-DO-TRECHO"] = df["CÓDIGO-DO-TRECHO"].str.strip().str.upper()

    # O CSV tem linhas duplicadas por código (aparentam ser artefatos de
    # extração/OCR, com pequenas variações de espaçamento no texto das
    # colunas de início/fim). Mantém, para cada código, a linha "mais
    # limpa" (menor quantidade de caracteres nas colunas de texto, que
    # tende a ser a versão sem espaços espúrios inseridos no meio das
    # palavras).
    n_antes = len(df)
    df["_tam_texto"] = (
        df["TRECHO-INÍCIO"].str.len().fillna(0)
        + df["TRECHO-FINAL"].str.len().fillna(0)
    )
    df = (
        df.sort_values("_tam_texto")
        .drop_duplicates("CÓDIGO-DO-TRECHO", keep="first")
        .drop(columns="_tam_texto")
        .sort_index()
    )
    if n_antes != len(df):
        print(f"Removidas {n_antes - len(df)} linhas duplicadas por código "
              f"(mantida a versão mais limpa de cada trecho).")

    codigos_csv = set(df["CÓDIGO-DO-TRECHO"])
    print(f"{len(df)} trechos após deduplicação ({len(codigos_csv)} códigos únicos).")

    print("Resolvendo URL do FeatureServer...")
    feature_server_url = resolver_feature_server(ARCGIS_ITEM_ID)
    print("FeatureServer:", feature_server_url)

    layer_id = escolher_layer_de_linhas(feature_server_url)

    print("Baixando camada de rodovias do DER/DF...")
    features = baixar_camada(feature_server_url, layer_id)
    geojson = {"type": "FeatureCollection", "features": features}

    campo_codigo = identificar_campo_codigo(geojson, codigos_csv)

    # Indexa as feições pelo código, guardando também a geometria
    indice = {}
    for feat in geojson["features"]:
        codigo = str(feat["properties"].get(campo_codigo, "")).strip().upper()
        if codigo:
            indice[codigo] = feat

    linhas_saida = []
    linhas_sem_match = []

    for _, row in df.iterrows():
        codigo = row["CÓDIGO-DO-TRECHO"]
        feat = indice.get(codigo)
        base = row.to_dict()
        info_snv = parse_codigo_snv(codigo)
        if info_snv:
            base.update({f"snv_{k}": v for k, v in info_snv.items()})

        if feat is None:
            linhas_sem_match.append(base)
            continue

        pontos = pontos_da_geometria(feat["geometry"])
        if pontos is None:
            linhas_sem_match.append(base)
            continue

        base.update(pontos)
        linhas_saida.append(base)

    pd.DataFrame(linhas_saida).to_csv(ARQUIVO_SAIDA, index=False)
    pd.DataFrame(linhas_sem_match).to_csv(ARQUIVO_NAO_CASADOS, index=False)

    print(f"\n{len(linhas_saida)} trechos com coordenadas -> {ARQUIVO_SAIDA}")
    print(f"{len(linhas_sem_match)} trechos sem geometria correspondente -> "
          f"{ARQUIVO_NAO_CASADOS}")


if __name__ == "__main__":
    sys.exit(main())