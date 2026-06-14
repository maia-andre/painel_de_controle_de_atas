"""Bot de extração de SDs (portal eSJC/ADMC) -> tabela `previstos`.

Fila e checkpoint vivem em `ata_documentos` (tipo_doc='SD'), já com a ata
vinculada pelo gestor. Credenciais via env (PORTAL_CPF/PORTAL_SENHA) ou prompt.
Headless por padrão (BOT_HEADLESS=false para depurar com o navegador visível).

A SD não armazena valor unitário (dado errado da licitação): só quantidade e
valor total previsto vão para o banco.
"""
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.bot_db import get_credenciais, get_fila, headless, marcar_status, salvar_previstos


def rodar_extracao():
    print("=== BOT DE EXTRAÇÃO DE SDs (ADMC) ===")

    fila = get_fila("SD")
    if not fila:
        print("Nenhuma SD pendente na fila (ata_documentos).")
        return

    usuario, senha = get_credenciais()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless())
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

        total = len(fila)
        for idx, doc in enumerate(fila):
            num_sd = str(doc["numero_doc"]).strip()
            ano_sd = str(doc.get("ano_doc") or "").strip()
            chave_doc = f"{num_sd}/{ano_sd}"

            print(f"[{idx+1}/{total}] Buscando SD {chave_doc} (Ata {doc.get('numero_ata')}/{doc.get('ano')})...")

            try:
                admc.locator("#P12001_SDNUM").fill(num_sd)
                admc.locator("#P12001_SDANO").fill(ano_sd)
                admc.wait_for_timeout(500)

                admc.locator("#B926380280944559563").click()

                linha_resultado = admc.locator(f"table.a-IRR-table tbody tr:has-text('{num_sd}')").first

                try:
                    linha_resultado.wait_for(state="visible", timeout=45000)
                except TimeoutError:
                    print(f"    [!] SD {chave_doc} não encontrada na busca.")
                    marcar_status(doc["id"], "erro")
                    admc.locator("#P12001_SDNUM").fill("")
                    admc.locator("#P12001_SDANO").fill("")
                    continue

                # --- BLINDAGEM DO DOM: lê a secretaria do cabeçalho com tentativas ---
                admc.wait_for_timeout(2000)
                nome_secretaria = "N/A"
                for _ in range(3):
                    try:
                        cabecalhos = admc.locator("table.a-IRR-table th").all_inner_texts()
                        indice_sec = [i for i, cab in enumerate(cabecalhos) if 'Secretaria' in cab][0]
                        colunas_resultado = linha_resultado.locator("td").all()
                        nome_secretaria = colunas_resultado[indice_sec].inner_text().strip()
                        break
                    except Exception:
                        admc.wait_for_timeout(1500)

                if nome_secretaria == "N/A":
                    print("    [!] Aviso: não foi possível identificar a coluna 'Secretaria'.")
                print(f"    -> Secretaria identificada: {nome_secretaria}")

                linha_resultado.locator("img.apex-edit-pencil").click()

                admc.locator("th:has-text('Qtde')").first.wait_for(state="visible", timeout=45000)
                admc.wait_for_timeout(1500)

                linhas = admc.locator("table.a-IRR-table tbody tr").all()
                itens = []
                for linha in linhas[1:]:
                    colunas = linha.locator("td").all()
                    if len(colunas) >= 7:
                        codigo = colunas[1].inner_text().strip()
                        descricao = colunas[2].inner_text().strip()
                        unidade = colunas[3].inner_text().strip()
                        quantidade = colunas[4].inner_text().strip()
                        valor_total = colunas[6].inner_text().strip()

                        status = ""
                        if len(colunas) >= 10:
                            status = colunas[9].inner_text().strip().upper()

                        if codigo and codigo != "Código":
                            if "CANCELAD" in status:
                                continue

                            itens.append({
                                "codigo_material": codigo,
                                "descricao": descricao,
                                "unidade": unidade,
                                "orgao": nome_secretaria,
                                "qtd_prevista": quantidade,
                                "valor_total_previsto": valor_total,
                                "tipo_doc": "SD",
                                "numero_doc": chave_doc,
                                "ata_id": doc.get("ata_id"),
                                "numero_ata": doc.get("numero_ata"),
                                "ano": doc.get("ano"),
                            })

                n = salvar_previstos("SD", chave_doc, itens)
                marcar_status(doc["id"], "processado")
                print(f"    -> {n} itens salvos com sucesso." if n else "    -> Nenhum item encontrado.")

                admc.go_back()
                admc.wait_for_selector("#P12001_SDNUM", timeout=45000)
                admc.locator("#P12001_SDNUM").fill("")
                admc.locator("#P12001_SDANO").fill("")

            except Exception as e:
                print(f"    [!] Erro ao processar a SD {chave_doc}: {e}")
                marcar_status(doc["id"], "erro")

        print("\n=== EXTRAÇÃO CONCLUÍDA ===")
        browser.close()


if __name__ == "__main__":
    rodar_extracao()
