# AURIX — Your World, Connected.

Local-first personal digital workspace for Windows. **v1.0:** Home, Memory, Find, Flow, Connect, Activity, Settings.

Everything stays on your computer (SQLite). No account, no internet, no paid services.

## Setup (Windows 10/11, VS Code terminal, Python 3.10+)
    python -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt

## Run
    python main.py          (or double-click run_aurix.bat)

## Test
    python -m pytest tests -v

## Build AURIX.exe
Double-click `build_windows.bat` (needs the setup above to have worked once). It runs the tests, then creates
`dist\AURIX\AURIX.exe` and `dist\AURIX-Windows.zip`. Upload that zip in the website admin panel.
(No Windows PC? Push this folder to GitHub and run the "Build AURIX for Windows" action.)

## Features
| Section | What it does |
|---|---|
| Home | Search, quick actions, recent projects/files, important notes, activity, suggestions, deadline warnings |
| Memory | Notes and ideas with tags, importance, search, edit, delete |
| Find | Keyword search over folders *you* choose (names, sizes, dates only), filters, descriptions, tags. Not AI. |
| Flow | Projects, tasks (To do / Doing / Done), deadlines, progress, attached notes/files, project history |
| Connect | Interactive graph of files, projects, notes, ideas, tasks. Drag, zoom, select, connect, disconnect |
| Activity | Timeline with filters. Only in-app actions are recorded; you can pause or clear it |
| Settings | Data location, indexed folders, privacy, backup & restore, delete-all, about |

## Privacy
AURIX never scans your PC on its own, never opens file contents, never uploads anything. Data lives in
`%APPDATA%\AURIX\aurix.db` (movable in Settings).

## Honest limits
* Search is keyword search with a few type words ("slides" → .pptx). It is not semantic/AI search yet;
  `core/search_engine.py` is the place to add a local semantic engine later.
* Only the light brand theme exists.
* Windows is the tested target. The code is cross-platform PySide6 but has not been tested elsewhere.
