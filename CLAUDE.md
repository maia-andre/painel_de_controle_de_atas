# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Painel de Controle de Atas** is a Streamlit dashboard for the DRM (Departamento de Recursos Materiais) of the São José dos Campos city government. It monitors *Atas de Registro de Preços* (price-registration agreements) by cross-referencing **planned** procurement (ETP / SD — preliminary studies and expense requests) against **actual** financial execution (RC / AF — purchase requisitions and supply authorizations).

The codebase is small and entirely in **Portuguese** (UI strings, variable names, comments, column headers). Keep new code in Portuguese to match.

## Architecture

There are three independently-runnable Python entry points and a data pipeline that connects them through CSV/XLSX files in the repo root:

```
bot_etps.py ─┐                          ┌─> previstos_dashboard.csv ─┐
bot_sd.py  ──┴─(Playwright scrape)──────┘                            ├─> app.py (Streamlit UI)
                                          base_rcaf.csv ──────────────┤
                                          base_sds.xlsx ──────────────┘
```

- **`app.py`** — the dashboard. Reads three root-level data files, normalizes/merges them, and renders KPIs, tables, a Plotly chart, and a pivot. Run standalone; no internal imports from the bots.
- **`bot_etps.py`** / **`bot_sd.py`** — Playwright (`headless=False`, Chromium) scrapers that log into the eSJC/ADMC portal (`https://sv03.sjc.sp.gov.br/eSJC`), navigate the menu tree, and append rows to `previstos_dashboard.csv`. They prompt for CPF/password via `input()`/`getpass` at the terminal. Each writes a checkpoint file (`log_etps_processados.txt` / `log_sds_processadas.txt`) of already-processed keys to make reruns idempotent and resumable after crashes.
- **`run_painel.py`** — PyInstaller entry wrapper. Invokes `streamlit run app.py` programmatically; the explicit `import pandas/numpy/plotly` lines are deliberate hooks so PyInstaller bundles them into `run_painel.exe`. Do not remove them.

### Key conventions in `app.py`

These patterns recur and any change must respect them:

- **Fuzzy column renaming.** Source files have inconsistent/dirty headers, so columns are matched by substring (e.g. `if 'Qtd' in col and 'RC' in col`) and renamed to canonical names like `Material RC`, `Secr. RC`, `Qtde RC`. When adding a column, extend the rename loops in `carregar_dados()` rather than assuming exact header names.
- **Brazilian number/locale handling.** Numeric strings use `.` as thousands separator and `,` as decimal. Parsing strips `.` then swaps `,`→`.` before `pd.to_numeric`. Display uses `formatar_brl()` which reverses this. Dates are `dayfirst=True`.
- **Ata key normalization.** `Nº Ata` and `Ano Ata` are the join keys everywhere; both are stripped and have leading zeros removed (`str.replace(r'^0+', '')`). Atas are matched on this `(num, ano)` pair across all three sources.
- **`@st.cache_data`** decorates `carregar_dados()` — editing data files at runtime requires clearing the Streamlit cache (or rerun) to see changes.

### Core business rules (do not silently break these)

- **Contractual capping (100%).** In the consolidated *Resumo Geral* (`df_geral`), realized consumption is capped at the planned ceiling (`np.minimum`) and saldo floored at 0. The *uncapped* real value is preserved as `Métrica RC Real` and is what drives the **critical (≥90%)** and **exhausted (≥100%)** KPI counts.
- **Service items (`Unidade de Medida == 'SV'`).** For these, the planned/realized metric switches from quantity to financial value (`Valor Total Previsto` / `Valor Total RC`). This is the `Métrica Prevista` / `Métrica RC` `np.where` logic.
- **Unit price = price actually practiced.** `Vlr Unitário` comes only from the RC execution (`Valor Unit. RC`), never the planned value. Items with no RC show `-`.
- **"Não Previsto" rows** (consumed but never planned: `Métrica Prevista == 0 and Métrica RC > 0`) get a red bar and red row highlight.
- **Cancelled records are dropped:** RCAF rows where `Status AF == 'CANCELADA'`, and scraped items whose status contains `CANCELAD`.
- **Prorrogated atas** (`Prorrogada == 'S'`) expose a period radio (Completo / Ano 1 / Ano 2) that splits `Data RC` at the vigência midpoint; default is Ano 2.

## Running & Development

There is **no `requirements.txt`** in the repo (the README references one, but it is absent). Install dependencies manually:

```bash
pip install streamlit pandas numpy plotly openpyxl playwright
playwright install chromium   # only needed to run the bots
```

Run the dashboard:

```bash
streamlit run app.py          # serves on http://localhost:8501
```

Run the scrapers (interactive — opens a visible browser, prompts for CPF/password):

```bash
python bot_etps.py
python bot_sd.py
```

There are **no tests, linters, or CI** configured in this repository.

### Data files (required at runtime, git-ignored)

`app.py` expects these in the repo root; all are listed in `.gitignore` because they contain real procurement data:

| File | Format | Produced by |
|------|--------|-------------|
| `base_rcaf.csv` | `;`-delimited (latin-1 fallback) | manual export |
| `base_sds.xlsx` | Excel | manual; supplies ata metadata + SD queue for `bot_sd.py` |
| `previstos_dashboard.csv` | `;`-delimited | the two bots |
| `base_etps.csv` | `;`-delimited | manual; ETP queue for `bot_etps.py` |

The committed **`templates/`** folder holds empty header-only versions of each. To set up: copy a template, drop the `_template` suffix, place it in the repo root, then fill it. Never commit the real (root) data files.

## Distribution

The intended deployment is a standalone PyInstaller build (`run_painel.exe`) placed on a network share, with `Instalador.bat` creating a Windows desktop shortcut. End users do not install Python. Build artifacts (`build/`, `dist/`, `*.spec`, the `.exe`) are git-ignored.
