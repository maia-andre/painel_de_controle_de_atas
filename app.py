"""Ponto de entrada (router multipage).

Mantém o `set_page_config` e o CSS globais e delega para as páginas em paginas/.
Rode com: streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Painel de Controle de Atas",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CSS CUSTOMIZADO (global, usado pelas tabelas/cards do dashboard) ---
st.markdown("""
<style>
    .card-container {
        background: linear-gradient(135deg, #002d72 0%, #001a40 100%);
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        margin-bottom: 16px;
        font-family: sans-serif;
    }
    .card-container .card-title {
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 4px;
    }
    .card-container .card-value {
        color: #ffffff;
        font-size: 1.8rem;
        font-weight: bold;
        margin: 0;
    }
    .progress-bar-bg {
        background-color: #e0e0e0;
        border-radius: 6px;
        overflow: hidden;
        height: 18px;
        width: 100%;
    }
    .progress-bar-fill {
        height: 100%;
        border-radius: 6px;
        text-align: center;
        font-size: 0.7rem;
        color: white;
        line-height: 18px;
        font-weight: bold;
    }
    .info-banner {
        background: linear-gradient(90deg, #002d72, #004aad);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        margin-bottom: 16px;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

paginas = [
    st.Page("paginas/dashboard.py", title="Dashboard", icon="📊", default=True),
    st.Page("paginas/admin_atas.py", title="Atas e Documentos", icon="📋"),
    st.Page("paginas/secretarias.py", title="Secretarias", icon="🏛️"),
]

st.navigation(paginas).run()
