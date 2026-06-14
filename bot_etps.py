"""Bot de extração de ETPs (portal eSJC/ADMC) -> tabela `previstos`.

Fila e checkpoint vivem em `ata_documentos` (tipo_doc='ETP'). Credenciais via
env (PORTAL_CPF/PORTAL_SENHA) ou prompt. Headless por padrão (BOT_HEADLESS=false
para depurar com o navegador visível).
"""
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.bot_db import get_credenciais, get_fila, headless, marcar_status, salvar_previstos


def rodar_extracao():
    print("=== BOT DE EXTRAÇÃO DE ETPS (ADMC) ===")

    fila = get_fila("ETP")
    if not fila:
        print("Nenhum ETP pendente na fila (ata_documentos).")
        return

    usuario, senha = get_credenciais()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless())
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
        total = len(fila)
        for idx, doc in enumerate(fila):
            num_etp = str(doc["numero_doc"]).strip()
            ano_etp = str(doc.get("ano_doc") or "").strip()
            nome_secretaria = str(doc.get("secretaria") or "").strip()
            chave_etp = f"{num_etp}/{ano_etp}"

            print(f"[{idx+1}/{total}] Extraindo ETP {chave_etp} (Secr: {nome_secretaria})...")

            try:
                # 1. Preenche os campos e Pesquisa
                admc.locator("#P12015_ETPNUM").fill(num_etp)
                admc.locator("#P12015_ETPANO").fill(ano_etp)
                admc.wait_for_timeout(500)
                admc.locator("#B33574469468732801").click()

                # 2. ESPERA DINÂMICA: aguarda a linha com o número do ETP pesquisado
                linha_resultado = admc.locator(f"table.a-IRR-table tbody tr:has-text('{num_etp}')").first

                try:
                    linha_resultado.wait_for(state="visible", timeout=45000)
                except TimeoutError:
                    print("    -> ETP não encontrado na busca (ou sistema demorou mais de 45s).")
                    marcar_status(doc["id"], "erro")
                    admc.locator("#P12015_ETPNUM").fill("")
                    admc.locator("#P12015_ETPANO").fill("")
                    continue

                # 3. ENTRANDO NO ETP: clica na lupa da linha carregada
                linha_resultado.locator("img.apex-edit-pencil").click()

                # 4. Aguarda a tela interna do ETP carregar
                admc.locator("th:has-text('Qtde')").first.wait_for(state="visible", timeout=45000)
                admc.wait_for_timeout(1500)

                # 5. Raspa a tabela de itens
                linhas = admc.locator("table.a-IRR-table tbody tr").all()
                itens = []
                for linha in linhas[1:]:
                    colunas = linha.locator("td").all()
                    if len(colunas) >= 5:
                        codigo = colunas[1].inner_text().strip()
                        descricao = colunas[2].inner_text().strip()
                        unidade = colunas[3].inner_text().strip()
                        quantidade = colunas[4].inner_text().strip()

                        if codigo and codigo != "Código":
                            itens.append({
                                "codigo_material": codigo,
                                "descricao": descricao,
                                "unidade": unidade,
                                "orgao": nome_secretaria,
                                "qtd_prevista": quantidade,
                                "tipo_doc": "ETP",
                                "numero_doc": chave_etp,
                                "ata_id": doc.get("ata_id"),
                                "numero_ata": doc.get("numero_ata"),
                                "ano": doc.get("ano"),
                            })

                n = salvar_previstos("ETP", chave_etp, itens)
                marcar_status(doc["id"], "processado")
                print(f"    -> {n} itens salvos com sucesso." if n else "    -> Nenhum item encontrado neste ETP.")

                # 6. VOLTAR PARA A BUSCA
                admc.go_back()
                admc.wait_for_selector("#P12015_ETPNUM", timeout=45000)
                admc.locator("#P12015_ETPNUM").fill("")
                admc.locator("#P12015_ETPANO").fill("")

            except Exception as e:
                print(f"    [!] Erro ao processar o ETP {chave_etp}: {e}")
                marcar_status(doc["id"], "erro")

        print("\n=== EXTRAÇÃO CONCLUÍDA ===")
        browser.close()


if __name__ == "__main__":
    rodar_extracao()
