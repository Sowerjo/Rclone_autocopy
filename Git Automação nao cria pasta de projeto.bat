@echo off
SETLOCAL EnableDelayedExpansion

title GIT MANAGER - by JOGUS
color 0A

:: ===================== MENU =======================
:MENU
cls
echo.
echo ================================================
echo        🚀 GESTOR DE PROJETOS GIT - JOGUS
echo ================================================
echo.
echo [1] Iniciar repositório COM Git LFS (na pasta atual + GitHub)
echo [2] Iniciar repositório SEM Git LFS (na pasta atual + GitHub)
echo [3] Atualizar repositório atual (pull + commit + push)
echo [4] Configurar autenticação do GitHub CLI (gh auth login)
echo [0] Sair
echo.
set /p op="Escolha uma opcao: "

if "%op%"=="1" goto INICIAR_COM_LFS
if "%op%"=="2" goto INICIAR_SEM_LFS
if "%op%"=="3" goto ATUALIZAR_PROJETO
if "%op%"=="4" goto CONFIGURAR_GH
if "%op%"=="0" exit
goto MENU

:: ===================== FUNÇÃO: VERIFICAR GH CLI =======================
:VERIFICAR_GH
where gh >nul 2>&1
if errorlevel 1 (
    echo.
    echo ❌ GitHub CLI nao encontrada. Instalando via winget...
    winget install GitHub.cli -e --id GitHub.cli
    echo 🔁 Verificando novamente...
    where gh >nul 2>&1
    if errorlevel 1 (
        echo ⚠️ Falha ao instalar GitHub CLI. Instale manualmente e tente novamente.
        pause
        goto MENU
    )
)
exit /b

:: ===================== VERIFICAR GIT LFS =======================
:VERIFICAR_LFS
echo 🔍 Verificando se Git LFS está instalado...
git lfs --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Git LFS nao encontrado. Tentando instalar com winget...
    winget install Git.GitLFS -e --id Git.GitLFS
    echo 🔁 Revalidando Git LFS...
    git lfs --version >nul 2>&1
    if errorlevel 1 (
        echo ⚠️ Git LFS ainda nao foi encontrado. Instale manualmente e tente novamente.
        pause
        goto MENU
    )
)
exit /b

:: ===================== CONFIGURAR GH AUTH LOGIN =======================
:CONFIGURAR_GH
cls
echo.
echo 🔐 CONFIGURANDO AUTENTICACAO COM GITHUB CLI (gh auth login)
echo.

call :VERIFICAR_GH

echo Verificando status atual...
gh auth status >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Ainda nao autenticado. Iniciando login...
    gh auth login
) else (
    echo ✅ Ja autenticado com o GitHub!
)

echo.
echo 🔍 Exibindo status atual:
gh auth status

pause
goto MENU

:: ===================== INICIAR COM GIT LFS =======================
:INICIAR_COM_LFS
cls
echo.
echo 🆕 INICIAR REPOSITORIO COM GIT LFS (pasta atual)
echo.

call :VERIFICAR_GH
call :VERIFICAR_LFS

:: Iniciar Git apenas se não estiver inicializado
if not exist ".git" (
    git init
    git checkout -b main
) else (
    echo ℹ️ Repositório Git já existente. Pulando git init...
)

:: Criar README se não existir
if not exist README.md echo # Novo Projeto> README.md

:: Nome do repositório no GitHub
set /p repo="Nome do repositório no GitHub: "

:: Criar repositório no GitHub
echo 🌐 Criando repositório no GitHub...
gh repo create %repo% --public --source=. --remote=origin
if errorlevel 1 (
    echo ❌ Falha ao criar repositório no GitHub.
    echo Verifique se você está autenticado com: gh auth login
    pause
    goto MENU
)

:: Ativar Git LFS
git lfs install
git lfs track "*.exe"
git add .gitattributes

:: Commit inicial
git add .
set /p msg="Mensagem do commit inicial: "
if "%msg%"=="" set msg=Primeiro commit
git commit -m "%msg%"
git push -u origin main

echo.
echo ✅ Repositório criado no GitHub e enviado com Git LFS.
pause
goto MENU

:: ===================== INICIAR SEM GIT LFS =======================
:INICIAR_SEM_LFS
cls
echo.
echo 🆕 INICIAR REPOSITORIO SEM GIT LFS (pasta atual)
echo.

call :VERIFICAR_GH

:: Iniciar Git apenas se necessário
if not exist ".git" (
    git init
    git checkout -b main
) else (
    echo ℹ️ Repositório Git já existente. Pulando git init...
)

:: Criar README se não existir
if not exist README.md echo # Novo Projeto> README.md

:: Nome do repositório
set /p repo="Nome do repositório no GitHub: "

:: Criar repositório remoto
echo 🌐 Criando repositório no GitHub...
gh repo create %repo% --public --source=. --remote=origin
if errorlevel 1 (
    echo ❌ Falha ao criar repositório no GitHub.
    echo Verifique se você está autenticado com: gh auth login
    pause
    goto MENU
)

:: Commit inicial
git add .
set /p msg="Mensagem do commit inicial: "
if "%msg%"=="" set msg=Primeiro commit
git commit -m "%msg%"
git push -u origin main

echo.
echo ✅ Repositório criado e enviado com sucesso!
pause
goto MENU

:: ===================== ATUALIZAR PROJETO =======================
:ATUALIZAR_PROJETO
cls
echo.
echo 🔄 ATUALIZAR PROJETO GIT EXISTENTE (pasta atual)
echo.

:: Verificar se é repositório Git
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo ❌ Este diretório não é um repositório Git válido.
    pause
    goto MENU
)

:: Verifica remote origin
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    set /p url="Repositorio remoto nao configurado. Digite a URL do GitHub: "
    git remote add origin %url%
)

:: Git LFS se estiver rastreando
git lfs install
git lfs track "*.exe"
git add .gitattributes

:: Pull antes de commit
echo 🔽 Fazendo pull...
git pull origin main

:: Adiciona e commita mudanças
git add -A
set /p msg="Mensagem do commit: "
if "%msg%"=="" set msg=Atualização
git commit -m "%msg%"

:: Push final
git push origin main

echo.
echo ✅ Projeto atualizado com sucesso!
pause
goto MENU
