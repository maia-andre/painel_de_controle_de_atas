import os
import getpass
import pandas as pd
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================
ARQUIVO_SAIDA = "base_rcaf.csv"
ARQUIVO_CHECKPOINT = "log_rcaf_ultima_execucao.txt"
ARQUIVO_TEMP_DOWNLOAD = "rcaf_download_temp.csv"
DATA_INICIO_HISTORICO = "01/01/2024"  # Usado quando base_rcaf.csv não existe ainda
JANELA_ATUALIZACAO_DIAS = 30          # Re-consulta últimos N dias para capturar mudanças de status

# value da opção "1. Relatório completo" no <select> de relatórios salvos do IRR.
# O bot seleciona esse relatório e RE-CONFIRMA até a seleção ficar estável: o IRR do
# APEX às vezes reverte para o 'Primário' (reduzido, sem Val.Unit RC) após um reload
# assíncrono tardio do 'Buscar'. Ver garantir_relatorio_completo().
REPORT_COMPLETO_VALUE = "5495497332881863449"

# Modo inspeção: True = captura HTML da tela e pausa para mapeamento manual.
MODO_INSPECAO = False

# Modo teste: True = grava em base_rcaf_TESTE.csv e NÃO altera a base real nem o
# checkpoint — valida download+parsing sem risco. Volte para False em produção.
MODO_TESTE = False

# =============================================================================
# CHECKPOINT (por data, não por ID)
# =============================================================================
def carregar_ultima_execucao():
    if not os.path.exists(ARQUIVO_CHECKPOINT):
        return None
    with open(ARQUIVO_CHECKPOINT, 'r', encoding='utf-8') as f:
        conteudo = f.read().strip()
        return conteudo if conteudo else None

def salvar_ultima_execucao():
    with open(ARQUIVO_CHECKPOINT, 'w', encoding='utf-8') as f:
        f.write(datetime.today().strftime('%d/%m/%Y'))

def calcular_janela_datas():
    hoje = datetime.today()
    data_fim = hoje.strftime('%d/%m/%Y')
    base_existe = os.path.exists(ARQUIVO_SAIDA) and os.path.getsize(ARQUIVO_SAIDA) > 0
    if not base_existe:
        print(f"[!] {ARQUIVO_SAIDA} não encontrada. Usando início histórico: {DATA_INICIO_HISTORICO}")
        return DATA_INICIO_HISTORICO, data_fim
    data_ini = (hoje - timedelta(days=JANELA_ATUALIZACAO_DIAS)).strftime('%d/%m/%Y')
    return data_ini, data_fim

# =============================================================================
# PROCESSAMENTO DE DADOS
# =============================================================================
def _parse_brl(valor):
    """Converte string em formato BRL (1.234,56) para float."""
    if pd.isna(valor) or str(valor).strip() in ('', '-', 'nan'):
        return 0.0
    return pd.to_numeric(
        str(valor).strip().replace('.', '').replace(',', '.'),
        errors='coerce'
    ) or 0.0

def _formatar_brl(valor_float):
    """Converte float para string BRL (1.234,56)."""
    return f"{valor_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def calcular_val_total_rc(df):
    """Calcula Val.Total RC = Val.Unit RC × Qtd RC (coluna não nativa do sistema)."""
    val_unit = df['Val.Unit RC'].apply(_parse_brl)
    qtd = df['Qtd RC'].apply(_parse_brl)
    df['Val.Total RC'] = (val_unit * qtd).apply(_formatar_brl)
    return df

def _make_key(row, key_cols):
    """Gera chave composta tratando NaN como string vazia."""
    parts = []
    for col in key_cols:
        val = row.get(col, '')
        if pd.isna(val) or str(val).strip().lower() == 'nan':
            parts.append('')
        else:
            parts.append(str(val).strip())
    return '|'.join(parts)

def fazer_upsert(df_novo, arquivo_saida=ARQUIVO_SAIDA):
    """
    Mescla df_novo na base_rcaf.csv.
    Chave: RC + AF + Material RC
      - Linhas com chave existente: status e demais campos são atualizados.
      - Linhas novas: inseridas no final.
    """
    KEY_COLS = ['RC', 'AF', 'Material RC']
    df_novo['_key'] = df_novo.apply(lambda r: _make_key(r, KEY_COLS), axis=1)

    if os.path.exists(ARQUIVO_SAIDA) and os.path.getsize(ARQUIVO_SAIDA) > 0:
        try:
            df_existente = pd.read_csv(ARQUIVO_SAIDA, sep=';', dtype=str)
        except UnicodeDecodeError:
            df_existente = pd.read_csv(ARQUIVO_SAIDA, sep=';', dtype=str, encoding='latin-1')

        df_existente['_key'] = df_existente.apply(lambda r: _make_key(r, KEY_COLS), axis=1)

        novos      = df_novo[~df_novo['_key'].isin(df_existente['_key'])]
        atualizados = df_novo[df_novo['_key'].isin(df_existente['_key'])]
        mantidos   = df_existente[~df_existente['_key'].isin(df_novo['_key'])]

        resultado = pd.concat([mantidos, atualizados, novos], ignore_index=True)
        print(f"    -> {len(novos)} linhas novas inseridas.")
        print(f"    -> {len(atualizados)} linhas existentes atualizadas.")
        print(f"    -> {len(mantidos)} linhas anteriores mantidas intactas.")
    else:
        resultado = df_novo
        print(f"    -> {len(df_novo)} linhas inseridas (base nova).")

    resultado = resultado.drop(columns=['_key'], errors='ignore')
    # Grava em Latin-1 para casar com a base existente e com o export do portal
    # (ambos Latin-1) e abrir corretamente no Excel. O app.py lê os dois encodings.
    resultado.to_csv(arquivo_saida, sep=';', index=False, encoding='latin-1')
    print(f"    -> Resultado gravado em '{arquivo_saida}' ({len(resultado)} linhas).")

# =============================================================================
# ABERTURA ROBUSTA DO DIÁLOGO DE DOWNLOAD (menu Ações do APEX é flaky)
# =============================================================================
def abrir_dialogo_download(admc, region):
    """Abre o menu Ações e clica em 'Fazer Download' com retentativa, pois o
    clique no botão de menu do APEX às vezes não dispara a abertura.
    Retorna True quando o diálogo de formato (CSV/Excel) fica visível."""
    btn = admc.locator(f"#{region}_actions_button")
    item = admc.locator("button.a-Menu-label", has_text="Fazer Download")
    formatos = admc.locator(f"#{region}_download_formats")
    for tentativa in range(1, 5):
        # 1) garante o menu aberto (só clica se o item ainda não estiver visível)
        if not item.is_visible():
            btn.click()
            try:
                item.wait_for(state="visible", timeout=4000)
            except TimeoutError:
                print(f"    -> menu Ações não abriu (tentativa {tentativa}); repetindo...")
                admc.wait_for_timeout(1000)
                continue
        # 2) clica em 'Fazer Download' e espera o diálogo de formato
        item.click()
        try:
            formatos.wait_for(state="visible", timeout=8000)
            return True
        except TimeoutError:
            print(f"    -> diálogo não abriu após clicar Download (tentativa {tentativa}); repetindo...")
            admc.wait_for_timeout(1000)
    return False

# =============================================================================
# SELEÇÃO ESTÁVEL DO "RELATÓRIO COMPLETO" (o IRR reverte p/ 'Primário' às vezes)
# =============================================================================
def garantir_relatorio_completo(admc, region, valor, tentativas=6):
    """Seleciona o 'Relatório completo' e garante que a seleção PERMANECE estável.
    O IRR do APEX por vezes reverte para o relatório padrão ('Primário', reduzido,
    sem Val.Unit RC) após um reload assíncrono tardio do 'Buscar'. Por isso
    re-seleciona e revalida o value do <select> até ele ficar estável.
    Retorna True quando o <select> está (e permanece) no 'Relatório completo'."""
    sel = admc.locator(f"#{region}_saved_reports")
    sel.wait_for(state="visible", timeout=30000)
    for tentativa in range(1, tentativas + 1):
        if sel.input_value() != valor:
            print(f"    -> selecionando 'Relatório completo' (tentativa {tentativa})...")
            sel.select_option(value=valor)
            admc.wait_for_load_state("networkidle", timeout=60000)
            admc.wait_for_timeout(2500)  # janela para um reload tardio reverter
        # Revalida: precisa continuar no completo após uma espera adicional.
        admc.wait_for_timeout(2000)
        if sel.input_value() == valor:
            print(f"    -> 'Relatório completo' confirmado e estável (tentativa {tentativa}).")
            return True
        print(f"    -> relatório reverteu para o padrão; repetindo...")
    return sel.input_value() == valor

# =============================================================================
# MOTOR DO BOT (PLAYWRIGHT)
# =============================================================================
def rodar_extracao():
    print("=== BOT DE EXTRAÇÃO DE RC/AF (ADMC) ===")

    usuario = input("Digite seu Usuário (CPF): ").strip()
    senha = getpass.getpass("Digite sua Senha: ")

    data_ini, data_fim = calcular_janela_datas()
    print(f"\n[+] Janela de consulta: {data_ini} → {data_fim}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # --- LOGIN (idêntico aos outros bots) ---
        print("\n[+] Acessando portal e efetuando login...")
        page.goto("https://sv03.sjc.sp.gov.br/eSJC/index.jsf#_", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=30000)

        page.locator("xpath=//a[contains(., 'Login')]").click()
        page.wait_for_load_state("networkidle", timeout=30000)

        page.locator("#cpf").fill(usuario)
        page.locator("#senha").fill(senha)
        page.wait_for_timeout(400)
        page.locator("#loginInternoButton").click()
        page.wait_for_load_state("networkidle", timeout=30000)
        print("[+] Login realizado. Abrindo ADMC...")

        with context.expect_page() as nova_aba_info:
            page.locator("xpath=//a[.//img[@alt='ADMC']]").click()

        admc = nova_aba_info.value
        admc.wait_for_load_state("networkidle", timeout=30000)
        print("[+] ADMC aberto com sucesso!")

        # --- NAVEGAÇÃO: Relatórios > Geral > Material (SD, ETP, RC e AF) ---
        print("[+] Expandindo menu 'Relatórios'...")
        admc.locator("xpath=//li[div[contains(@class, 'a-TreeView-content')]/span[text()='Relatórios']]/span[contains(@class, 'a-TreeView-toggle')]").click()
        admc.wait_for_timeout(1000)

        print("[+] Expandindo menu 'Geral'...")
        admc.locator("xpath=//li[div[contains(@class, 'a-TreeView-content')]/span[text()='Geral']]/span[contains(@class, 'a-TreeView-toggle')]").click()
        admc.wait_for_timeout(1000)

        print("[+] Acessando 'Material (SD, ETP, RC e AF)'...")
        admc.locator("xpath=//a[contains(@class, 'a-TreeView-label') and contains(text(), 'Material (SD, ETP, RC e AF)')]").click()
        admc.wait_for_load_state("networkidle", timeout=30000)

        # --- FILTROS DE DATA ---
        print(f"[+] Preenchendo filtro de data: {data_ini} a {data_fim}...")
        admc.locator("#P5045_DATA_INI").fill(data_ini)
        admc.locator("#P5045_DATA_FIM").fill(data_fim)
        admc.wait_for_timeout(300)

        print("[+] Clicando em Buscar...")
        admc.locator("#B1626455186604065282").click()
        admc.wait_for_load_state("networkidle", timeout=60000)

        # --- MODO INSPEÇÃO: captura o HTML para mapear os seletores de download ---
        if MODO_INSPECAO:
            print("\n" + "=" * 70)
            print("[INSPEÇÃO] Capturando a estrutura da tela para mapear o download...")
            print("=" * 70)

            with open("inspect_01_report.html", "w", encoding="utf-8") as f:
                f.write(admc.content())
            print("[INSPEÇÃO] -> inspect_01_report.html  (tela do relatório / opções de relatórios salvos)")

            # 1) Abre o seletor de relatórios salvos (onde fica 'Relatório Completo')
            try:
                admc.locator("#R1626374312484053947_saved_reports").click()
                admc.wait_for_timeout(1000)
                with open("inspect_02_saved_reports.html", "w", encoding="utf-8") as f:
                    f.write(admc.content())
                print("[INSPEÇÃO] -> inspect_02_saved_reports.html  (dropdown de relatórios salvos aberto)")
                admc.keyboard.press("Escape")
                admc.wait_for_timeout(500)
            except Exception as e:
                print(f"[INSPEÇÃO] (!) Não consegui abrir o seletor de relatórios salvos: {e}")

            # 2) Abre o menu Ações (onde fica 'Fazer Download')
            try:
                admc.locator("#R1626374312484053947_actions_button").click()
                admc.wait_for_timeout(1000)
                with open("inspect_03_actions_menu.html", "w", encoding="utf-8") as f:
                    f.write(admc.content())
                print("[INSPEÇÃO] -> inspect_03_actions_menu.html  (menu Ações aberto)")
            except Exception as e:
                print(f"[INSPEÇÃO] (!) Não consegui abrir o menu Ações: {e}")

            print("\n[INSPEÇÃO] Navegador PAUSADO. Faça o seguinte À MÃO nesta janela do navegador:")
            print("   1. Troque o relatório de 'Primário' para 'Relatório Completo'.")
            print("   2. Confira se a tabela ganha mais colunas (valida que o relatório existe).")
            print("   3. Em Ações > Fazer Download, baixe um CSV e confira que o fluxo funciona.")
            print("   Quando terminar, clique em 'Resume' no Playwright Inspector para encerrar.\n")
            admc.pause()

            browser.close()
            return

        # --- DOWNLOAD DO CSV ---
        # Deixa o load do "Buscar" ASSENTAR antes de trocar o relatório, para que a
        # nossa seleção seja o último estado aplicado (o IRR às vezes dispara um
        # reload tardio do 'Buscar' que reverte o relatório para o 'Primário').
        admc.wait_for_timeout(3000)

        # Passo 1: garante o 'Relatório completo' e que a seleção PERMANECE estável.
        print("[+] Selecionando 'Relatório completo' e confirmando estabilidade...")
        if not garantir_relatorio_completo(admc, "R1626374312484053947", REPORT_COMPLETO_VALUE):
            print("[!] Não consegui fixar o 'Relatório completo' (segue revertendo p/ Primário).")
            print("[!] Abortando SEM baixar e SEM alterar a base de produção.")
            browser.close()
            return
        admc.locator("#R1626374312484053947_actions_button").wait_for(state="visible", timeout=30000)
        admc.wait_for_timeout(1000)

        # Passo 2: abre o diálogo de download (Ações > Fazer Download), robusto.
        print("[+] Abrindo menu Ações > Fazer Download...")
        if not abrir_dialogo_download(admc, "R1626374312484053947"):
            with open("inspect_05_download_falhou.html", "w", encoding="utf-8") as f:
                f.write(admc.content())
            print("[!] Não consegui abrir o diálogo de download após várias tentativas.")
            print("[!] Salvei 'inspect_05_download_falhou.html'. Pausando p/ inspeção...")
            admc.pause()
            browser.close()
            return

        # Passo 3: diálogo aberto -> garante CSV (já vem pré-selecionado) e confirma
        #          no botão 'Fazer Download' (ui-button--hot), que dispara o download.
        print("[+] Diálogo aberto. Selecionando CSV e confirmando...")
        try:
            admc.locator("#R1626374312484053947_download_formats li[data-value='CSV']").click()
            admc.wait_for_timeout(300)
            with admc.expect_download(timeout=60000) as download_info:
                admc.locator(".a-IRR-dialog--download button.ui-button--hot").click()
            download = download_info.value
            download.save_as(ARQUIVO_TEMP_DOWNLOAD)
            print(f"[+] Download concluído: '{ARQUIVO_TEMP_DOWNLOAD}'")
        except Exception as e:
            with open("inspect_06_confirmacao_falhou.html", "w", encoding="utf-8") as f:
                f.write(admc.content())
            print(f"[!] Falha ao confirmar/baixar o CSV: {e}")
            print("[!] Salvei 'inspect_06_confirmacao_falhou.html'. Pausando p/ inspeção...")
            admc.pause()
            browser.close()
            return

        browser.close()

    # --- PROCESSAMENTO E UPSERT ---
    print("\n[+] Processando CSV baixado...")
    try:
        df = pd.read_csv(ARQUIVO_TEMP_DOWNLOAD, sep=';', dtype=str)
    except UnicodeDecodeError:
        df = pd.read_csv(ARQUIVO_TEMP_DOWNLOAD, sep=';', dtype=str, encoding='latin-1')

    df.columns = df.columns.str.strip()

    # Trava de segurança: confirma que veio o "Relatório completo" (com as colunas
    # de valor). Se vier o relatório reduzido, aborta SEM tocar na base nem no
    # checkpoint — evita corromper produção com um download incompleto.
    COLS_OBRIGATORIAS = ['Qtd RC', 'Val.Unit RC']
    faltando = [c for c in COLS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        print(f"\n[!] Colunas obrigatórias ausentes no CSV baixado: {faltando}")
        print(f"[!] Colunas recebidas ({len(df.columns)}): {list(df.columns)}")
        print("[!] O relatório baixado provavelmente NÃO é o 'Relatório completo'.")
        print(f"[!] CSV bruto mantido em '{ARQUIVO_TEMP_DOWNLOAD}' para conferência.")
        print("[!] Abortando SEM alterar a base de produção nem o checkpoint.")
        return

    df = calcular_val_total_rc(df)

    saida = "base_rcaf_TESTE.csv" if MODO_TESTE else ARQUIVO_SAIDA
    print(f"[+] {len(df)} registros no CSV. Fazendo upsert -> {saida} ...")
    fazer_upsert(df, arquivo_saida=saida)

    if MODO_TESTE:
        print("\n[TESTE] Base real e checkpoint PRESERVADOS.")
        print("[TESTE] Confira o resultado em 'base_rcaf_TESTE.csv'.")
        print(f"[TESTE] CSV bruto mantido em '{ARQUIVO_TEMP_DOWNLOAD}' para conferência.")
    else:
        salvar_ultima_execucao()
        if os.path.exists(ARQUIVO_TEMP_DOWNLOAD):
            os.remove(ARQUIVO_TEMP_DOWNLOAD)

    print("\n=== EXTRAÇÃO CONCLUÍDA ===")

if __name__ == "__main__":
    rodar_extracao()
