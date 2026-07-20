@echo off
echo [INFO] Controllo aggiornamenti in corso...

:: 1. CONFIGURAZIONE REPOSITORY
set TOKEN=IL_TUO_TOKEN_GITHUB
set REPO_URL=https://%TOKEN%@github.com/Marcu08/App_Gestionale.git

if not exist .git (
    echo [INFO] Inizializzazione repository locale...
    git init
    git remote add origin %REPO_URL%
)

echo [INFO] Sincronizzazione con il server...
:: Scarica i dati dal server senza unirli ancora
git fetch %REPO_URL% main

:: FORZATURA (Risolve l'errore dell'untracked file sovrascrivendolo)
:: Nota: Questo allinea la tua cartella locale esattamente come su GitHub
git reset --hard FETCH_HEAD

echo.
echo [INFO] Avvio di Logistic Launcher...

:: 2. AVVIO DEL FILE CORRETTO
:: Se launcher.py si trova dentro una sottocartella, togli il "::" dalla riga sotto:
:: cd App_Gestionale

if exist launcher.py (
    python launcher.py
) else (
    echo [ERRORE] Impossibile trovare il file launcher.py! Controlla il percorso.
)

pause