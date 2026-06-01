@echo off
chcp 65001 >nul
echo ============================================================
echo      CONFIGURANDO ATALHO DO PAINEL DE ATAS (SJC)
echo ============================================================

:: 1. CAMINHOS DA REDE E DO ÍCONE
set "PASTA_REDE=G:\Administracao\Recursos_Materiais\Docs_Drm\Registro de Precos\Painel de Controle de Atas"
set "EXECUTAVEL=%PASTA_REDE%\run_painel.exe"
set "ICONE_REDE=%PASTA_REDE%\favicon.ico"

:: Nome que vai aparecer na Área de Trabalho
set "NOME_ATALHO=Painel de Controle de Atas.lnk"

:: Caminho da Área de Trabalho do usuário atual
set "DESKTOP_DIR=%USERPROFILE%\Desktop"

:: --- SOLUÇÃO PARA O ÍCONE BRANCO (Cópia Local) ---
:: Vamos criar uma pasta local oculta para guardar o ícone
set "PASTA_LOCAL_ICONE=%APPDATA%\PainelAtasSJC"
set "CAMINHO_ICONE_LOCAL=%PASTA_LOCAL_ICONE%\favicon.ico"

echo [+] Preparando ícone localmente para garantir exibição...
if not exist "%PASTA_LOCAL_ICONE%" mkdir "%PASTA_LOCAL_ICONE%"
copy /y "%ICONE_REDE%" "%CAMINHO_ICONE_LOCAL%" >nul

echo [+] Criando atalho na Área de Trabalho...

:: 2. COMANDO EM POWERSHELL (Agora apontando para o ícone LOCAL)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP_DIR%\%NOME_ATALHO%'); $Shortcut.TargetPath = '%EXECUTAVEL%'; $Shortcut.WorkingDirectory = '%PASTA_REDE%'; $Shortcut.IconLocation = '%CAMINHO_ICONE_LOCAL%'; $Shortcut.Description = 'Painel de Controle de Atas - SJC'; $Shortcut.Save()"

echo [+] Atalho criado com sucesso!
echo ============================================================
pause