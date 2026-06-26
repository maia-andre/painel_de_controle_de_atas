# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Painel de Controle de Atas** — a financial analytics dashboard for tracking consumption of municipal Purchase Price Registration Agreements (Atas de Registro de Preços) in São José dos Campos, SP, Brazil. The system automates data collection from the eSJC/ADMC government portal and presents consumption metrics to procurement staff.

## Running the Application

```bash
# Install dependencies (no requirements.txt — install manually)
pip install streamlit pandas numpy plotly openpyxl playwright
playwright install chromium

# Run the dashboard
streamlit run app.py

# Run data collection bots (prompts for portal CPF/password at runtime)
python bot_etps.py   # Scrapes ETP (Technical Study Process) item data
python bot_sd.py     # Scrapes SD (Expense Request) financial data

# Build standalone Windows executable
pyinstaller --onefile run_painel.py
```

No `requirements.txt` exists — dependencies are inferred from imports.

## Data Files & Git Ignored Files

Production data files are **gitignored**. Users copy the templates from `templates/` to the project root and populate them:

| File (root) | Template | Purpose |
|---|---|---|
| `base_etps.csv` | `templates/base_etps_template.csv` | Queue of ETP numbers to scrape |
| `base_sds.xlsx` | `templates/base_sds_template.xlsx` | Ata metadata linked to SDs — **objeto + validity dates** (`Assinatura da Ata`, `Vigência`, `Ata Prorrogada`). Only atas present here are treated as "managed". |
| `base_rcaf.csv` | `templates/base_rcaf_template.csv` | RC/AF actual consumption data |
| `previstos_dashboard.csv` | `templates/previstos_dashboard_template.csv` | Consolidated forecasted items |
| `base_homologados.csv` | `templates/base_homologados_template.csv` | Homologated (awarded) items — filters out failed (`fracassado`) forecast items and supplies `Fornecedor`/`Marca` |

The bots maintain checkpoint logs (`log_etps_processados.txt`, `log_sds_processadas.txt`) to avoid re-scraping on restart — also gitignored.

## Architecture

### Data Flow

```
[bot_etps.py] ──→ base_etps.csv ──┐
                                   ├──→ [app.py] ──→ Streamlit Dashboard
[bot_sd.py]   ──→ base_sds.xlsx ──┘
                                   
base_rcaf.csv (manual/external export) ──→ [app.py]
previstos_dashboard.csv (generated from ETPs+SDs) ──→ [app.py]
```

### Key Modules

- **`app.py`** — Main Streamlit app. Loads and joins all data sources, applies business logic, renders UI (KPI cards, filterable tables, Plotly chart, pivot table).
- **`bot_etps.py`** — Playwright bot; logs into portal, navigates ETP menus, extracts item details (material code, description, unit, quantity). Checkpoint-aware.
- **`bot_sd.py`** — Playwright bot; scrapes Expense Requests with financial metrics. Checkpoint-aware.
- **`run_painel.py`** — Thin launcher used by PyInstaller to bundle into `.exe`.

### Core Business Logic (app.py)

1. **Contractual capping:** Consumption displayed to users is capped at 100% of forecast for compliance. Raw overconsumption is tracked separately to surface critical/exhausted status (≥90% = critical, ≥100% = exhausted).

2. **Service items (SV unit):** Items with unit `SV` switch from quantity-based to financial-value (R$) tracking automatically.

3. **Unit price:** Derived exclusively from RC (Requisição de Compra) records. Items without RCs display `"-"`.

4. **AF cancellation:** `CANCELADA` AFs are subtracted from totals before aggregation.

5. **Relational join key:** `(Nº Ata, Ano Ata, Material Code, Secretaria)` — all four fields must match to link planned vs. actual data.

6. **Ata validity scoping & expiry alerts (dropdown + top cards):** The ata selector lists only *managed* atas — those present in `base_sds.xlsx` (which carry `Assinatura`/`Vigência` dates) **and** currently within their validity window. This deliberately hides the ~500 consumption-only atas (e.g. the Health dept, which has its own procurement and floods `base_rcaf.csv`) that have no metadata. An "Incluir atas vencidas" checkbox re-includes expired managed atas; the list is sorted **numerically** by ata number. Three clickable alert cards at the top (`Atas Vigentes` / `A Vencer ≤ DIAS_ALERTA_VENCIMENTO days` / `Vencidas`) are computed from the validity dates and open `@st.dialog` modals listing each ata (número, descrição, início, término, dias). The whole block is guarded by a `tem_vigencia` flag and **degrades safely** to the legacy "show all atas" behavior if `base_sds` metadata is absent.

   - *Clickable-card technique:* HTML markdown cards can't trigger Python callbacks, so the cards are `st.button(..., width="stretch")` styled as cards via CSS scoped to the per-key `.st-key-card_*` class (two-line label renders as two `<p>`: title + value). Reusable pattern for making cards interactive in Streamlit ≥1.31 (`st.dialog`).

### Column Normalization

Source files have inconsistent column names (e.g., `"N Ata"` / `"N° Ata"` / `"Nº Ata"`). `app.py` normalizes all column names via rename dictionaries at load time. When adding new data sources, follow this same pattern in `carregar_dados()`.

### Secretaria Code Mapping

Department codes are mapped to names in `app.py` (e.g., `5=GP`, `10=SG`, `15=SAJ`). Update this dictionary when new secretarias are added.

## Encoding & Locale

- Files may be UTF-8 or Latin-1; `carregar_dados()` tries UTF-8 first, falls back to `latin-1`.
- Brazilian number formatting throughout: decimal separator `,`, thousands separator `.` (e.g., `1.234,56`). All `pd.to_numeric()` calls strip locale separators before conversion.
