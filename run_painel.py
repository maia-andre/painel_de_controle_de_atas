import sys
import traceback
import streamlit.web.cli as stcli

# --- GANCHOS ---
import pandas
import numpy
import plotly
import plotly.graph_objects as go

if __name__ == "__main__":
    try:
        sys.argv = ["streamlit", "run", "app.py", "--global.developmentMode=false"]
        sys.exit(stcli.main())
    except Exception as e:
        print("=== DEU ERRO NA INICIALIZAÇÃO ===")
        traceback.print_exc()
        input("\nPressione ENTER para fechar essa janela...")