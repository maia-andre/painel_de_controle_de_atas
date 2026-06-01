import os
import getpass
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError

# =============================================================================
# CONFIGURAÇÕES DE ARQUIVOS
# =============================================================================
ARQUIVO_ORIGEM = "base_sds.xlsx"  
ARQUIVO_SAIDA = "previstos_dashboard.csv"
ARQUIVO_CHECKPOINT = "log_sds_processadas.txt"

def carregar_checkpoint():
    if not os.path.exists(ARQUIVO_CHECKPOINT):
        return set()
    with open(ARQUIVO_CHECKPOINT, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)

def salvar_checkpoint(chave_doc):
    with open(ARQUIVO_CHECKPOINT, 'a', encoding='utf-8') as f:
        f.write(f"{chave_doc}\n")

def inicializar_csv_saida():
    if not os.path.exists(ARQUIVO_SAIDA):
        with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
            f.write("Material RC;Descrição Material RC;Unidade de Medida;Secr. RC;Qtde Prevista;Valor Unitário Previsto;Valor Total Previsto;Num DOC;Nº Ata;Ano Ata\n")

def salvar_itens(itens):
    if not itens:
        return
    df = pd.DataFrame(itens)
    df.to_csv(ARQUIVO_SAIDA, mode='a', sep=';', header=False, index=False, encoding='utf-8')

# =============================================================================
# MOTOR DO BOT (PLAYWRIGHT) - VERSÃO SD
# =============================================================================
def rodar_extracao():
    print("=== BOT DE EXTRAÇÃO DE SDs (ADMC) ===")
    
    usuario = input("Digite seu Usuário (CPF): ").strip()
    senha = getpass.getpass("Digite sua Senha: ")
    
    try:
        df_fila = pd.read_excel(ARQUIVO_ORIGEM, dtype=str)
    except Exception as e:
        print(f"Erro ao ler {ARQUIVO_ORIGEM}: {e}")
        return
    
    df_fila.columns = df_fila.columns.str.strip()
    
    # Vacina contra caracteres invisíveis no cabeçalho
    if 'N Ata' in df_fila.columns:
        df_fila.rename(columns={'N Ata': 'Nº Ata'}, inplace=True)
    if 'N° Ata' in df_fila.columns:
        df_fila.rename(columns={'N° Ata': 'Nº Ata'}, inplace=True)
        
    colunas_num_sd = [col for col in df_fila.columns if col.startswith('Num SD')]
    colunas_ano_sd = [col for col in df_fila.columns if col.startswith('Ano SD')]
    
    processados = carregar_checkpoint()
    inicializar_csv_saida()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) 
        context = browser.new_context()
        page = context.new_page()
        
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
        
        print("[+] Expandindo menu 'Compras'...")
        admc.locator("xpath=//li[div[contains(@class, 'a-TreeView-content')]/span[text()='Compras']]/span[contains(@class, 'a-TreeView-toggle')]").click()
        admc.wait_for_timeout(1000)
        
        print("[+] Expandindo menu 'Lei 14133_2021'...")
        admc.locator("xpath=//li[div[contains(@class, 'a-TreeView-content')]/span[text()='Lei 14133_2021']]/span[contains(@class, 'a-TreeView-toggle')]").click()
        admc.wait_for_timeout(1000)
        
        print("[+] Expandindo menu 'SD'...")
        bloco_sd = admc.locator("xpath=//li[div[contains(@class, 'a-TreeView-content')]/span[text()='SD']]")
        bloco_sd.locator("xpath=./span[contains(@class, 'a-TreeView-toggle')]").click()
        admc.wait_for_timeout(1000)
        
        print("[+] Acessando tela de 'Cadastro' de SD...")
        bloco_sd.locator("xpath=.//li[div[contains(@class, 'a-TreeView-content')]/*[contains(text(), 'Cadastro')]]/div[contains(@class, 'a-TreeView-content')]").click()
        
        admc.wait_for_selector("#P12001_SDNUM", timeout=20000)
        
        total_atas = len(df_fila)
        for index, row in df_fila.iterrows():
            ata_num = str(row.get('Nº Ata', '')).strip()
            ata_ano = str(row.get('Ano Ata', '')).strip()
            
            if ata_num.lower() == 'nan': ata_num = ''
            if ata_ano.lower() == 'nan': ata_ano = ''
            
            print(f"\n[+] Processando Ata {ata_num}/{ata_ano} (Linha {index+1}/{total_atas})...")
            
            for col_num, col_ano in zip(colunas_num_sd, colunas_ano_sd):
                num_sd = str(row.get(col_num, '')).strip()
                ano_sd = str(row.get(col_ano, '')).strip()
                
                if not num_sd or num_sd.lower() == 'nan':
                    continue
                
                chave_doc = f"{num_sd}/{ano_sd}"
                
                if chave_doc in processados:
                    print(f"    -> Pulo: SD {chave_doc} já processada.")
                    continue
                    
                print(f"    -> Buscando SD {chave_doc}...")
                
                try:
                    admc.locator("#P12001_SDNUM").fill(num_sd)
                    admc.locator("#P12001_SDANO").fill(ano_sd)
                    admc.wait_for_timeout(500)  
                    
                    admc.locator("#B926380280944559563").click()
                    
                    linha_resultado = admc.locator(f"table.a-IRR-table tbody tr:has-text('{num_sd}')").first
                    
                    try:
                        linha_resultado.wait_for(state="visible", timeout=45000)
                    except TimeoutError:
                        print(f"       [!] SD {chave_doc} não encontrada na busca.")
                        admc.locator("#P12001_SDNUM").fill("")
                        admc.locator("#P12001_SDANO").fill("")
                        continue
                    
                    # --- BLINDAGEM DO DOM (Tentativas de leitura para evitar o erro de contexto destruído) ---
                    admc.wait_for_timeout(2000) # Respiro inicial maior
                    nome_secretaria = "N/A"
                    
                    for tentativa in range(3):
                        try:
                            cabecalhos = admc.locator("table.a-IRR-table th").all_inner_texts()
                            indice_sec = [i for i, cab in enumerate(cabecalhos) if 'Secretaria' in cab][0]
                            colunas_resultado = linha_resultado.locator("td").all()
                            nome_secretaria = colunas_resultado[indice_sec].inner_text().strip()
                            break # Se deu certo, sai do loop de tentativas
                        except Exception:
                            admc.wait_for_timeout(1500) # Se falhou, espera mais um pouco e tenta de novo
                    
                    if nome_secretaria == "N/A":
                        print("       [!] Aviso: Não foi possível identificar a coluna 'Secretaria' após várias tentativas.")

                    print(f"       -> Secretaria identificada: {nome_secretaria}")

                    linha_resultado.locator("img.apex-edit-pencil").click()
                    
                    admc.locator("th:has-text('Qtde')").first.wait_for(state="visible", timeout=45000)
                    admc.wait_for_timeout(1500)
                    
                    linhas = admc.locator("table.a-IRR-table tbody tr").all()
                    itens_raspados = []
                    
                    for linha in linhas[1:]:
                        colunas = linha.locator("td").all()
                        
                        if len(colunas) >= 7:
                            codigo = colunas[1].inner_text().strip()
                            descricao = colunas[2].inner_text().strip()
                            unidade = colunas[3].inner_text().strip()
                            quantidade = colunas[4].inner_text().strip()
                            valor_unitario = colunas[5].inner_text().strip()
                            valor_total = colunas[6].inner_text().strip()
                            
                            status = ""
                            if len(colunas) >= 10:
                                status = colunas[9].inner_text().strip().upper()
                            
                            if codigo and codigo != "Código":
                                if "CANCELAD" in status:
                                    continue
                                
                                itens_raspados.append({
                                    'Material RC': codigo,
                                    'Descrição Material RC': descricao,
                                    'Unidade de Medida': unidade,
                                    'Secr. RC': nome_secretaria, 
                                    'Qtde Prevista': quantidade,
                                    'Valor Unitário Previsto': valor_unitario,
                                    'Valor Total Previsto': valor_total,
                                    'Num DOC': chave_doc,        
                                    'Nº Ata': ata_num,           
                                    'Ano Ata': ata_ano           
                                })
                    
                    if itens_raspados:
                        salvar_itens(itens_raspados)
                        salvar_checkpoint(chave_doc)
                        print(f"       -> {len(itens_raspados)} itens salvos com sucesso.")
                    else:
                        print(f"       -> Nenhum item encontrado.")
                    
                    admc.go_back()
                    admc.wait_for_selector("#P12001_SDNUM", timeout=45000)
                    
                    admc.locator("#P12001_SDNUM").fill("")
                    admc.locator("#P12001_SDANO").fill("")

                except Exception as e:
                    print(f"       [!] Erro ao processar a SD {chave_doc}: {e}")
        
        print("\n=== EXTRAÇÃO CONCLUÍDA ===")
        browser.close()

if __name__ == "__main__":
    rodar_extracao()