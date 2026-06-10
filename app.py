import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# 1. Configuração inicial da página
st.set_page_config(
    page_title="Painel de Controle de Atas",
    page_icon="📊",
    layout="wide"
)

# --- CSS CUSTOMIZADO ---
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


def criar_card(titulo, valor, cor="#f2a900"):
    return f"""
    <div class="card-container" style="border-left: 6px solid {cor};">
        <p class="card-title" style="color: {cor};">{titulo}</p>
        <p class="card-value">{valor}</p>
    </div>
    """


def barra_progresso(percentual, previsto=True):
    """Retorna HTML de barra de progresso com cor dinâmica."""
    if not previsto:
        return (
            f'<div class="progress-bar-bg">'
            f'<div class="progress-bar-fill" style="width:100%;background:#d62828;">'
            f'Não Previsto</div></div>'
        )
    p = min(percentual, 100)
    if percentual > 100:
        cor = "#d62828"
    elif percentual >= 80:
        cor = "#f77f00"
    elif percentual >= 50:
        cor = "#f2a900"
    else:
        cor = "#2a9d8f"
    return (
        f'<div class="progress-bar-bg">'
        f'<div class="progress-bar-fill" style="width:{p}%;background:{cor};">'
        f'{percentual:.0f}%</div></div>'
    )


def formatar_brl(valor):
    """Formata valor numérico no padrão BRL (R$ 1.234,56)."""
    try:
        return f"R$ {valor:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')
    except Exception:
        return "R$ 0,00"


# ==========================================================
# 2. CARREGAMENTO DE DADOS
# ==========================================================
@st.cache_data
def carregar_dados():
    # --- Base de Atas (metadados: vigência, prorrogada) ---
    try:
        df_atas = pd.read_excel('base_sds.xlsx', dtype=str)
    except Exception:
        df_atas = pd.DataFrame()

    if not df_atas.empty:
        df_atas.columns = df_atas.columns.str.strip()
        ren = {}
        for c in df_atas.columns:
            if 'Ata' in c and 'N' in c and 'Prorr' not in c and 'Ano' not in c:
                ren[c] = 'Nº Ata'
            elif 'Ano' in c and 'Ata' in c:
                ren[c] = 'Ano Ata'
            elif 'Assinatura' in c:
                ren[c] = 'Assinatura'
            elif 'Vig' in c:
                ren[c] = 'Vigência'
            elif 'Prorr' in c:
                ren[c] = 'Prorrogada'
            elif 'Objeto' in c:
                ren[c] = 'Objeto'
        df_atas.rename(columns=ren, inplace=True)
        df_atas['Nº Ata'] = df_atas['Nº Ata'].fillna('').str.strip().str.replace(r'^0+', '', regex=True)
        df_atas['Ano Ata'] = df_atas['Ano Ata'].fillna('').str.strip()
        meta = df_atas.groupby(['Nº Ata', 'Ano Ata']).first().reset_index()
        meta = meta[['Nº Ata', 'Ano Ata'] + [c for c in ['Objeto', 'Assinatura', 'Vigência', 'Prorrogada'] if c in meta.columns]]
    else:
        meta = pd.DataFrame(columns=['Nº Ata', 'Ano Ata', 'Objeto', 'Assinatura', 'Vigência', 'Prorrogada'])

    # --- Base de Consumo (RCAF) ---
    try:
        df_real = pd.read_csv('base_rcaf.csv', sep=';', dtype=str, low_memory=False)
    except UnicodeDecodeError:
        df_real = pd.read_csv('base_rcaf.csv', sep=';', dtype=str, encoding='latin-1', low_memory=False)

    df_real.columns = df_real.columns.str.strip()
    rr = {}
    for col in df_real.columns:
        if 'N' in col and 'Ata' in col:
            rr[col] = 'Nº Ata'
        elif 'Ano' in col and 'Ata' in col:
            rr[col] = 'Ano Ata'
        elif 'Qtd' in col and 'RC' in col:
            rr[col] = 'Qtde RC'
        elif 'Val.Unit' in col and 'RC' in col:
            rr[col] = 'Valor Unit. RC'
        elif 'Val.Total' in col and 'RC' in col:
            rr[col] = 'Valor Total RC'
        elif 'Secr' in col and 'RC' in col:
            rr[col] = 'Secr. RC'
        elif 'Material' in col and 'RC' in col and 'Descri' not in col:
            rr[col] = 'Material RC'
        elif 'Descri' in col and 'Material' in col and 'RC' in col:
            rr[col] = 'Descrição Material RC'
        elif 'Data' in col and 'RC' in col:
            rr[col] = 'Data RC'
    df_real.rename(columns=rr, inplace=True)

    df_real['Nº Ata'] = df_real['Nº Ata'].fillna('').str.strip().str.replace(r'^0+', '', regex=True)
    df_real['Ano Ata'] = df_real['Ano Ata'].fillna('').str.strip()
    
    df_real['Qtde RC'] = pd.to_numeric(
        df_real.get('Qtde RC', pd.Series(dtype=str)).fillna('0').str.replace(',', '.', regex=False), errors='coerce'
    ).fillna(0)
    df_real['Valor Unit. RC'] = pd.to_numeric(
        df_real.get('Valor Unit. RC', pd.Series(dtype=str)).fillna('0').str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0)
    df_real['Valor Total RC'] = pd.to_numeric(
        df_real.get('Valor Total RC', pd.Series(dtype=str)).fillna('0').str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0)

    if 'Data RC' in df_real.columns:
        df_real['Data RC'] = pd.to_datetime(df_real['Data RC'], dayfirst=True, errors='coerce')

    # Descartar registros onde a AF (Autorização de Fornecimento) foi CANCELADA
    if 'Status AF' in df_real.columns:
        df_real = df_real[df_real['Status AF'] != 'CANCELADA']

    # --- Base de Previstos ---
    try:
        df_prev = pd.read_csv('previstos_dashboard.csv', sep=';', dtype=str, low_memory=False)
    except UnicodeDecodeError:
        df_prev = pd.read_csv('previstos_dashboard.csv', sep=';', dtype=str, encoding='latin-1', low_memory=False)

    df_prev.columns = df_prev.columns.str.strip()
    rp = {}
    for col in df_prev.columns:
        if 'N' in col and 'Ata' in col:
            rp[col] = 'Nº Ata'
        elif 'Ano' in col and 'Ata' in col:
            rp[col] = 'Ano Ata'
        elif 'Qtde' in col and 'Prev' in col:
            rp[col] = 'Qtde Prevista'
        elif 'Valor Unit' in col and 'Prev' in col:
            rp[col] = 'Valor Unitário Previsto'
        elif 'Valor Total' in col and 'Prev' in col:
            rp[col] = 'Valor Total Previsto'
        elif 'Secr' in col and 'RC' in col:
            rp[col] = 'Secr. RC'
        elif 'Material' in col and 'RC' in col and 'Descri' not in col:
            rp[col] = 'Material RC'
        elif 'Descri' in col and 'Material' in col and 'RC' in col:
            rp[col] = 'Descrição Material RC'
        elif 'Unidade' in col and 'Medida' in col:
            rp[col] = 'Unidade de Medida'
    df_prev.rename(columns=rp, inplace=True)

    df_prev['Nº Ata'] = df_prev['Nº Ata'].fillna('').str.strip().str.replace(r'^0+', '', regex=True)
    df_prev['Ano Ata'] = df_prev['Ano Ata'].fillna('').str.strip()
    df_prev['Qtde Prevista'] = pd.to_numeric(
        df_prev.get('Qtde Prevista', pd.Series(dtype=str)).fillna('0').str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0)
    df_prev['Valor Total Previsto'] = pd.to_numeric(
        df_prev.get('Valor Total Previsto', pd.Series(dtype=str)).fillna('0').str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0)
    df_prev['Valor Unitário Previsto'] = pd.to_numeric(
        df_prev.get('Valor Unitário Previsto', pd.Series(dtype=str)).fillna('0').str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).fillna(0)

    # Dicionário de secretarias
    dic_sec = {
        5: "5 - GP", 10: "10 - SG", 15: "15 - SAJ", 20: "20 - SGAF",
        30: "30 - SEURBS", 35: "35 - SGO", 40: "40 - SEC", 45: "45 - SEQV", 50: "50 - SASC",
        55: "55 - SMC", 60: "60 - SS", 65: "65 - SEMOB", 70: "70 - SEPAC",
        75: "75 - SIDE", 80: "80 - EG", 90: "90 - SHRF"
    }
    
    for df in [df_real, df_prev]:
        if 'Secr. RC' in df.columns:
            nums = df['Secr. RC'].str.extract(r'(\d+)')[0].astype(float)
            df['Nome Secretaria'] = nums.map(dic_sec).fillna(df['Secr. RC'])

    return df_real, df_prev, meta


# ==========================================================
# 3. INTERFACE
# ==========================================================
st.title("📊 Painel de Controle de Atas")
st.markdown("Visão consolidada: **Planejamento (ETP)** vs. **Execução (RC)**.")
st.divider()

try:
    df_real, df_prev, df_meta = carregar_dados()
except FileNotFoundError:
    st.error("⚠️ Certifique-se de que os arquivos 'base_rcaf.csv' e 'previstos_dashboard.csv' estão no diretório.")
    st.stop()

# --- Montar lista de atas disponíveis ---
atas_prev = df_prev[['Nº Ata', 'Ano Ata']].drop_duplicates()
atas_real = df_real[['Nº Ata', 'Ano Ata']].drop_duplicates()
atas_todas = pd.concat([atas_prev, atas_real]).drop_duplicates().sort_values(['Ano Ata', 'Nº Ata'])
atas_todas = atas_todas[(atas_todas['Nº Ata'] != '') & (atas_todas['Ano Ata'] != '')]

# Mapear objetos a partir de df_meta para pesquisa de palavras-chave
dict_objetos = {}
if not df_meta.empty and 'Objeto' in df_meta.columns:
    dict_objetos = df_meta.groupby(['Nº Ata', 'Ano Ata'])['Objeto'].first().to_dict()

opcoes_ata = []
for _, r in atas_todas.iterrows():
    num, ano = r['Nº Ata'], r['Ano Ata']
    obj = dict_objetos.get((num, ano), "")
    if obj and str(obj).strip():
        # Limpar descrição e anexar na opção
        label = f"Ata {num}/{ano} - {str(obj).strip()}"
    else:
        label = f"Ata {num}/{ano}"
    opcoes_ata.append(label)

col_sel1, col_sel2 = st.columns([2, 3])
with col_sel1:
    escolha = st.selectbox("Selecione a Ata", opcoes_ata, index=None, placeholder="Escolha uma ata...")

if not escolha:
    st.info("👆 Selecione uma ata para visualizar a comparação Previsto vs. Realizado.")
    st.stop()

# Parse seleção
parts = escolha.split(" - ")[0]
busca_ata = parts.split("Ata ")[1].split("/")[0]
busca_ano = parts.split("/")[1]

# --- Buscar metadados da ata ---
info_ata = df_meta[(df_meta['Nº Ata'] == busca_ata) & (df_meta['Ano Ata'] == busca_ano)]
prorrogada = False
dt_inicio = None
dt_fim = None

if not info_ata.empty:
    row_meta = info_ata.iloc[0]
    obj_ata = row_meta.get('Objeto', '')
    prorrogada = str(row_meta.get('Prorrogada', 'N')).strip().upper() == 'S'
    try:
        dt_inicio = pd.to_datetime(row_meta.get('Assinatura', ''))
        dt_fim = pd.to_datetime(row_meta.get('Vigência', ''))
    except Exception:
        pass

    # Banner informativo
    banner = f"<div class='info-banner'><b>📋 {obj_ata[:120]}{'...' if len(str(obj_ata)) > 120 else ''}</b>"
    if dt_inicio and dt_fim:
        banner += f" &nbsp;|&nbsp; Vigência: {dt_inicio.strftime('%d/%m/%Y')} a {dt_fim.strftime('%d/%m/%Y')}"
    if prorrogada:
        banner += " &nbsp;|&nbsp; ⚠️ <b>ATA PRORROGADA</b>"
    banner += "</div>"
    st.markdown(banner, unsafe_allow_html=True)

# --- Filtrar dados pela ata selecionada ---
ata_real = df_real[(df_real['Nº Ata'] == busca_ata) & (df_real['Ano Ata'] == busca_ano)].copy()
ata_prev = df_prev[(df_prev['Nº Ata'] == busca_ata) & (df_prev['Ano Ata'] == busca_ano)].copy()

# --- Filtro de período para atas prorrogadas ---
periodo_label = "Período completo"
if prorrogada and dt_inicio is not None and dt_fim is not None and 'Data RC' in ata_real.columns:
    meio = dt_inicio + (dt_fim - dt_inicio) / 2
    with col_sel2:
        periodo = st.radio(
            "Período de consumo (ata prorrogada)",
            ["Completo", f"Ano 1 (até {meio.strftime('%d/%m/%Y')})", f"Ano 2 (após {meio.strftime('%d/%m/%Y')})"],
            horizontal=True,
            index=2 # Padrão para Ano 2
        )
    if "Ano 1" in periodo:
        ata_real = ata_real[ata_real['Data RC'] <= meio]
        periodo_label = "Ano 1"
    elif "Ano 2" in periodo:
        ata_real = ata_real[ata_real['Data RC'] > meio]
        periodo_label = "Ano 2"

if ata_prev.empty and ata_real.empty:
    st.warning(f"⚠️ Nenhuma informação encontrada para a Ata {busca_ata}/{busca_ano}.")
    st.stop()

# ==========================================================
# 4. ENGINE DE CRUZAMENTO (MERGE)
# ==========================================================
# Garantir existência das colunas de valor unitário
v_unit_prev_col = 'Valor Unitário Previsto' if 'Valor Unitário Previsto' in ata_prev.columns else 'Valor Unitário Previsto'
v_unit_real_col = 'Valor Unit. RC' if 'Valor Unit. RC' in ata_real.columns else 'Valor Unit. RC'

# Assegurar tipo numérico nas colunas locais de valor unitário
if v_unit_prev_col in ata_prev.columns:
    ata_prev[v_unit_prev_col] = pd.to_numeric(ata_prev[v_unit_prev_col], errors='coerce').fillna(0)
else:
    ata_prev[v_unit_prev_col] = 0.0

if v_unit_real_col in ata_real.columns:
    ata_real[v_unit_real_col] = pd.to_numeric(ata_real[v_unit_real_col], errors='coerce').fillna(0)
else:
    ata_real[v_unit_real_col] = 0.0

grp_prev = ata_prev.groupby(
    ['Material RC', 'Nome Secretaria', 'Unidade de Medida'], as_index=False
).agg({
    'Descrição Material RC': 'first',
    'Qtde Prevista': 'sum',
    'Valor Total Previsto': 'sum',
    v_unit_prev_col: 'first'
})

grp_real = ata_real.groupby(
    ['Material RC', 'Nome Secretaria'], as_index=False
).agg({
    'Descrição Material RC': 'first',
    'Qtde RC': 'sum',
    'Valor Total RC': 'sum',
    v_unit_real_col: 'first'
})

df_m = pd.merge(grp_prev, grp_real, on=['Material RC', 'Nome Secretaria'], how='outer')
df_m['Descrição Material RC'] = df_m['Descrição Material RC_y'].fillna(df_m['Descrição Material RC_x']).fillna('Sem Descrição')
df_m['Unidade de Medida'] = df_m['Unidade de Medida'].fillna('-')
df_m.drop(columns=['Descrição Material RC_x', 'Descrição Material RC_y'], inplace=True, errors='ignore')

# Mapeamentos globais por código para resolver lacunas
global_prev_prices = grp_prev.groupby('Material RC')[v_unit_prev_col].first().to_dict()
global_real_prices = grp_real.groupby('Material RC')[v_unit_real_col].first().to_dict()

# Determinar valor unitário definitivo APENAS pelo preço praticado na base de consumo (Val.Unit RC)
df_m['Vlr Unitário'] = df_m[v_unit_real_col].replace(0, np.nan)
df_m['Vlr Unitário'] = df_m['Vlr Unitário'].fillna(df_m['Material RC'].map(global_real_prices))
df_m['Vlr Unitário'] = df_m['Vlr Unitário'].fillna(0)

df_m = df_m.fillna(0)

# Padronizar Descrição e Unidade por código (evitar duplicidades na tabela geral e preencher o que não foi previsto)
desc_map = df_m[df_m['Descrição Material RC'] != 'Sem Descrição'].groupby('Material RC')['Descrição Material RC'].first()
unid_map = df_m[df_m['Unidade de Medida'] != '-'].groupby('Material RC')['Unidade de Medida'].first()
df_m['Descrição Material RC'] = df_m['Material RC'].map(desc_map).fillna(df_m['Descrição Material RC'])
df_m['Unidade de Medida'] = df_m['Material RC'].map(unid_map).fillna(df_m['Unidade de Medida'])

# Regra para Serviços (SV): Usar Valor Total RC/Previsto em vez de Quantidade
df_m['Métrica Prevista'] = np.where(df_m['Unidade de Medida'] == 'SV', df_m['Valor Total Previsto'], df_m['Qtde Prevista'])
df_m['Métrica RC'] = np.where(df_m['Unidade de Medida'] == 'SV', df_m['Valor Total RC'], df_m['Qtde RC'])

df_m['Saldo'] = df_m['Métrica Prevista'] - df_m['Métrica RC']
df_m['% Consumo'] = np.where(df_m['Métrica Prevista'] > 0, df_m['Métrica RC'] / df_m['Métrica Prevista'] * 100, 0)

# ==========================================================
# 5. TABELA GERAL POR ITEM (RESUMO EXECUTIVO COM CAPPING CONTRATUAL A 100%)
# ==========================================================
# O consumo acumulado real por item na ata não pode ultrapassar o teto contratual previsto (100% de consumo, saldo zero).
# Criamos a tabela geral primeiro para obtermos as métricas consolidadas e limitadas por item de acordo com as regras de negócio contratuais.
df_geral = df_m.groupby(
    ['Material RC', 'Descrição Material RC', 'Unidade de Medida'], as_index=False
).agg({
    'Métrica Prevista': 'sum',
    'Métrica RC': 'sum',
    'Valor Total RC': 'sum',
    'Vlr Unitário': 'first'
})

# Salvar o consumo real sem limites para identificar itens críticos/esgotados reais
df_geral['Métrica RC Real'] = df_geral['Métrica RC']

# Aplicar o cap de 100% no consumo e saldo mínimo zero para a visão contratual consolidada
df_geral['Métrica RC'] = np.minimum(df_geral['Métrica RC'], df_geral['Métrica Prevista'])
df_geral['Saldo'] = np.maximum(0.0, df_geral['Métrica Prevista'] - df_geral['Métrica RC'])
df_geral['% Consumo'] = np.where(df_geral['Métrica Prevista'] > 0, df_geral['Métrica RC'] / df_geral['Métrica Prevista'] * 100, 0)

# Ordenação
df_geral['Material_Num'] = pd.to_numeric(df_geral['Material RC'], errors='coerce').fillna(0)
df_geral = df_geral.sort_values('Material_Num', ascending=True).drop(columns=['Material_Num'])

# ==========================================================
# 5.1 KPIs E RESUMO EXECUTIVO
# ==========================================================
total_prev = df_geral['Métrica Prevista'].sum()
total_real = df_geral['Métrica RC'].sum() # Soma das métricas limitadas ao teto contratual da Ata
valor_total = df_geral['Valor Total RC'].sum()
perc_global = (total_real / total_prev * 100) if total_prev > 0 else 0

n_itens = df_geral.shape[0]
# Criticos e esgotados usam a métrica real não limitada para identificar pressão real física sobre as cotas
criticos = int(((df_geral['Métrica RC Real'] / df_geral['Métrica Prevista']) >= 0.9).sum())
esgotados = int(((df_geral['Métrica RC Real'] / df_geral['Métrica Prevista']) >= 1.0).sum())

st.subheader("Resumo Executivo")
k1, k2, k3, k4, k5 = st.columns(5)
k1.markdown(criar_card("Consumo Global", f"{perc_global:.1f}%", "#f2a900" if perc_global < 90 else "#d62828"), unsafe_allow_html=True)
k2.markdown(criar_card("Valor Total (RCs)", f"R$ {valor_total:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')), unsafe_allow_html=True)
k3.markdown(criar_card("Total de Itens", str(n_itens), "#2a9d8f"), unsafe_allow_html=True)
k4.markdown(criar_card("Itens Críticos (≥90%)", f"{criticos}", "#f77f00" if criticos > 0 else "#2a9d8f"), unsafe_allow_html=True)
k5.markdown(criar_card("Itens Esgotados (100%)", f"{esgotados}", "#d62828" if esgotados > 0 else "#2a9d8f"), unsafe_allow_html=True)

st.divider()

# ==========================================================
# 5.5 TABELA GERAL POR ITEM (APRESENTAÇÃO)
# ==========================================================
st.subheader("📋 Resumo Geral por Item")
st.caption("Visão consolidada do consumo total da ata, independente da secretaria (limitada ao teto contratual de 100%).")


linhas_geral_html = ""
for _, r in df_geral.iterrows():
    nao_previsto = (r['Métrica Prevista'] == 0) and (r['Métrica RC'] > 0)
    bp = barra_progresso(r['% Consumo'], previsto=not nao_previsto)
    
    saldo_cor = "color:#d62828;font-weight:bold;" if r['Saldo'] < 0 else ""
    fmt_m = "{:,.2f}" if r['Unidade de Medida'] == 'SV' else "{:,.0f}"
    
    linha_estilo = "background-color: #ffe6e6; font-weight: bold; color: #990000;" if nao_previsto else ""
    
    vlr_unit_str = "-" if r['Unidade de Medida'] == 'SV' or r['Vlr Unitário'] == 0 else formatar_brl(r['Vlr Unitário'])
    
    linhas_geral_html += f"""
    <tr style="{linha_estilo}">
        <td>{r['Material RC']}</td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{r['Descrição Material RC']}">{r['Descrição Material RC'][:70]}</td>
        <td style="text-align:center;">{r['Unidade de Medida']}</td>
        <td style="text-align:right; font-weight:bold;">{vlr_unit_str}</td>
        <td style="text-align:right;">{fmt_m.format(r['Métrica Prevista'])}</td>
        <td style="text-align:right;">{fmt_m.format(r['Métrica RC'])}</td>
        <td style="text-align:right;{saldo_cor}">{fmt_m.format(r['Saldo'])}</td>
        <td style="min-width:120px;">{bp}</td>
        <td style="text-align:right;">{formatar_brl(r['Valor Total RC'])}</td>
    </tr>"""

tabela_geral_html = f"""
<div style="overflow-x:auto; max-height:400px; overflow-y:auto; margin-bottom: 20px;">
<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
<thead style="position:sticky;top:0;background:#004aad;color:white;">
<tr>
    <th style="padding:8px;text-align:left;">Código</th>
    <th style="padding:8px;text-align:left;">Descrição</th>
    <th style="padding:8px;text-align:center;">Unid.</th>
    <th style="padding:8px;text-align:right;">Vlr. Unitário</th>
    <th style="padding:8px;text-align:right;">Total Previsto</th>
    <th style="padding:8px;text-align:right;">Total Realizado</th>
    <th style="padding:8px;text-align:right;">Saldo Geral</th>
    <th style="padding:8px;text-align:center;">% Consumo Global</th>
    <th style="padding:8px;text-align:right;">Gasto Total</th>
</tr>
</thead>
<tbody>{linhas_geral_html}</tbody>
</table>
</div>
"""
st.markdown(tabela_geral_html, unsafe_allow_html=True)

st.divider()
# ==========================================================
# 6. TABELA DETALHADA COM BARRAS DE PROGRESSO
# ==========================================================
st.subheader("📋 Detalhamento por Item e Secretaria")
st.caption("Nota: Para itens de serviço (SV), as colunas de Previsto, Realizado e Saldo exibem o Valor Financeiro ao invés de quantidades.")

# Filtros por Item e Secretaria
col_f1, col_f2 = st.columns(2)
with col_f1:
    itens_cod = sorted(df_m['Material RC'].unique().tolist())
    item_filtro = st.multiselect("Filtrar por Código do Item:", itens_cod, default=itens_cod)
with col_f2:
    secretarias = sorted(df_m['Nome Secretaria'].unique().tolist())
    sec_filtro = st.multiselect("Filtrar por Secretaria:", secretarias, default=secretarias)

df_tab = df_m[df_m['Material RC'].isin(item_filtro) & df_m['Nome Secretaria'].isin(sec_filtro)].copy()

df_tab['Material_Num'] = pd.to_numeric(df_tab['Material RC'], errors='coerce').fillna(0)
df_tab = df_tab.sort_values(['Material_Num', 'Nome Secretaria'], ascending=[True, True]).drop(columns=['Material_Num'])

# Montar HTML da tabela
linhas_html = ""
for _, r in df_tab.iterrows():
    nao_previsto = (r['Métrica Prevista'] == 0) and (r['Métrica RC'] > 0)
    bp = barra_progresso(r['% Consumo'], previsto=not nao_previsto)
    
    saldo_cor = "color:#d62828;font-weight:bold;" if r['Saldo'] < 0 else ""
    fmt_m = "{:,.2f}" if r['Unidade de Medida'] == 'SV' else "{:,.0f}"
    
    linha_estilo = "background-color: #ffe6e6; font-weight: bold; color: #990000;" if nao_previsto else ""
    
    vlr_unit_str = "-" if r['Unidade de Medida'] == 'SV' or r['Vlr Unitário'] == 0 else formatar_brl(r['Vlr Unitário'])
    
    linhas_html += f"""
    <tr style="{linha_estilo}">
        <td>{r['Material RC']}</td>
        <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{r['Descrição Material RC']}">{r['Descrição Material RC'][:60]}</td>
        <td style="text-align:center;">{r['Unidade de Medida']}</td>
        <td style="text-align:right; font-weight:bold;">{vlr_unit_str}</td>
        <td>{r['Nome Secretaria']}</td>
        <td style="text-align:right;">{fmt_m.format(r['Métrica Prevista'])}</td>
        <td style="text-align:right;">{fmt_m.format(r['Métrica RC'])}</td>
        <td style="text-align:right;{saldo_cor}">{fmt_m.format(r['Saldo'])}</td>
        <td style="min-width:120px;">{bp}</td>
        <td style="text-align:right;">{formatar_brl(r['Valor Total RC'])}</td>
    </tr>"""

tabela_html = f"""
<div style="overflow-x:auto; max-height:500px; overflow-y:auto;">
<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
<thead style="position:sticky;top:0;background:#002d72;color:white;">
<tr>
    <th style="padding:8px;text-align:left;">Código</th>
    <th style="padding:8px;text-align:left;">Descrição</th>
    <th style="padding:8px;text-align:center;">Unid.</th>
    <th style="padding:8px;text-align:right;">Vlr. Unitário</th>
    <th style="padding:8px;text-align:left;">Secretaria</th>
    <th style="padding:8px;text-align:right;">Previsto</th>
    <th style="padding:8px;text-align:right;">Realizado</th>
    <th style="padding:8px;text-align:right;">Saldo</th>
    <th style="padding:8px;text-align:center;">% Consumo</th>
    <th style="padding:8px;text-align:right;">Gasto Total</th>
</tr>
</thead>
<tbody>{linhas_html}</tbody>
</table>
</div>
"""
st.markdown(tabela_html, unsafe_allow_html=True)

st.divider()

# ==========================================================
# 7. GRÁFICO INTERATIVO
# ==========================================================
st.subheader("📊 Volume Previsto vs. Realizado por Secretaria")

lista_itens = sorted(df_m['Material RC'].unique().tolist())
lista_itens.insert(0, "TODOS OS ITENS")
item_sel = st.selectbox("Filtrar gráfico por item:", lista_itens)

if item_sel == "TODOS OS ITENS":
    df_g = df_m.groupby('Nome Secretaria')[['Métrica Prevista', 'Métrica RC']].sum().reset_index()
else:
    df_g = df_m[df_m['Material RC'] == item_sel].groupby('Nome Secretaria')[['Métrica Prevista', 'Métrica RC']].sum().reset_index()

df_g = df_g.rename(columns={'Métrica Prevista': 'Teto Previsto', 'Métrica RC': 'Consumo Realizado'})
df_g = df_g.sort_values('Teto Previsto', ascending=True)

if not df_g.empty:
    fig = go.Figure()
    cores_realizado = ['#d62828' if r > t else '#005ce6' for r, t in zip(df_g['Consumo Realizado'], df_g['Teto Previsto'])]

    fig.add_trace(go.Bar(
        y=df_g['Nome Secretaria'], x=df_g['Consumo Realizado'],
        name='Consumo Realizado (RC)', orientation='h',
        marker=dict(color=cores_realizado),
        offsetgroup=0
    ))
    fig.add_trace(go.Bar(
        y=df_g['Nome Secretaria'], x=df_g['Teto Previsto'],
        name='Teto Previsto (ETP)', orientation='h',
        marker=dict(color='rgba(0,0,0,0)', line=dict(color='#f2a900', width=4)),
        offsetgroup=0
    ))
    fig.update_layout(
        barmode='overlay', height=max(350, len(df_g) * 45),
        margin=dict(l=10, r=10, t=30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(title="Métrica (Unidades ou Reais p/ SV)", showgrid=True, gridcolor='rgba(128,128,128,0.15)'),
        yaxis=dict(title="")
    )
    st.plotly_chart(fig, width='stretch')
else:
    st.info("Sem dados gráficos para a seleção.")

# ==========================================================
# 8. MATRIZ PIVOT (mantida para referência cruzada)
# ==========================================================
with st.expander("🔍 Matriz de Consumo detalhada (Pivot Table)"):
    tabela_pivot = pd.pivot_table(
        df_m.rename(columns={'Métrica Prevista': '1.Previsto', 'Métrica RC': '2.Realizado'}),
        index=['Material RC', 'Descrição Material RC', 'Unidade de Medida'],
        columns='Nome Secretaria',
        values=['1.Previsto', '2.Realizado'],
        aggfunc='sum', fill_value=0
    )
    tabela_pivot = tabela_pivot.swaplevel(0, 1, axis=1).sort_index(axis=1)
    st.dataframe(tabela_pivot, width='stretch')