chcp 65001
@echo off
SETLOCAL EnableDelayedExpansion

title GIT MANAGER - by JOGUS
color 0A

:: ===================== MENU =======================
:MENU
cls
echo.
echo ================================================
echo        🚀 GESTOR DE PROJETOS GIT
echo ================================================
echo.
echo [1] Iniciar repositório COM Git LFS (na pasta atual + GitHub)
echo [2] Iniciar repositório SEM Git LFS (na pasta atual + GitHub)
echo [3] Atualizar repositório atual (pull + commit + push)
echo [4] Configurar autenticação do GitHub CLI (gh auth login)
echo [5] Fazer logout do GitHub CLI e limpar credenciais Git
echo [6] Configurar ou editar nome/email do Git (git config)
echo [7] Ver Repositorio de trabalho Atual
echo [0] Sair
echo.
echo.
echo O SEU REPOSITORIO DE TRABALHO DESTA PASTA É:
git remote -v
echo.
echo.
set /p op="Escolha uma opcao: "

if "%op%"=="1" goto INICIAR_COM_LFS
if "%op%"=="2" goto INICIAR_SEM_LFS
if "%op%"=="3" goto ATUALIZAR_PROJETO
if "%op%"=="4" goto CONFIGURAR_GH
if "%op%"=="5" goto LOGOUT_GH
if "%op%"=="6" goto CONFIG_GIT_ID
if "%op%"=="7" goto REPO_LIST
if "%op%"=="0" exit
echo.
echo.
echo.
goto MENU

:: ===================== VERIFICAR GH CLI =======================
:VERIFICAR_GH
where gh >nul 2>&1
if errorlevel 1 (
    echo ❌ GitHub CLI não encontrada. Instalando via winget...
    winget install GitHub.cli -e --id GitHub.cli
    where gh >nul 2>&1
    if errorlevel 1 (
        echo ❌ Falha ao instalar GitHub CLI.
        pause
        goto MENU
    )
)
exit /b

:: ===================== VERIFICAR GIT LFS =======================
:VERIFICAR_LFS
git lfs --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Git LFS não encontrado. Tentando instalar com winget...
    winget install Git.GitLFS -e --id Git.GitLFS
    git lfs --version >nul 2>&1
    if errorlevel 1 (
        echo ❌ Git LFS ainda não foi instalado. Instale manualmente.
        pause
        goto MENU
    )
)
exit /b

:: ===================== LOGIN GH =======================
:CONFIGURAR_GH
cls
echo 🔐 Autenticando com GitHub CLI...
call :VERIFICAR_GH

gh auth status >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Ainda não autenticado. Iniciando login...
    gh auth login
) else (
    echo ✅ Já autenticado com o GitHub.
)

gh auth status
pause
goto MENU

:: ===================== LOGOUT =======================
:LOGOUT_GH
cls
echo 🔓 Fazendo logout e limpando credenciais...
call :VERIFICAR_GH

gh auth logout --hostname github.com

cmdkey /delete:git:https://github.com >nul 2>&1
cmdkey /delete:git:github.com >nul 2>&1

echo ✅ Logout completo.
pause
goto MENU

:: ===================== CONFIG GIT NAME/EMAIL =======================
:CONFIG_GIT_ID
cls
echo 🧾 CONFIGURAR OU EDITAR NOME E EMAIL PARA COMMITS (git config)
echo.

:: Nome
for /f "tokens=*" %%i in ('git config --global user.name 2^>nul') do set GITNAME=%%i
echo 🔍 Nome atual: %GITNAME%
set /p NOVONOME="Digite um novo nome ou pressione Enter para manter: "
if not "!NOVONOME!"=="" (
    git config --global user.name "!NOVONOME!"
    echo ✅ Nome atualizado para: !NOVONOME!
) else (
    echo ✅ Nome mantido: !GITNAME!
)

:: Email
for /f "tokens=*" %%i in ('git config --global user.email 2^>nul') do set GITEMAIL=%%i
echo 🔍 Email atual: %GITEMAIL%
set /p NOVOEMAIL="Digite um novo email ou pressione Enter para manter: "
if not "!NOVOEMAIL!"=="" (
    git config --global user.email "!NOVOEMAIL!"
    echo ✅ Email atualizado para: !NOVOEMAIL!
) else (
    echo ✅ Email mantido: !GITEMAIL!
)

echo.
echo 🔎 Configuração final:
git config --global user.name
git config --global user.email
pause
goto MENU

:: ===================== INICIAR COM GIT LFS =======================
:INICIAR_COM_LFS
cls
echo 🆕 Iniciando repositório COM Git LFS...
call :VERIFICAR_GH
call :VERIFICAR_LFS

gh auth status >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Não autenticado. Iniciando login...
    gh auth login
)

if not exist ".git" (
    git init
    git checkout -b main
)

if not exist README.md echo # Novo Projeto> README.md

set /p repo="Nome do repositório no GitHub: "
gh repo create "%repo%" --public --source=. --remote=origin
if errorlevel 1 (
    echo ❌ Falha ao criar repositório.
    pause
    goto MENU
)

git lfs install
git lfs track "*.exe"
git add .gitattributes

git add .
set /p msg="Mensagem do commit inicial: "
if "%msg%"=="" set msg=Primeiro commit
git commit -m "%msg%"
git push -u origin main

echo ✅ Repositório criado e enviado com LFS.
pause
goto MENU

:: ===================== INICIAR SEM GIT LFS =======================
:INICIAR_SEM_LFS
cls
echo 🆕 Iniciando repositório SEM Git LFS...
call :VERIFICAR_GH

gh auth status >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Não autenticado. Iniciando login...
    gh auth login
)

if not exist ".git" (
    git init
    git checkout -b main
)

if not exist README.md echo # Novo Projeto> README.md

set /p repo="Nome do repositório no GitHub: "
gh repo create "%repo%" --public --source=. --remote=origin
if errorlevel 1 (
    echo ❌ Falha ao criar repositório.
    pause
    goto MENU
)

git add .
set /p msg="Mensagem do commit inicial: "
if "%msg%"=="" set msg=Primeiro commit
git commit -m "%msg%"
git push -u origin main

echo ✅ Repositório criado e enviado com sucesso.
pause
goto MENU

:: ===================== ATUALIZAR PROJETO =======================
:ATUALIZAR_PROJETO
cls
echo 🔄 Atualizando repositório local...

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo ❌ Este diretório não é um repositório Git válido.
    pause
    goto MENU
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
    set /p url="Digite a URL do repositório remoto: "
    git remote add origin %url%
)


git pull origin main

git add -A
set /p msg="Mensagem do commit: "
if "%msg%"=="" set msg=Atualização
git commit -m "%msg%"
git push origin main

echo ✅ Repositório atualizado com sucesso!
pause
goto MENU

:: ===================== VER REPO ATUAL =======================
:REPO_LIST
cls
echo O SEU REPOSITORIO DE TRABALHO ATUAL É:
git remote -v
pause
goto MENU
