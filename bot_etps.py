import os
import getpass
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError

# =============================================================================
# CONFIGURAÇÕES DE ARQUIVOS
# =============================================================================
ARQUIVO_ORIGEM = "base_etps.csv" 
ARQUIVO_SAIDA = "previstos_dashboard.csv"
ARQUIVO_CHECKPOINT = "log_etps_processados.txt"

def carregar_checkpoint():
    if not os.path.exists(ARQUIVO_CHECKPOINT):
        return set()
    with open(ARQUIVO_CHECKPOINT, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)

def salvar_checkpoint(chave_etp):
    with open(ARQUIVO_CHECKPOINT, 'a', encoding='utf-8') as f:
        f.write(f"{chave_etp}\n")

def inicializar_csv_saida():
    if not os.path.exists(ARQUIVO_SAIDA):
        with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
            f.write("Material RC;Descrição Material RC;Unidade de Medida;Secr. RC;Qtde Prevista;Num ETP;Nº Ata;Ano Ata\n")

def salvar_itens(itens):
    if not itens:
        return
    df = pd.DataFrame(itens)
    df.to_csv(ARQUIVO_SAIDA, mode='a', sep=';', header=False, index=False, encoding='utf-8')

# =============================================================================
# MOTOR DO BOT (PLAYWRIGHT)
# =============================================================================
def rodar_extracao():
    print("=== BOT DE EXTRAÇÃO DE ETPS (ADMC) ===")
    
    usuario = input("Digite seu Usuário (CPF): ").strip()
    senha = getpass.getpass("Digite sua Senha: ")
    
    try:
        df_fila = pd.read_csv(ARQUIVO_ORIGEM, sep=';', dtype=str)
    except UnicodeDecodeError:
        df_fila = pd.read_csv(ARQUIVO_ORIGEM, sep=';', dtype=str, encoding='latin-1')
    except Exception as e:
        print(f"Erro ao ler {ARQUIVO_ORIGEM}: {e}")
        return
    
    # LIMPEZA DE CABEÇALHOS E DEBUG
    df_fila.columns = df_fila.columns.str.strip()
    print("\n[+] Colunas identificadas no CSV:", df_fila.columns.tolist())
    
    processados = carregar_checkpoint()
    inicializar_csv_saida()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) 
        context = browser.new_context()
        page = context.new_page()
        
        # --- LOGIN UNIFICADO ---
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
        
        print("[+] Login no portal realizado. Abrindo ADMC...")
        
        with context.expect_page() as nova_aba_info:
            page.locator("xpath=//a[.//img[@alt='ADMC']]").click()
        
        admc = nova_aba_info.value
        admc.wait_for_load_state("networkidle", timeout=30000)
        print("[+] ADMC aberto com sucesso!")
        
        # --- NAVEGAÇÃO NO MENU (Com XPaths Blindados) ---
        print("[+] Expandindo menu 'Compras'...")
        admc.locator("xpath=//li[div[contains(@class, 'a-TreeView-content')]/span[text()='Compras']]/span[contains(@class, 'a-TreeView-toggle')]").click()
        admc.wait_for_timeout(1000)
        
        print("[+] Expandindo menu 'Lei 14133_2021'...")
        admc.locator("xpath=//li[div[contains(@class, 'a-TreeView-content')]/span[text()='Lei 14133_2021']]/span[contains(@class, 'a-TreeView-toggle')]").click()
        admc.wait_for_timeout(1000)
        
        print("[+] Expandindo menu 'ETP'...")
        bloco_etp = admc.locator("xpath=//li[div[contains(@class, 'a-TreeView-content')]/span[text()='ETP']]")
        bloco_etp.locator("xpath=./span[contains(@class, 'a-TreeView-toggle')]").click()
        admc.wait_for_timeout(1000)
        
        print("[+] Acessando tela de 'Cadastro'...")
        bloco_etp.locator("xpath=.//li[div[contains(@class, 'a-TreeView-content')]/*[contains(text(), 'Cadastro')]]/div[contains(@class, 'a-TreeView-content')]").click()
        
        # Aguarda a tela de ETPs carregar
        admc.wait_for_selector("#P12015_ETPNUM", timeout=20000)
        
        # --- LOOP DA FILA DE ETPs ---
        total = len(df_fila)
        for index, row in df_fila.iterrows():
            num_etp = str(row['Num.']).strip()
            ano_etp = str(row['Ano']).strip()
            
            nome_secretaria = str(row['secretaria']).strip() 
            
            chave_etp = f"{num_etp}/{ano_etp}"
            
            if chave_etp in processados:
                print(f"[{index+1}/{total}] Pulo: ETP {chave_etp} já processado.")
                continue
                
            print(f"[{index+1}/{total}] Extraindo ETP {chave_etp} (Secr: {nome_secretaria})...")
            
            try:
                # 1. Preenche os campos e Pesquisa
                admc.locator("#P12015_ETPNUM").fill(num_etp)
                admc.locator("#P12015_ETPANO").fill(ano_etp)
                admc.wait_for_timeout(500)  
                admc.locator("#B33574469468732801").click()
                
                # 2. ESPERA DINÂMICA
                # Em vez de um tempo fixo, mandamos ele esperar a linha que contenha exatamente o número do ETP pesquisado
                linha_resultado = admc.locator(f"table.a-IRR-table tbody tr:has-text('{num_etp}')").first
                
                try:
                    # Dá até 45 segundos de paciência para o sistema responder à busca
                    linha_resultado.wait_for(state="visible", timeout=45000)
                except TimeoutError:
                    print(f"    -> ETP não encontrado na busca (ou sistema demorou mais de 45s).")
                    admc.locator("#P12015_ETPNUM").fill("")
                    admc.locator("#P12015_ETPANO").fill("")
                    continue
                
                # 3. ENTRANDO NO ETP: Clica na lupa exatamente da linha que acabou de carregar
                linha_resultado.locator("img.apex-edit-pencil").click()
                
                # 4. Aguarda a tela interna do ETP (Página de Detalhes) carregar (timeout de 45s)
                admc.locator("th:has-text('Qtde')").first.wait_for(state="visible", timeout=45000)
                admc.wait_for_timeout(1500) # Um respiro de 1.5s só para o HTML terminar de se desenhar
                
                # 5. AGORA SIM: Raspa a tabela de itens
                tabela_locator = admc.locator("table.a-IRR-table tbody tr")
                linhas = tabela_locator.all()
                
                itens_raspados = []
                
                for linha in linhas[1:]:
                    colunas = linha.locator("td").all()
                    
                    if len(colunas) >= 5:
                        codigo = colunas[1].inner_text().strip()
                        descricao = colunas[2].inner_text().strip()
                        unidade = colunas[3].inner_text().strip()
                        quantidade = colunas[4].inner_text().strip()
                        
                        # Evita linhas vazias ou de cabeçalho
                        if codigo and codigo != "Código":
                            itens_raspados.append({
                                'Material RC': codigo,
                                'Descrição Material RC': descricao,
                                'Unidade de Medida': unidade,
                                'Secr. RC': nome_secretaria,
                                'Qtde Prevista': quantidade,
                                'Num ETP': chave_etp,
                                'Nº Ata': '', 
                                'Ano Ata': ''
                            })
                
                if itens_raspados:
                    salvar_itens(itens_raspados)
                    salvar_checkpoint(chave_etp)
                    print(f"    -> {len(itens_raspados)} itens salvos com sucesso.")
                else:
                    print(f"    -> Nenhum item encontrado na tabela deste ETP.")
                
                # 6. VOLTAR PARA A BUSCA
                admc.go_back()
                
                # Aguarda o campo de busca aparecer de novo para garantir que voltámos com sucesso
                admc.wait_for_selector("#P12015_ETPNUM", timeout=45000)
                
                admc.locator("#P12015_ETPNUM").fill("")
                admc.locator("#P12015_ETPANO").fill("")

            except Exception as e:
                print(f"    [!] Erro ao processar o ETP {chave_etp}: {e}")
        
        print("\n=== EXTRAÇÃO CONCLUÍDA ===")
        browser.close()

if __name__ == "__main__":
    rodar_extracao()