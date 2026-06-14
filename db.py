"""Camada de acesso a dados usada pelo app Streamlit.

Reaproveita o engine único de core.banco. Substitui a leitura de CSV/XLSX.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from core.banco import engine


def get_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Executa SQL e devolve um DataFrame."""
    return pd.read_sql(text(sql), engine(), params=params)
