"""CRUD administrativo (telas de Administração).

Operações de escrita sobre secretarias, atas e a fila de documentos
(ata_documentos). Usa o engine único de core.banco.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from core.banco import engine


def _read(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine().connect() as cx:
        return pd.read_sql(text(sql), cx, params=params)


# ---------------------------------------------------------------------------
# Secretarias
# ---------------------------------------------------------------------------
def listar_secretarias() -> pd.DataFrame:
    return _read("SELECT codigo, sigla, nome FROM secretarias ORDER BY codigo")


def salvar_secretaria(codigo: int, sigla: str, nome: str | None) -> None:
    with engine().begin() as cx:
        cx.execute(
            text(
                """
                INSERT INTO secretarias (codigo, sigla, nome)
                VALUES (:c, :s, :n)
                ON CONFLICT (codigo) DO UPDATE SET
                    sigla = EXCLUDED.sigla, nome = EXCLUDED.nome
                """
            ),
            {"c": int(codigo), "s": sigla, "n": nome or None},
        )


def deletar_secretaria(codigo: int) -> None:
    with engine().begin() as cx:
        cx.execute(text("DELETE FROM secretarias WHERE codigo = :c"), {"c": int(codigo)})


# ---------------------------------------------------------------------------
# Atas
# ---------------------------------------------------------------------------
def listar_atas() -> pd.DataFrame:
    return _read(
        """
        SELECT id, numero_ata, ano, objeto, vigencia_inicio, vigencia_fim, prorrogada
        FROM atas
        ORDER BY ano DESC NULLS LAST, numero_ata
        """
    )


def upsert_ata(id_, numero_ata, ano, objeto, vigencia_inicio, vigencia_fim, prorrogada) -> None:
    p = {
        "id": id_, "n": numero_ata, "a": ano or None, "o": objeto or None,
        "vi": vigencia_inicio, "vf": vigencia_fim, "p": bool(prorrogada),
    }
    with engine().begin() as cx:
        if id_ is None:
            cx.execute(
                text(
                    """
                    INSERT INTO atas (numero_ata, ano, objeto, vigencia_inicio,
                                      vigencia_fim, prorrogada)
                    VALUES (:n, :a, :o, :vi, :vf, :p)
                    ON CONFLICT (numero_ata, ano) DO UPDATE SET
                        objeto = EXCLUDED.objeto,
                        vigencia_inicio = EXCLUDED.vigencia_inicio,
                        vigencia_fim = EXCLUDED.vigencia_fim,
                        prorrogada = EXCLUDED.prorrogada
                    """
                ),
                p,
            )
        else:
            cx.execute(
                text(
                    """
                    UPDATE atas SET numero_ata = :n, ano = :a, objeto = :o,
                        vigencia_inicio = :vi, vigencia_fim = :vf, prorrogada = :p
                    WHERE id = :id
                    """
                ),
                p,
            )


def deletar_ata(id_: int) -> None:
    with engine().begin() as cx:
        cx.execute(text("DELETE FROM atas WHERE id = :id"), {"id": int(id_)})


# ---------------------------------------------------------------------------
# Documentos (fila dos bots)
# ---------------------------------------------------------------------------
def listar_documentos(ata_id: int) -> pd.DataFrame:
    return _read(
        """
        SELECT id, tipo_doc, numero_doc, ano_doc, secretaria, status, processado_em
        FROM ata_documentos
        WHERE ata_id = :a
        ORDER BY tipo_doc, numero_doc
        """,
        {"a": int(ata_id)},
    )


def adicionar_documento(ata_id, tipo_doc, numero_doc, ano_doc, secretaria) -> None:
    """Enfileira (ou re-vincula) um documento, deixando-o pendente para o bot."""
    with engine().begin() as cx:
        cx.execute(
            text(
                """
                INSERT INTO ata_documentos (ata_id, tipo_doc, numero_doc, ano_doc,
                                            secretaria, status)
                VALUES (:a, :t, :n, :ano, :sec, 'pendente')
                ON CONFLICT (tipo_doc, numero_doc, ano_doc) DO UPDATE SET
                    ata_id = EXCLUDED.ata_id,
                    secretaria = EXCLUDED.secretaria,
                    status = 'pendente',
                    processado_em = NULL
                """
            ),
            {"a": int(ata_id), "t": tipo_doc, "n": numero_doc,
             "ano": ano_doc or "", "sec": secretaria or None},
        )


def reenfileirar_documento(id_: int) -> None:
    with engine().begin() as cx:
        cx.execute(
            text(
                "UPDATE ata_documentos SET status = 'pendente', processado_em = NULL "
                "WHERE id = :id"
            ),
            {"id": int(id_)},
        )


def deletar_documento(id_: int) -> None:
    with engine().begin() as cx:
        cx.execute(text("DELETE FROM ata_documentos WHERE id = :id"), {"id": int(id_)})
