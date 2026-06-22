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
| `base_sds.xlsx` | `templates/base_sds_template.xlsx` | Ata metadata linked to SDs |
| `base_rcaf.csv` | `templates/base_rcaf_template.csv` | RC/AF actual consumption data |
| `previstos_dashboard.csv` | `templates/previstos_dashboard_template.csv` | Consolidated forecasted items |

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

### Column Normalization

Source files have inconsistent column names (e.g., `"N Ata"` / `"N° Ata"` / `"Nº Ata"`). `app.py` normalizes all column names via rename dictionaries at load time. When adding new data sources, follow this same pattern in `carregar_dados()`.

### Secretaria Code Mapping

Department codes are mapped to names in `app.py` (e.g., `5=GP`, `10=SG`, `15=SAJ`). Update this dictionary when new secretarias are added.

## Encoding & Locale

- Files may be UTF-8 or Latin-1; `carregar_dados()` tries UTF-8 first, falls back to `latin-1`.
- Brazilian number formatting throughout: decimal separator `,`, thousands separator `.` (e.g., `1.234,56`). All `pd.to_numeric()` calls strip locale separators before conversion.
