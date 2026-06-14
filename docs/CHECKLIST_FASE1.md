# ✅ Checklist de verificação manual — Fase 1

Lista do que precisa ser validado **na máquina local** (o ambiente da sessão de
desenvolvimento não tem os arquivos de produção nem o banco). Marque os itens
conforme for testando.

Branch: `migration-fase-1` (commits A→E + ajuste de portas).

---

## 0. Pré-requisitos / setup
- [ ] `git checkout migration-fase-1 && git pull`
- [ ] `cp .env.example .env` e editar: `POSTGRES_PASSWORD`, `PORTAL_CPF`, `PORTAL_SENHA`
- [ ] Confirmar portas livres: `POSTGRES_HOST_PORT` (default **5434**) e `APP_PORT` (default **8501**). Se 5434 também estiver em uso, troque **e** ajuste a porta na `DATABASE_URL` pro mesmo número.
- [ ] Colocar os arquivos legados reais na **raiz**: `base_rcaf.csv`, `base_sds.xlsx`, `previstos_dashboard.csv`

## 1. Banco + carga (resolve dúvidas em aberto)
- [ ] `docker compose up -d db` — sobe e aplica `db/schema.sql` sem erro
- [ ] `python scripts/load_csv_to_db.py --profile` — **o mais importante**:
  - [ ] Conferir os **valores reais de `Status RC` / `Status AF`** e se o filtro por prefixo `CANCELAD` cobre todos
  - [ ] Contagem de itens **SV** e de linhas **sem ata** (prováveis ETP) faz sentido
- [ ] `python scripts/load_csv_to_db.py` — carga + validação dá **OK** (linhas e somas arquivo vs banco)
- [ ] **Números BR**: o parsing de quantidade foi corrigido (`"1.500"` antes virava `1.5`); validar que quantidades com milhar vêm corretas (pode mudar valores vs painel antigo)

## 2. Dashboard (paridade com o painel antigo)
- [ ] `docker compose up -d --build app` (1ª vez baixa o Chromium) → abrir `http://localhost:8501`
- [ ] Selecionar uma ata conhecida e comparar com o painel antigo:
  - [ ] **Nome da secretaria** no formato `60 - SS` (o join depende disso)
  - [ ] KPIs, Resumo Geral, Detalhamento e gráfico batendo
  - [ ] **Itens "não previstos"** agora **não** contam como esgotados — confirmar que é o desejado
  - [ ] **Valor unitário** só vem da RC (itens sem RC mostram `-`); valor da SD não é mais usado
  - [ ] Ata prorrogada: filtro de período (Ano 1 / Ano 2) funcionando com datas do banco
- [ ] Se o `st.data_editor` reclamar de `width="stretch"`, avisar para trocar por `use_container_width=True` (depende da versão do Streamlit)

## 3. Telas de Administração
- [ ] **Secretarias**: editar/adicionar/remover e salvar; remover uma em uso deve **bloquear** com aviso (FK)
- [ ] **Atas e Documentos** → aba Atas: criar/editar ata (datas + checkbox prorrogada) e salvar
- [ ] Aba Documentos: escolher ata, **enfileirar** uma SD e um ETP → aparecem como 🟡 pendente

## 4. Bots (precisa do portal real)
- [ ] `docker compose run --rm app python bot_sd.py`:
  - [ ] Login com credenciais do `.env` (headless)
  - [ ] **Seletores Playwright ainda batem** com o portal atual
  - [ ] SD enfileirada vira 🟢 processado e itens aparecem em `previstos` / no Dashboard
- [ ] `docker compose run --rm app python bot_etps.py` — idem para ETP
- [ ] **Reenfileirar** numa tela (volta a pendente) e rodar o bot de novo → confirmar idempotência (não duplica em `previstos`)
- [ ] Lembrete: a fila de **ETP** só existe depois de cadastrar/enfileirar via tela

## 5. Backup
- [ ] `./scripts/backup.sh` gera o `.sql`
- [ ] (Opcional) testar restore num banco limpo (comando no README)

## 6. Decisões pendentes
- [ ] PR da `migration-fase-1` — definir a base (`migration` ou `main`)
- [ ] Deploy na VM da intranet — mesmo compose, ajustar `.env` e backup/porta com a TI
