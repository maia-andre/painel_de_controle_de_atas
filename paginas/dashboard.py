import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from db import get_df


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
# CARREGAMENTO DE DADOS (PostgreSQL)
# ==========================================================
@st.cache_data
def carregar_dados():
    # --- Metadados das atas ---
    meta = get_df('''
        SELECT numero_ata AS "Nº Ata", ano AS "Ano Ata", objeto AS "Objeto",
               vigencia_inicio AS "Assinatura", vigencia_fim AS "Vigência",
               CASE WHEN prorrogada THEN 'S' ELSE 'N' END AS "Prorrogada"
        FROM atas
    ''')
    for c in ['Nº Ata', 'Ano Ata']:
        meta[c] = meta[c].fillna('').astype(str).str.strip()

    # --- Consumo (RCAF) — já sem cancelados (view consumo_valido) ---
    df_real = get_df('''
        SELECT c.numero_ata AS "Nº Ata", c.ano AS "Ano Ata",
               c.codigo_material AS "Material RC",
               c.descricao AS "Descrição Material RC",
               c.quantidade AS "Qtde RC", c.valor_unitario AS "Valor Unit. RC",
               c.valor_total AS "Valor Total RC", c.data_rc AS "Data RC",
               c.orgao AS "Secr. RC",
               COALESCE(s.codigo || ' - ' || s.sigla, c.orgao) AS "Nome Secretaria"
        FROM consumo_valido c
        LEFT JOIN secretarias s ON s.codigo = c.secretaria_codigo
    ''')
    for c in ['Nº Ata', 'Ano Ata', 'Material RC', 'Nome Secretaria']:
        df_real[c] = df_real[c].fillna('').astype(str).str.strip()
    for c in ['Qtde RC', 'Valor Unit. RC', 'Valor Total RC']:
        df_real[c] = pd.to_numeric(df_real[c], errors='coerce').fillna(0)
    df_real['Data RC'] = pd.to_datetime(df_real['Data RC'], errors='coerce')

    # --- Previstos (teto planejado) ---
    df_prev = get_df('''
        SELECT p.numero_ata AS "Nº Ata", p.ano AS "Ano Ata",
               p.codigo_material AS "Material RC",
               p.descricao AS "Descrição Material RC",
               p.qtd_prevista AS "Qtde Prevista",
               p.valor_total_previsto AS "Valor Total Previsto",
               p.unidade AS "Unidade de Medida", p.orgao AS "Secr. RC",
               COALESCE(s.codigo || ' - ' || s.sigla, p.orgao) AS "Nome Secretaria"
        FROM previstos p
        LEFT JOIN secretarias s ON s.codigo = p.secretaria_codigo
    ''')
    for c in ['Nº Ata', 'Ano Ata', 'Material RC', 'Nome Secretaria']:
        df_prev[c] = df_prev[c].fillna('').astype(str).str.strip()
    df_prev['Unidade de Medida'] = df_prev['Unidade de Medida'].fillna('-')
    for c in ['Qtde Prevista', 'Valor Total Previsto']:
        df_prev[c] = pd.to_numeric(df_prev[c], errors='coerce').fillna(0)

    return df_real, df_prev, meta


# ==========================================================
# INTERFACE
# ==========================================================
st.title("📊 Painel de Controle de Atas")
st.markdown("Visão consolidada: **Planejamento (ETP)** vs. **Execução (RC)**.")
st.divider()

try:
    df_real, df_prev, df_meta = carregar_dados()
except Exception as e:
    st.error(
        "⚠️ Erro ao carregar dados do banco. Verifique a conexão "
        f"(DATABASE_URL no .env). Detalhe: {e}"
    )
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
# ENGINE DE CRUZAMENTO (MERGE)
# ==========================================================
# Valor unitário vem EXCLUSIVAMENTE do preço praticado na execução (Val.Unit RC).
# O valor unitário da SD/previsto nunca é usado (dado errado, do início da licitação).
v_unit_real_col = 'Valor Unit. RC'
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

# Preço unitário definitivo: somente o praticado na base de consumo (Val.Unit RC)
global_real_prices = grp_real.groupby('Material RC')[v_unit_real_col].first().to_dict()
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
# TABELA GERAL POR ITEM (RESUMO EXECUTIVO COM CAPPING CONTRATUAL A 100%)
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

# Aplicar o cap de 100% no consumo e saldo mínimo zero para a visão contratual consolidada.
# A mesma métrica limitada alimenta a tabela E os KPIs: no consolidado nada passa de 100%.
df_geral['Métrica RC'] = np.minimum(df_geral['Métrica RC'], df_geral['Métrica Prevista'])
df_geral['Saldo'] = np.maximum(0.0, df_geral['Métrica Prevista'] - df_geral['Métrica RC'])
df_geral['% Consumo'] = np.where(df_geral['Métrica Prevista'] > 0, df_geral['Métrica RC'] / df_geral['Métrica Prevista'] * 100, 0)

# Ordenação
df_geral['Material_Num'] = pd.to_numeric(df_geral['Material RC'], errors='coerce').fillna(0)
df_geral = df_geral.sort_values('Material_Num', ascending=True).drop(columns=['Material_Num'])

# ==========================================================
# KPIs E RESUMO EXECUTIVO
# ==========================================================
total_prev = df_geral['Métrica Prevista'].sum()
total_real = df_geral['Métrica RC'].sum() # Soma das métricas limitadas ao teto contratual da Ata
valor_total = df_geral['Valor Total RC'].sum()
perc_global = (total_real / total_prev * 100) if total_prev > 0 else 0

n_itens = df_geral.shape[0]
# Críticos e esgotados usam a métrica já limitada ao teto (consolidado nunca passa de 100%).
# Itens "não previstos" (sem teto) têm % Consumo = 0 e, portanto, não inflam o contador de esgotados.
criticos = int((df_geral['% Consumo'] >= 90).sum())
esgotados = int((df_geral['% Consumo'] >= 100).sum())

st.subheader("Resumo Executivo")
k1, k2, k3, k4, k5 = st.columns(5)
k1.markdown(criar_card("Consumo Global", f"{perc_global:.1f}%", "#f2a900" if perc_global < 90 else "#d62828"), unsafe_allow_html=True)
k2.markdown(criar_card("Valor Total (RCs)", f"R$ {valor_total:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')), unsafe_allow_html=True)
k3.markdown(criar_card("Total de Itens", str(n_itens), "#2a9d8f"), unsafe_allow_html=True)
k4.markdown(criar_card("Itens Críticos (≥90%)", f"{criticos}", "#f77f00" if criticos > 0 else "#2a9d8f"), unsafe_allow_html=True)
k5.markdown(criar_card("Itens Esgotados (100%)", f"{esgotados}", "#d62828" if esgotados > 0 else "#2a9d8f"), unsafe_allow_html=True)

st.divider()

# ==========================================================
# TABELA GERAL POR ITEM (APRESENTAÇÃO)
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
# TABELA DETALHADA COM BARRAS DE PROGRESSO
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
# GRÁFICO INTERATIVO
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
# MATRIZ PIVOT (mantida para referência cruzada)
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
