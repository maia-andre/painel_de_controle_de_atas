"""Camada de acesso a dados — PostgreSQL.

Substitui a leitura de CSV/XLSX da raiz. Lê DATABASE_URL do ambiente (.env).
O engine é cacheado pelo Streamlit (pool reutilizado entre reruns).
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


@st.cache_resource
def get_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL não definida. Copie .env.example para .env e preencha."
        )
    return create_engine(url, pool_pre_ping=True)


def get_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Executa SQL e devolve um DataFrame."""
    return pd.read_sql(text(sql), get_engine(), params=params)
