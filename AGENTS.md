# Repository Guidelines

## Project Structure & Module Organization

- `copy.py` contains the Tkinter interface, rclone command construction, progress parsing, and process cancellation.
- `copy.spec` is the PyInstaller recipe and bundles `rclone.exe`.
- `rclone.exe` is the Windows runtime dependency and is tracked through Git LFS.
- `build/` and `dist/` contain packaging outputs. Treat their contents as generated; make source changes in `copy.py` or `copy.spec`.
- `Git Automação nao cria pasta de projeto.bat` is a separate Git/GitHub maintenance helper, not application code.
- No automated test directory or asset directory currently exists.

## Build, Test, and Development Commands

| Task | Command |
|---|---|
| Run the GUI from source | `python copy.py` |
| Check Python syntax | `python -m py_compile copy.py` |
| Build the Windows executable | `pyinstaller --clean copy.spec` |
| Run the packaged application | `.\dist\copy.exe` |

Use the `pyinstaller` executable, not `python -m PyInstaller`: the local `copy.py` name can shadow Python's standard-library `copy` module during module-based startup. Running transfers requires a valid `%APPDATA%\rclone\rclone.conf` and an accessible `rclone.exe`.

## Coding Style & Naming Conventions

Use four-space indentation and PEP 8 spacing. Name functions, methods, and local variables in `snake_case`; use `PascalCase` for classes and `UPPER_SNAKE_CASE` for compiled patterns or constants. Keep UI callbacks small, prefix internal callbacks with `_`, and pass subprocess arguments as lists rather than shell-formatted strings where possible. Preserve UTF-8 for Portuguese labels.

## Testing Guidelines

There is no configured test framework or coverage threshold. At minimum, run the syntax check and manually exercise local-to-remote, remote-to-local, remote-to-remote, progress updates, and cancellation. New automated tests should live in `tests/`, use names such as `test_parse_size.py`, and mock `subprocess` so tests never contact real remotes.

## Commit & Pull Request Guidelines

The history currently contains only `Commit inicial`, so no formal convention is established. Use short imperative commits, for example `Corrige cancelamento da cópia`. Pull requests should describe behavior changes, list verification steps, link relevant issues, and include screenshots for UI changes. Call out modified executables or Git LFS changes explicitly.

## Security & Configuration

Never commit `rclone.conf`, remote credentials, tokens, or local paths. Review rclone flags carefully because copy operations affect external storage.


caso tenha qualquer duvida use a propria documentação do rclone: https://rclone.org/docs/
