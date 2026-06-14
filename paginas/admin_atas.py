import pandas as pd
import streamlit as st

from core.admin import (
    adicionar_documento,
    deletar_ata,
    deletar_documento,
    listar_atas,
    listar_documentos,
    reenfileirar_documento,
    upsert_ata,
)

st.title("📋 Atas e Documentos")


def _str_ou_nulo(v):
    s = str(v).strip() if pd.notna(v) else ""
    return s or None


def _data_ou_nulo(v):
    return None if pd.isna(v) else v


try:
    atas = listar_atas()
except Exception as e:
    st.error(f"⚠️ Erro ao acessar o banco (DATABASE_URL). Detalhe: {e}")
    st.stop()

aba_atas, aba_docs = st.tabs(["📑 Atas", "🤖 Documentos (fila dos bots)"])

# ===========================================================================
# Aba 1 — Cadastro/edição de atas
# ===========================================================================
with aba_atas:
    st.caption("Edite na tabela, adicione linhas no rodapé ou remova selecionando a lixeira. Depois clique em salvar.")

    edit = st.data_editor(
        atas,
        num_rows="dynamic",
        width="stretch",
        key="atas_editor",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "numero_ata": st.column_config.TextColumn("Nº Ata", required=True),
            "ano": st.column_config.TextColumn("Ano"),
            "objeto": st.column_config.TextColumn("Objeto", width="large"),
            "vigencia_inicio": st.column_config.DateColumn("Assinatura", format="DD/MM/YYYY"),
            "vigencia_fim": st.column_config.DateColumn("Vigência", format="DD/MM/YYYY"),
            "prorrogada": st.column_config.CheckboxColumn("Prorrogada"),
        },
    )

    if st.button("💾 Salvar atas", type="primary"):
        ids_editados = set()
        for _, r in edit.iterrows():
            if not str(r.get("numero_ata") or "").strip():
                continue
            rid = None if pd.isna(r["id"]) else int(r["id"])
            if rid is not None:
                ids_editados.add(rid)
            upsert_ata(
                rid,
                str(r["numero_ata"]).strip(),
                _str_ou_nulo(r["ano"]),
                _str_ou_nulo(r["objeto"]),
                _data_ou_nulo(r["vigencia_inicio"]),
                _data_ou_nulo(r["vigencia_fim"]),
                bool(r["prorrogada"]) if pd.notna(r["prorrogada"]) else False,
            )

        for old_id in set(atas["id"].tolist()) - ids_editados:
            try:
                deletar_ata(int(old_id))
            except Exception:
                st.warning(f"Ata id={old_id} não pôde ser removida (há documentos/dados vinculados).")

        st.success("Atas atualizadas.")
        st.rerun()

# ===========================================================================
# Aba 2 — Fila de documentos (SD/ETP) por ata
# ===========================================================================
with aba_docs:
    if atas.empty:
        st.info("Cadastre uma ata na aba anterior antes de enfileirar documentos.")
        st.stop()

    atas = atas.copy()
    atas["label"] = "Ata " + atas["numero_ata"].astype(str) + "/" + atas["ano"].astype(str)
    escolha = st.selectbox("Ata", atas["label"].tolist())
    ata_id = int(atas.loc[atas["label"] == escolha, "id"].iloc[0])

    st.markdown("##### ➕ Enfileirar documento")
    st.caption("O documento entra como **pendente** e será raspado na próxima execução do bot correspondente.")
    with st.form("add_doc", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1, 1.5, 1, 2])
        tipo = c1.selectbox("Tipo", ["SD", "ETP"])
        numero = c2.text_input("Número")
        ano = c3.text_input("Ano")
        secretaria = c4.text_input("Secretaria (usada pelo bot de ETP)")
        if st.form_submit_button("Adicionar à fila"):
            if not numero.strip():
                st.warning("Informe o número do documento.")
            else:
                try:
                    adicionar_documento(ata_id, tipo, numero.strip(), ano.strip() or None, secretaria.strip() or None)
                    st.success(f"{tipo} {numero.strip()}/{ano.strip()} enfileirado.")
                except Exception as e:
                    st.error(f"Não foi possível adicionar: {e}")
                st.rerun()

    st.divider()
    st.markdown("##### 📋 Documentos desta ata")
    docs = listar_documentos(ata_id)
    if docs.empty:
        st.caption("Nenhum documento vinculado a esta ata.")
    else:
        emoji = {"pendente": "🟡 pendente", "processado": "🟢 processado", "erro": "🔴 erro"}
        vis = docs.copy()
        vis["status"] = vis["status"].map(lambda s: emoji.get(s, s))
        st.dataframe(vis, width="stretch", hide_index=True)

        ids = docs["id"].tolist()
        sel = st.multiselect("Selecionar documentos (por id) para ação:", ids)
        cc1, cc2 = st.columns(2)
        if cc1.button("🔁 Reenfileirar (voltar a pendente)", disabled=not sel):
            for i in sel:
                reenfileirar_documento(int(i))
            st.success("Documentos reenfileirados.")
            st.rerun()
        if cc2.button("🗑️ Remover da fila", disabled=not sel):
            for i in sel:
                deletar_documento(int(i))
            st.success("Documentos removidos.")
            st.rerun()
