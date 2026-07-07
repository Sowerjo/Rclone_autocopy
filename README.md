# Backup Manager

Aplicação desktop em PySide6 para executar cópias com `rclone` entre pasta local e remote, remote para local e remote para remote.

## Requisitos

- Python 3.12 ou superior
- PySide6 instalado no ambiente
- `rclone.exe` presente na raiz do projeto
- `rclone.conf` configurado no Windows
- Git LFS para clonar os binários versionados em `.exe`

## Execução

```powershell
python .\copy.py
```

## Build do executável

```powershell
pyinstaller --clean copy.spec
```

## Build do instalador Windows

Requer Inno Setup 6 instalado.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\build_release.ps1
```

## Estrutura principal

- `copy.py`: aplicação principal
- `copy.spec`: build local com PyInstaller
- `installer/BackupManager.iss`: script do instalador Inno Setup
- `installer/build_release.ps1`: pipeline de empacotamento
- `assets/`: ícones da aplicação
- `rclone.exe`: binário do rclone distribuído com o app

## Observações

- O app depende de um `rclone.conf` válido no ambiente do usuário.
- Arquivos de build, cache, logs, testes temporários e configurações locais não devem ser versionados.
- Não versionar credenciais, tokens ou arquivos de configuração reais do rclone.
