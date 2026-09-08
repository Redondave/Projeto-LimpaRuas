"""
Para cada trecho em trechos_com_coordenadas.csv (gerado por
mapear_trechos_df.py), chama a API Flow Segment Data da TomTom com o ponto
médio do trecho e salva as informações de tráfego retornadas.

Roda em uma única execução: itera pelo CSV, respeita o rate limit da
TomTom, salva progressivamente em JSON Lines (para não perder trabalho se
o processo cair no meio) e, ao final, consolida tudo em um único CSV.

Requisitos:
    pip install pandas requests

Uso:
    export TOMTOM_API_KEY="sua_chave_aqui"
    python chamar_tomtom_flow.py

Se o script for interrompido, rode de novo: ele pula os trechos que já
tiveram resposta salva no arquivo .jsonl (checkpoint).
"""

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ----------------------------- CONFIG ------------------------------------

CSV_ENTRADA = "trechos_com_coordenadas.csv"

# Qual ponto do trecho usar na chamada: "meio", "inicio" ou "fim".
CAMPO_PONTO = "meio"

# Nível de zoom da Flow Segment Data (afeta a precisão do "encaixe" no
# fragmento de via mais próximo). 10 é um valor razoável para vias
# urbanas/rodovias; ajuste conforme a documentação da TomTom se os
# resultados não corresponderem ao trecho esperado.
ZOOM = 10

API_KEY = os.environ.get("TOMTOM_API_KEY")
BASE_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/{zoom}/json"

# Rate limit do plano padrão da TomTom é 5 req/s — uso 4/s de margem de
# segurança. Ajuste se seu contrato tiver um QPS diferente.
REQS_POR_SEGUNDO = 4
INTERVALO = 1.0 / REQS_POR_SEGUNDO

MAX_TENTATIVAS = 4

ARQUIVO_CHECKPOINT = "tomtom_flow_resultados.jsonl"   # 1 JSON por linha, salvo incrementalmente
ARQUIVO_FINAL = "tomtom_flow_consolidado.csv"          # tabela final consolidada

# ---------------------------------------------------------------------------


def carregar_ja_processados(path: str) -> set:
    """Lê o checkpoint existente (se houver) e devolve o conjunto de
    códigos de trecho já resolvidos, para retomar de onde parou."""
    processados = set()
    if not Path(path).exists():
        return processados
    with open(path, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
                processados.add(registro["codigo_trecho"])
            except (json.JSONDecodeError, KeyError):
                continue
    return processados


def chamar_flow_segment(session: requests.Session, lat: float, lon: float) -> dict:
    url = BASE_URL.format(zoom=ZOOM)
    params = {"key": API_KEY, "point": f"{lat},{lon}"}

    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        r = session.get(url, params=params, timeout=20)

        if r.status_code == 200:
            return {"sucesso": True, "dados": r.json()}

        if r.status_code == 429:
            # respeita Retry-After se vier, senão usa backoff exponencial
            espera = float(r.headers.get("Retry-After", 2 ** tentativa))
            print(f"  429 (rate limit) — aguardando {espera:.1f}s "
                  f"(tentativa {tentativa}/{MAX_TENTATIVAS})")
            time.sleep(espera)
            ultimo_erro = f"429: {r.text[:300]}"
            continue

        if r.status_code >= 500:
            espera = 2 ** tentativa
            print(f"  {r.status_code} do servidor — aguardando {espera}s "
                  f"(tentativa {tentativa}/{MAX_TENTATIVAS})")
            time.sleep(espera)
            ultimo_erro = f"{r.status_code}: {r.text[:300]}"
            continue

        # 4xx que não é rate limit (ex.: 400 por ponto inválido) — não
        # adianta tentar de novo com os mesmos parâmetros.
        return {"sucesso": False, "erro": f"{r.status_code}: {r.text[:300]}"}

    return {"sucesso": False, "erro": f"Esgotadas as tentativas. Último erro: {ultimo_erro}"}


def main():
    if not API_KEY:
        sys.exit(
            "Defina a variável de ambiente TOMTOM_API_KEY antes de rodar.\n"
            "Ex.: export TOMTOM_API_KEY='sua_chave_aqui'"
        )

    df = pd.read_csv(CSV_ENTRADA, dtype={"CÓDIGO-DO-TRECHO": str})
    col_lat = f"lat_{CAMPO_PONTO}"
    col_lon = f"lon_{CAMPO_PONTO}"
    if col_lat not in df.columns or col_lon not in df.columns:
        sys.exit(f"Colunas '{col_lat}'/'{col_lon}' não encontradas em {CSV_ENTRADA}. "
                  f"Colunas disponíveis: {list(df.columns)}")

    ja_processados = carregar_ja_processados(ARQUIVO_CHECKPOINT)
    if ja_processados:
        print(f"Retomando: {len(ja_processados)} trechos já resolvidos no checkpoint.")

    pendentes = df[~df["CÓDIGO-DO-TRECHO"].isin(ja_processados)]
    print(f"{len(pendentes)} trechos a consultar de {len(df)} no total.")

    session = requests.Session()
    with open(ARQUIVO_CHECKPOINT, "a", encoding="utf-8") as saida:
        for i, (_, row) in enumerate(pendentes.iterrows(), start=1):
            codigo = row["CÓDIGO-DO-TRECHO"]
            lat, lon = row[col_lat], row[col_lon]

            if pd.isna(lat) or pd.isna(lon):
                registro = {"codigo_trecho": codigo, "sucesso": False,
                            "erro": "sem coordenada disponível"}
            else:
                resultado = chamar_flow_segment(session, lat, lon)
                registro = {"codigo_trecho": codigo, "lat": lat, "lon": lon, **resultado}

            saida.write(json.dumps(registro, ensure_ascii=False) + "\n")
            saida.flush()  # garante que nada se perde se o processo cair

            status = "ok" if registro.get("sucesso") else f"falhou ({registro.get('erro')})"
            print(f"[{i}/{len(pendentes)}] {codigo}: {status}")

            time.sleep(INTERVALO)

    consolidar(df, ARQUIVO_CHECKPOINT, ARQUIVO_FINAL)


def consolidar(df_trechos: pd.DataFrame, path_checkpoint: str, path_final: str):
    """Junta o CSV original com as respostas da TomTom (uma linha por
    trecho) em uma única tabela final."""
    registros = {}
    with open(path_checkpoint, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            reg = json.loads(linha)
            registros[reg["codigo_trecho"]] = reg  # mantém a última ocorrência

    linhas = []
    for _, row in df_trechos.iterrows():
        codigo = row["CÓDIGO-DO-TRECHO"]
        reg = registros.get(codigo, {})
        base = row.to_dict()
        base["tomtom_sucesso"] = reg.get("sucesso")
        if reg.get("sucesso"):
            fsd = reg.get("dados", {}).get("flowSegmentData", {})
            base.update({
                "tomtom_currentSpeed": fsd.get("currentSpeed"),
                "tomtom_freeFlowSpeed": fsd.get("freeFlowSpeed"),
                "tomtom_currentTravelTime": fsd.get("currentTravelTime"),
                "tomtom_freeFlowTravelTime": fsd.get("freeFlowTravelTime"),
                "tomtom_confidence": fsd.get("confidence"),
                "tomtom_roadClosure": fsd.get("roadClosure"),
            })
        else:
            base["tomtom_erro"] = reg.get("erro")
        linhas.append(base)

    pd.DataFrame(linhas).to_csv(path_final, index=False)
    n_ok = sum(1 for l in linhas if l.get("tomtom_sucesso"))
    print(f"\n{n_ok}/{len(linhas)} trechos com dados de tráfego -> {path_final}")


if __name__ == "__main__":
    main()