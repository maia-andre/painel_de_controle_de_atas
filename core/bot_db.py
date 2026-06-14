"""Operações de banco compartilhadas pelos bots de raspagem (ETP/SD).

Substitui os arquivos de fila (base_etps.csv / base_sds.xlsx) e os arquivos de
checkpoint (log_*_processados.txt): a fila e o checkpoint passam a viver na
tabela `ata_documentos`.
"""
from __future__ import annotations

import getpass
import os

import pandas as pd
from sqlalchemy import text

from core.banco import engine
from core.normalizacao import extrai_codigo_secretaria, parse_decimal_br

COLS_PREVISTOS = [
    "ata_id", "numero_ata", "ano", "codigo_material", "descricao", "unidade",
    "orgao", "secretaria_codigo", "qtd_prevista", "valor_total_previsto",
    "tipo_doc", "numero_doc",
]


def headless() -> bool:
    """Modo headless (padrão True; defina BOT_HEADLESS=false para depurar)."""
    return os.environ.get("BOT_HEADLESS", "true").strip().lower() not in ("0", "false", "no")


def get_credenciais() -> tuple[str, str]:
    """Credenciais do portal via env (PORTAL_CPF/PORTAL_SENHA) ou prompt."""
    cpf = os.environ.get("PORTAL_CPF", "").strip()
    senha = os.environ.get("PORTAL_SENHA", "")
    if not cpf:
        cpf = input("Digite seu Usuário (CPF): ").strip()
    if not senha:
        senha = getpass.getpass("Digite sua Senha: ")
    return cpf, senha


def get_fila(tipo_doc: str) -> list[dict]:
    """Documentos pendentes da fila, com a ata resolvida (se houver)."""
    sql = text(
        """
        SELECT d.id, d.numero_doc, d.ano_doc, d.secretaria, d.ata_id,
               a.numero_ata, a.ano
        FROM ata_documentos d
        LEFT JOIN atas a ON a.id = d.ata_id
        WHERE d.tipo_doc = :t AND d.status = 'pendente'
        ORDER BY d.id
        """
    )
    with engine().connect() as cx:
        return [dict(r._mapping) for r in cx.execute(sql, {"t": tipo_doc})]


def marcar_status(doc_id: int, status: str) -> None:
    """Atualiza o checkpoint do documento ('processado' | 'erro')."""
    with engine().begin() as cx:
        cx.execute(
            text(
                """
                UPDATE ata_documentos
                SET status = :s,
                    processado_em = CASE WHEN :s = 'processado' THEN NOW()
                                         ELSE processado_em END
                WHERE id = :id
                """
            ),
            {"s": status, "id": doc_id},
        )


def salvar_previstos(tipo_doc: str, numero_doc: str, itens: list[dict]) -> int:
    """Regrava os previstos de um documento (DELETE + INSERT = idempotente)."""
    with engine().begin() as cx:
        cx.execute(
            text("DELETE FROM previstos WHERE tipo_doc = :t AND numero_doc = :n"),
            {"t": tipo_doc, "n": numero_doc},
        )
    if not itens:
        return 0

    df = pd.DataFrame(itens)
    df["qtd_prevista"] = parse_decimal_br(df.get("qtd_prevista", pd.Series(dtype=str)))
    df["valor_total_previsto"] = (
        parse_decimal_br(df["valor_total_previsto"])
        if "valor_total_previsto" in df.columns
        else 0
    )
    df["secretaria_codigo"] = extrai_codigo_secretaria(df.get("orgao", pd.Series(dtype=str)))
    for c in COLS_PREVISTOS:
        if c not in df.columns:
            df[c] = None
    df = df[COLS_PREVISTOS].astype(object)
    df = df.where(pd.notnull(df), None)

    df.to_sql("previstos", engine(), if_exists="append", index=False, method="multi")
    return len(df)
