"""Carga inicial dos CSV/XLSX da raiz para o PostgreSQL.

Roda LOCALMENTE, onde os arquivos de produção existem (eles estão no .gitignore
e não vivem no repositório). Lê DATABASE_URL do ambiente (.env).

Uso:
    python scripts/load_csv_to_db.py --profile      # só diagnostica os arquivos
    python scripts/load_csv_to_db.py --schema       # aplica db/schema.sql
    python scripts/load_csv_to_db.py                # carrega tudo + valida
    python scripts/load_csv_to_db.py --schema       # (idempotente; pode repetir)

A carga é idempotente: dimensões (atas, ata_documentos, secretarias) via UPSERT;
fatos (previstos, consumo_rcaf) via TRUNCATE + reinserção.

NÃO altera regras de negócio. Apenas move o dado para o banco, já normalizado
(números/datas/chave de ata) pela camada única em core/normalizacao.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Permite rodar como script solto (python scripts/load_csv_to_db.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.banco import engine  # noqa: E402
from core.normalizacao import (  # noqa: E402
    extrai_codigo_secretaria,
    is_cancelado,
    normaliza_chave_ata,
    parse_data_br,
    parse_decimal_br,
    renomeia_por_substring,
)

RAIZ = Path(__file__).resolve().parent.parent
ARQ_SDS = RAIZ / "base_sds.xlsx"
ARQ_PREVISTOS = RAIZ / "previstos_dashboard.csv"
ARQ_RCAF = RAIZ / "base_rcaf.csv"
SCHEMA_SQL = RAIZ / "db" / "schema.sql"


# ----------------------------------------------------------------------------
# Leitura tolerante (mesmas heurísticas do app.py)
# ----------------------------------------------------------------------------
def _ler_csv(caminho: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(caminho, sep=";", dtype=str, low_memory=False)
    except UnicodeDecodeError:
        return pd.read_csv(caminho, sep=";", dtype=str, encoding="latin-1", low_memory=False)


def _eng():
    try:
        return engine()
    except RuntimeError as e:
        sys.exit(f"ERRO: {e}")


# ----------------------------------------------------------------------------
# Mapeamentos de colunas (espelham o renomear fuzzy do app.py)
# ----------------------------------------------------------------------------
REGRAS_SDS = [
    (lambda c: "Ata" in c and "N" in c and "Prorr" not in c and "Ano" not in c, "numero_ata"),
    (lambda c: "Ano" in c and "Ata" in c, "ano"),
    (lambda c: "Assinatura" in c, "assinatura"),
    (lambda c: "Prorr" in c, "prorrogada"),
    (lambda c: "Vig" in c, "vigencia"),
    (lambda c: "Objeto" in c, "objeto"),
]

REGRAS_PREVISTOS = [
    (lambda c: "N" in c and "Ata" in c, "numero_ata"),
    (lambda c: "Ano" in c and "Ata" in c, "ano"),
    (lambda c: "Qtde" in c and "Prev" in c, "qtd_prevista"),
    (lambda c: "Valor Total" in c and "Prev" in c, "valor_total_previsto"),
    (lambda c: "Secr" in c and "RC" in c, "orgao"),
    (lambda c: "Material" in c and "RC" in c and "Descri" not in c, "codigo_material"),
    (lambda c: "Descri" in c and "Material" in c and "RC" in c, "descricao"),
    (lambda c: "Unidade" in c and "Medida" in c, "unidade"),
    (lambda c: "Num" in c and "DOC" in c, "numero_doc"),
    (lambda c: "Num" in c and "ETP" in c, "numero_doc"),
]

REGRAS_RCAF = [
    (lambda c: c == "Status RC", "status_rc"),
    (lambda c: c == "Status AF", "status_af"),
    (lambda c: "Val.Unit" in c and "RC" in c, "valor_unitario"),
    (lambda c: "Val.Total" in c and "RC" in c, "valor_total"),
    (lambda c: "Qtd" in c and "RC" in c, "quantidade"),
    (lambda c: "Data" in c and "RC" in c, "data_rc"),
    (lambda c: "Descri" in c and "Material" in c and "RC" in c, "descricao"),
    (lambda c: "Material" in c and "RC" in c and "Descri" not in c, "codigo_material"),
    (lambda c: "Secr" in c and "RC" in c, "orgao"),
    (lambda c: c == "RC", "numero_rc"),
    (lambda c: c == "AF", "numero_af"),
    (lambda c: "N" in c and "Ata" in c, "numero_ata"),
    (lambda c: "Ano" in c and "Ata" in c, "ano"),
]


# ----------------------------------------------------------------------------
# Atas + documentos (origem: base_sds.xlsx)
# ----------------------------------------------------------------------------
def carregar_atas(engine) -> dict:
    """Upsert das atas e dos vínculos de SD. Retorna {(numero, ano): ata_id}."""
    if not ARQ_SDS.exists():
        print(f"[!] {ARQ_SDS.name} não encontrado — pulando atas/documentos.")
        return {}

    df = pd.read_excel(ARQ_SDS, dtype=str)
    df = renomeia_por_substring(df, REGRAS_SDS)
    df["numero_ata"] = normaliza_chave_ata(df.get("numero_ata", pd.Series(dtype=str)))
    df["ano"] = normaliza_chave_ata(df.get("ano", pd.Series(dtype=str)))

    meta = df[df["numero_ata"] != ""].groupby(["numero_ata", "ano"], as_index=False).first()

    with engine.begin() as cx:
        for _, r in meta.iterrows():
            cx.execute(
                text(
                    """
                    INSERT INTO atas (numero_ata, ano, objeto, vigencia_inicio,
                                      vigencia_fim, prorrogada)
                    VALUES (:n, :a, :obj, :vi, :vf, :prorr)
                    ON CONFLICT (numero_ata, ano) DO UPDATE SET
                        objeto = EXCLUDED.objeto,
                        vigencia_inicio = EXCLUDED.vigencia_inicio,
                        vigencia_fim = EXCLUDED.vigencia_fim,
                        prorrogada = EXCLUDED.prorrogada
                    """
                ),
                {
                    "n": r["numero_ata"],
                    "a": r.get("ano") or None,
                    "obj": r.get("objeto") or None,
                    "vi": _data_ou_nulo(r.get("assinatura")),
                    "vf": _data_ou_nulo(r.get("vigencia")),
                    "prorr": str(r.get("prorrogada", "")).strip().upper() == "S",
                },
            )

        mapa = {
            (n, a): i
            for i, n, a in cx.execute(text("SELECT id, numero_ata, ano FROM atas")).all()
        }

        # Vínculos ata <-> SD (colunas "Num SD x" / "Ano SD x")
        cols_num = [c for c in df.columns if c.startswith("Num SD")]
        cols_ano = [c for c in df.columns if c.startswith("Ano SD")]
        vinc = 0
        for _, r in df.iterrows():
            ata_id = mapa.get((r["numero_ata"], r["ano"]))
            for cn, ca in zip(cols_num, cols_ano):
                num_sd = str(r.get(cn, "")).strip()
                if not num_sd or num_sd.lower() == "nan":
                    continue
                ano_sd = str(r.get(ca, "")).strip()
                ano_sd = "" if ano_sd.lower() == "nan" else ano_sd
                cx.execute(
                    text(
                        """
                        INSERT INTO ata_documentos (ata_id, tipo_doc, numero_doc, ano_doc)
                        VALUES (:ata, 'SD', :num, :ano)
                        ON CONFLICT (tipo_doc, numero_doc, ano_doc) DO UPDATE SET
                            ata_id = EXCLUDED.ata_id
                        """
                    ),
                    {"ata": ata_id, "num": num_sd, "ano": ano_sd or None},
                )
                vinc += 1

    print(f"[+] Atas: {len(meta)} | vínculos de SD: {vinc}")
    return mapa


def _data_ou_nulo(v):
    d = parse_data_br(pd.Series([v])).iloc[0]
    return None if pd.isna(d) else d.date()


# ----------------------------------------------------------------------------
# Previstos (origem: previstos_dashboard.csv)
# ----------------------------------------------------------------------------
def carregar_previstos(engine, mapa_atas: dict) -> pd.DataFrame:
    if not ARQ_PREVISTOS.exists():
        print(f"[!] {ARQ_PREVISTOS.name} não encontrado — pulando previstos.")
        return pd.DataFrame()

    df = renomeia_por_substring(_ler_csv(ARQ_PREVISTOS), REGRAS_PREVISTOS)
    df["numero_ata"] = normaliza_chave_ata(df.get("numero_ata", pd.Series(dtype=str)))
    df["ano"] = normaliza_chave_ata(df.get("ano", pd.Series(dtype=str)))
    df["qtd_prevista"] = parse_decimal_br(df.get("qtd_prevista", pd.Series(dtype=str)))
    df["valor_total_previsto"] = parse_decimal_br(
        df.get("valor_total_previsto", pd.Series(dtype=str))
    )
    df["secretaria_codigo"] = extrai_codigo_secretaria(df.get("orgao", pd.Series(dtype=str)))
    # Origem inferida na carga histórica; daqui pra frente o bot grava tipo_doc.
    df["tipo_doc"] = df["valor_total_previsto"].apply(lambda v: "SD" if v > 0 else "ETP")
    df["ata_id"] = df.apply(lambda r: mapa_atas.get((r["numero_ata"], r["ano"])), axis=1)

    cols = [
        "ata_id", "numero_ata", "ano", "codigo_material", "descricao", "unidade",
        "orgao", "secretaria_codigo", "qtd_prevista", "valor_total_previsto",
        "tipo_doc", "numero_doc",
    ]
    df = _garante_colunas(df, cols)
    _truncar_e_inserir(engine, "previstos", df[cols])
    print(f"[+] Previstos: {len(df)} linhas")
    return df


# ----------------------------------------------------------------------------
# Consumo RCAF (origem: base_rcaf.csv)
# ----------------------------------------------------------------------------
def carregar_consumo(engine, mapa_atas: dict) -> pd.DataFrame:
    if not ARQ_RCAF.exists():
        print(f"[!] {ARQ_RCAF.name} não encontrado — pulando consumo.")
        return pd.DataFrame()

    df = renomeia_por_substring(_ler_csv(ARQ_RCAF), REGRAS_RCAF)
    df["numero_ata"] = normaliza_chave_ata(df.get("numero_ata", pd.Series(dtype=str)))
    df["ano"] = normaliza_chave_ata(df.get("ano", pd.Series(dtype=str)))
    df["quantidade"] = parse_decimal_br(df.get("quantidade", pd.Series(dtype=str)))
    df["valor_unitario"] = parse_decimal_br(df.get("valor_unitario", pd.Series(dtype=str)))
    df["valor_total"] = parse_decimal_br(df.get("valor_total", pd.Series(dtype=str)))
    df["data_rc"] = parse_data_br(df.get("data_rc", pd.Series(dtype=str))).dt.date
    df["secretaria_codigo"] = extrai_codigo_secretaria(df.get("orgao", pd.Series(dtype=str)))
    df["ata_id"] = df.apply(lambda r: mapa_atas.get((r["numero_ata"], r["ano"])), axis=1)

    cols = [
        "ata_id", "numero_ata", "ano", "codigo_material", "descricao", "orgao",
        "secretaria_codigo", "numero_rc", "data_rc", "status_rc", "numero_af",
        "status_af", "quantidade", "valor_unitario", "valor_total",
    ]
    df = _garante_colunas(df, cols)
    _truncar_e_inserir(engine, "consumo_rcaf", df[cols])
    print(f"[+] Consumo RCAF: {len(df)} linhas")
    return df


# ----------------------------------------------------------------------------
# Helpers de escrita
# ----------------------------------------------------------------------------
def _garante_colunas(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df


def _truncar_e_inserir(eng, tabela: str, df: pd.DataFrame) -> None:
    with eng.begin() as cx:
        cx.execute(text(f"TRUNCATE {tabela} RESTART IDENTITY CASCADE"))
    df = df.astype(object).where(pd.notnull(df), None)
    df.to_sql(
        tabela, eng, if_exists="append", index=False, chunksize=5000, method="multi"
    )


# ----------------------------------------------------------------------------
# Profiling e validação
# ----------------------------------------------------------------------------
def profile() -> None:
    """Diagnostica os arquivos de origem — não toca no banco."""
    print("=== PROFILING DOS ARQUIVOS DE ORIGEM ===")
    if ARQ_RCAF.exists():
        df = renomeia_por_substring(_ler_csv(ARQ_RCAF), REGRAS_RCAF)
        print(f"\n[base_rcaf.csv] {len(df)} linhas")
        for col in ("status_rc", "status_af"):
            if col in df.columns:
                print(f"  valores distintos de {col}: {sorted(df[col].dropna().unique())}")
        if "status_rc" in df and "status_af" in df:
            canc_rc = df["status_rc"].apply(is_cancelado).sum()
            canc_af = df["status_af"].apply(is_cancelado).sum()
            print(f"  linhas com RC cancelada: {canc_rc} | AF cancelada: {canc_af}")
    if ARQ_PREVISTOS.exists():
        df = renomeia_por_substring(_ler_csv(ARQ_PREVISTOS), REGRAS_PREVISTOS)
        print(f"\n[previstos_dashboard.csv] {len(df)} linhas")
        if "unidade" in df:
            print(f"  itens SV: {(df['unidade'].str.strip().str.upper() == 'SV').sum()}")
        if "numero_ata" in df:
            sem_ata = (normaliza_chave_ata(df['numero_ata']) == '').sum()
            print(f"  linhas sem nº de ata (prováveis ETP): {sem_ata}")


def validar(engine, df_prev: pd.DataFrame, df_cons: pd.DataFrame) -> None:
    print("\n=== VALIDAÇÃO (arquivo vs banco) ===")
    with engine.connect() as cx:
        for tab, df, soma_col in (
            ("previstos", df_prev, "qtd_prevista"),
            ("consumo_rcaf", df_cons, "valor_total"),
        ):
            if df.empty:
                continue
            n_db = cx.execute(text(f"SELECT count(*) FROM {tab}")).scalar()
            s_db = cx.execute(text(f"SELECT COALESCE(sum({soma_col}),0) FROM {tab}")).scalar()
            ok_n = "OK" if n_db == len(df) else "DIVERGE"
            ok_s = "OK" if abs(float(s_db) - df[soma_col].sum()) < 0.01 else "DIVERGE"
            print(f"  {tab}: linhas arquivo={len(df)} banco={n_db} [{ok_n}] | "
                  f"sum({soma_col}) arquivo={df[soma_col].sum():.2f} banco={float(s_db):.2f} [{ok_s}]")


def aplicar_schema(engine) -> None:
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    with engine.begin() as cx:
        cx.execute(text(sql))
    print(f"[+] Schema aplicado de {SCHEMA_SQL}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Carga inicial CSV/XLSX -> PostgreSQL")
    ap.add_argument("--profile", action="store_true", help="só diagnostica os arquivos")
    ap.add_argument("--schema", action="store_true", help="aplica db/schema.sql antes da carga")
    args = ap.parse_args()

    if args.profile:
        profile()
        return

    engine = _eng()
    if args.schema:
        aplicar_schema(engine)

    mapa = carregar_atas(engine)
    df_prev = carregar_previstos(engine, mapa)
    df_cons = carregar_consumo(engine, mapa)
    validar(engine, df_prev, df_cons)
    print("\n=== CARGA CONCLUÍDA ===")


if __name__ == "__main__":
    main()
