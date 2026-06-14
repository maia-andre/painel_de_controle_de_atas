import pandas as pd
import streamlit as st

from core.admin import deletar_secretaria, listar_secretarias, salvar_secretaria

st.title("🏛️ Secretarias")
st.caption(
    "Cadastro das secretarias. O **código** é a chave usada para vincular o "
    "consumo (RCAF) e o previsto às secretarias no painel."
)

try:
    orig = listar_secretarias()
except Exception as e:
    st.error(f"⚠️ Erro ao acessar o banco (DATABASE_URL). Detalhe: {e}")
    st.stop()

edit = st.data_editor(
    orig,
    num_rows="dynamic",
    width="stretch",
    key="sec_editor",
    column_config={
        "codigo": st.column_config.NumberColumn("Código", min_value=1, step=1, required=True),
        "sigla": st.column_config.TextColumn("Sigla", required=True),
        "nome": st.column_config.TextColumn("Nome", width="large"),
    },
)

if st.button("💾 Salvar alterações", type="primary"):
    erros = []
    codigos_editados = set()
    for _, r in edit.iterrows():
        if pd.isna(r["codigo"]) or not str(r.get("sigla") or "").strip():
            continue
        codigos_editados.add(int(r["codigo"]))
        nome = str(r["nome"]).strip() if pd.notna(r.get("nome")) else None
        salvar_secretaria(int(r["codigo"]), str(r["sigla"]).strip(), nome)

    # Remover as que saíram da tabela (protegido por FK: secretaria em uso não é apagada)
    for codigo in set(orig["codigo"].tolist()) - codigos_editados:
        try:
            deletar_secretaria(int(codigo))
        except Exception:
            erros.append(
                f"Secretaria {codigo} não pôde ser removida (há consumo/previsto vinculado)."
            )

    if erros:
        for msg in erros:
            st.warning(msg)
    else:
        st.success("Secretarias atualizadas.")
    st.rerun()
