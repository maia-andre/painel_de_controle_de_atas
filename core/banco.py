"""Acesso ao PostgreSQL — engine puro (sem Streamlit).

Fonte única do engine para os bots, o script de carga e o app (via db.py).
Lê DATABASE_URL do ambiente (.env).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

RAIZ = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def engine():
    load_dotenv(RAIZ / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL não definida. Copie .env.example para .env e preencha."
        )
    return create_engine(url, pool_pre_ping=True)
