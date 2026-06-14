"""Normalização única dos dados do Painel de Controle de Atas.

Fonte de verdade compartilhada entre o script de carga (`scripts/load_csv_to_db.py`)
e os bots (`bot_etps.py` / `bot_sd.py`). Centraliza aqui o que antes vivia espalhado
e inconsistente dentro de `app.py:carregar_dados()`.

Decisões travadas no planejamento da migração:
  * Chave de ata: zeros à esquerda removidos (ata "012" == "12").
  * Números em padrão BR: ponto é separador de milhar, vírgula é decimal.
    Regra única (remover '.', trocar ',' por '.') — corrige o bug antigo em que
    quantidades com milhar (ex.: "1.500") eram lidas como 1.5.
  * Datas: dia primeiro (dd/mm/aaaa).
  * Cancelado: prefixo 'CANCELAD' (cobre CANCELADA/CANCELADO sem depender da grafia).
"""
from __future__ import annotations

import re
import pandas as pd


def normaliza_chave_ata(serie: pd.Series) -> pd.Series:
    """Limpa e remove zeros à esquerda da chave de ata (número ou ano)."""
    return (
        serie.fillna("").astype(str).str.strip().str.replace(r"^0+", "", regex=True)
    )


def parse_decimal_br(serie: pd.Series) -> pd.Series:
    """Converte texto em número, assumindo formatação BR (1.234,56 -> 1234.56).

    Regra única para quantidades e valores: remove o separador de milhar ('.')
    e troca o decimal (',') por '.'. Valores não-parseáveis viram 0.
    """
    limpo = (
        serie.fillna("0")
        .astype(str)
        .str.strip()
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(limpo, errors="coerce").fillna(0)


def parse_data_br(serie: pd.Series) -> pd.Series:
    """Converte texto em data com dia primeiro (dd/mm/aaaa)."""
    return pd.to_datetime(serie, dayfirst=True, errors="coerce")


def is_cancelado(valor) -> bool:
    """True se o status indica cancelamento (prefixo 'CANCELAD')."""
    if valor is None:
        return False
    return str(valor).strip().upper().startswith("CANCELAD")


def extrai_codigo_secretaria(serie: pd.Series) -> pd.Series:
    """Extrai o código numérico inicial de 'Secr. RC' (ex.: '60 - SS' -> 60)."""
    return pd.to_numeric(
        serie.fillna("").astype(str).str.extract(r"(\d+)")[0], errors="coerce"
    ).astype("Int64")


def renomeia_por_substring(df: pd.DataFrame, regras: list[tuple]) -> pd.DataFrame:
    """Renomeia colunas por casamento de substring, replicando a lógica do app.

    `regras` é uma lista de (predicado, nome_canonico), onde predicado(coluna)
    retorna bool. A primeira regra que casa vence. Mantém o comportamento
    tolerante a cabeçalhos sujos das planilhas de origem.
    """
    df = df.copy()
    df.columns = df.columns.str.strip()
    mapa = {}
    for col in df.columns:
        for pred, canonico in regras:
            if pred(col):
                mapa[col] = canonico
                break
    return df.rename(columns=mapa)
