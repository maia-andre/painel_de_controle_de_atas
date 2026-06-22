# 🧊 bot_rcaf — Próximas Fases (CONGELADO)

> **Status:** automação em **produção desde 18/06/2026**, rodando **manualmente**.
> As Fases B e C abaixo estão **parqueadas** — retomar quando voltar a este projeto.

---

## ✅ O que já está pronto (estado atual)

- `bot_rcaf.py` baixa RC/AF do portal **eSJC/ADMC** e faz *upsert* em `base_rcaf.csv`.
- Roda **manual** numa janela interativa do PowerShell (pede CPF/senha no terminal):
  ```powershell
  cd "G:\Administracao\Recursos_Materiais\Docs_Drm\Registro de Precos\Painel de Controle de Atas"
  python bot_rcaf.py
  ```
- Interpretador: **Python global do scoop** — `D:\Users\andre.maia\scoop\apps\python312\current\python.exe` (sem venv).
- Export do portal é **Latin-1**; relatório usado é **"1. Relatório completo"** (`value=5495497332881863449`).
- A *race condition* do IRR do APEX (revertia para o relatório "Primário", sem `Val.Unit RC`) já está resolvida em `garantir_relatorio_completo()` — seleciona e revalida o `<select>` até a seleção ficar estável.
- Trava de segurança: se faltarem as colunas `Qtd RC`/`Val.Unit RC`, o bot **aborta sem tocar na base**.
- Checkpoint por data: `log_rcaf_ultima_execucao.txt` (janela de re-consulta de 30 dias).
- Backup pré-cutover preservado: `base_rcaf.bak.csv`.

---

## 🔜 Fase B — rodar sem supervisão (credenciais + robustez)

Objetivo: deixar o bot pronto para execução **não interativa** (pré-requisito da Fase C).

- [ ] Tirar CPF/senha do `input()`/`getpass`:
  - Opção 1: arquivo `.env` (fora do Git) lido no início.
  - Opção 2: **Windows Credential Manager** (mais seguro p/ máquina compartilhada).
  - **Fallback:** se a credencial não-interativa não existir, cair no `input()` atual.
- [ ] Tornar `headless` configurável (rodar sem abrir o navegador no modo agendado).
- [ ] Logging em arquivo (data/hora, nº de linhas novas/atualizadas, erros).
- [ ] *Retries* nos passos flaky (login, abertura do ADMC, menu Ações).

## 🔜 Fase C — agendamento diário

- [ ] **Windows Task Scheduler** numa máquina **sempre ligada e DENTRO da rede da prefeitura**.
  - ⚠️ O portal `sv03.sjc.sp.gov.br` é **interno** — nuvem/agente remoto está **descartado**.
- [ ] Usar o Python global do scoop (caminho acima).
- [ ] **Depende da Fase B** (credenciais não interativas).

---

## ♻️ Rollback / retomada

- **Rollback da base:** `Copy-Item base_rcaf.bak.csv base_rcaf.csv -Force` e voltar `MODO_TESTE = True`.
- **Contexto registrado na memória do Claude Code:** `rcaf-bot-cutover-plan`, `rcaf-bot-scheduling-internal-only`.
