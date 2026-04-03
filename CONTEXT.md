# CONTEXT.md — reshade-shader-manager (RSM)

**Purpose:** Handoff document for humans and AI sessions. Read this first, then `PROJECT_SPEC.md` and `IMPLEMENTATION_PLAN.md` for full detail.

---

## What this project is

**reshade-shader-manager (RSM)** is a standalone Linux application (Python backend + GTK 4 UI) that:

- Installs / removes / checks **ReShade** into a user-chosen game directory (Wine/Proton-oriented).
- Manages **Git-based shader repositories** (clone/pull, catalog merge).
- **Projects** enabled repos into `<game>/reshade-shaders/` using **directory symlinks** (no per-file symlinks, no flattening, no renaming shader files).

It is **inspired by** SteamTinkerLaunch (STL) behavior only; it does **not** depend on STL or replicate its shell architecture.

---

## Full architecture

### Layers

1. **Core (`reshade_shader_manager/core/`)**  
   Filesystem, network, git, manifest I/O, ReShade download/extract/install, INI patching, PCGW fetch/parse, symlink projection. **No GTK imports.**

2. **UI (`reshade_shader_manager/ui/`)**  
   Thin GTK 4 layer: `MainWindow`, `ShaderRepoWindow`, `LogPanel` + logging handler. Long work runs on **background threads**; UI updates via `GLib.idle_add`.

3. **Entry (`reshade_shader_manager/main.py`)**  
   `gi.require_version("Gtk", "4.0")` then `Gtk.Application` → `MainWindow`.

### Data flow (conceptual)

- **Single source of truth:** JSON metadata under `~/.config/.../games/<game-id>.json` (`GameManifest`), not marker files in the game tree.
- **Filesystem** (DLLs, symlinks, `ReShade.ini`) is **derived** from manifest + user actions; repair/drift is informational only unless code explicitly rescans (minimal in v0.1).

### XDG layout

| Location | Contents |
|----------|----------|
| `~/.config/reshade-shader-manager/` | `config.json`, `repos.json` (user repos only), `games/<sha256-of-game_dir>.json` |
| `~/.local/share/reshade-shader-manager/` | `repos/<id>/` (git clones), `reshade/downloads/`, `reshade/extracted/<version>/`, `logs/` |
| `~/.cache/reshade-shader-manager/` | `pcgw_repos.json`, `reshade_latest_cache.json` |

### Per-game tree (managed)

- `<game>/ReShade.ini` — RSM patches only `EffectSearchPaths` / `TextureSearchPaths` under `[GENERAL]` (Windows-style `.\reshade-shaders\...**`).
- Proxy DLL(s) + optional `d3dcompiler_47.dll` — tracked in `installed_reshade_files`.
- `reshade-shaders/Shaders/<repo-id>` → symlink to `.../share/.../repos/<repo-id>/Shaders` (same for `Textures/`). **Absolute** symlink targets; manifest stores **absolute paths to the symlink inodes** under the game dir (not `resolve()` through the link).

---

## Key design decisions

1. **Metadata-only state** — No `enabled/` marker files; `enabled_repo_ids` + `symlinks_by_repo_id` in manifest.
2. **`symlinks_by_repo_id`** — Map `repo_id → [absolute symlink paths]` for precise disable/remove.
3. **Built-in repos in code** — `repos.BUILTIN_REPOS`; `repos.json` holds **user** entries only; PCGW merged at runtime from cache.
4. **Remove ReShade** — Deletes **only** `installed_reshade_files`; does **not** remove shader symlinks, `enabled_repo_ids`, or `ReShade.ini` by default.
5. **One active ReShade runtime per game (v0.1)** — On **install**, previously tracked DLLs are removed from disk before copying new ones; `installed_reshade_files` is **replaced** (no multi-runtime merge).
6. **`latest` version** — Resolved from GitHub **tags** (`/repos/crosire/reshade/tags?per_page=100`), highest semver (not `releases/latest`, which 404’d). On failure, use `~/.cache/.../reshade_latest_cache.json`; else require explicit version.
7. **DX8** — Present in UI/model; **not implemented** in v0.1 (install blocked with clear message).
8. **Git concurrency (v0.1)** — `threading.Lock` in `git_sync.py` (in-process only).
9. **PyGObject** — Declared in `pyproject.toml`; many Fedora users install with `pip install --no-deps -e .` after `dnf install python3-gobject gtk4` to avoid building PyGObject/pycairo from pip.

---

## File structure

```
reshadeshadermanager/
├── CONTEXT.md                 # This file (AI/human handoff)
├── README.md                  # GitHub quickstart
├── PROJECT_SPEC.md            # Product goals, non-goals, data examples
├── IMPLEMENTATION_PLAN.md     # Locked decisions + validation notes
├── pyproject.toml             # hatchling, deps, entry point, pytest
├── .gitignore                 # .venv, __pycache__, etc.
├── reshade_shader_manager/
│   ├── __init__.py
│   ├── main.py                # GTK Application entry
│   ├── core/
│   │   ├── __init__.py
│   │   ├── exceptions.py      # RSMError, VersionResolutionError
│   │   ├── paths.py           # XDG, game_id (SHA-256 of resolved game_dir)
│   │   ├── config.py          # config.json
│   │   ├── manifest.py        # GameManifest, load/save games/*.json
│   │   ├── targets.py         # GraphicsAPI, PE arch, proxy DLL names, DX8 msg
│   │   ├── ini.py             # ReShade.ini [GENERAL] search paths only
│   │   ├── reshade.py         # GitHub tags, download, zip extract, install/remove/check
│   │   ├── repos.py           # BUILTIN_REPOS, user repos.json, merged_catalog
│   │   ├── pcgw.py            # MediaWiki API, parse HTML → repo list, cache
│   │   ├── git_sync.py        # clone/pull + lock
│   │   └── link_farm.py       # enable/disable directory symlinks
│   └── ui/
│       ├── __init__.py
│       ├── log_view.py        # LogPanel, GtkLogHandler, setup_gui_logging
│       ├── main_window.py     # Target, ReShade, shader buttons, workers
│       └── shader_dialog.py   # ShaderRepoWindow checklist + apply
└── tests/
    ├── conftest.py
    ├── test_paths.py
    ├── test_ini.py
    ├── test_manifest.py
    ├── test_backend_flows.py  # Integration-style: fake zip, mock git, PCGW fixture
    └── fixtures/pcgw_sample.html
```

**Console script:** `reshade-shader-manager` → `reshade_shader_manager.main:main`

---

## Important constraints (do not violate casually)

- **Non-goals:** No Steam integration, no game launching, no `WINEDLLOVERRIDES` automation, no SpecialK, no STL dependency.
- **No marker files** for repo enablement.
- **No flattening** shader repos; **no renaming** shader files.
- **STL = reference only** — do not port shell/YAD patterns as architecture.
- **Backend/UI split** — Keep core importable without GTK; avoid heavy logic in UI files.
- **v0.1 scope** — Avoid scope creep (no CLI required yet per spec deferral; no auto-bump ReShade).

---

## Current progress (as of this document)

- **Backend:** Implemented and covered by tests (`pytest tests/` — includes flow tests with fake ReShade zip and mocked `clone_or_pull`; optional live PCGW with `RSM_NETWORK_TEST=1`).
- **GTK UI:** Minimal v0.1 — game dir + optional exe, arch display, API/variant/version, Install/Remove/Check, Refresh catalog + Manage shaders dialog, log panel.
- **README:** GitHub-oriented setup (system PyGObject, `pip install --no-deps -e .`).
- **Known user environment:** `releases/latest` 404 → fixed by tags-based `latest`; pip PyGObject build fails without cairo → documented workaround.

---

## Next steps (suggested)

1. **Packaging:** Flatpak or distro package; document optional `pip install -e .` vs system deps clearly.
2. **Hardening:** More edge cases (empty extract, addon filename mismatch, repo without Shaders/Textures — already warn/skip).
3. **UX:** Persist/restore window geometry; optional “Save target only” clarity; better error strings for network/Git.
4. **Tests:** Headless GTK smoke optional; more unit tests for `fetch_latest_reshade_version_from_github` with mocked HTTP.
5. **Deferred per spec:** CLI, auto ReShade version bump, DX8 implementation, multi-profile per game.
6. **pyproject:** Consider adding `CONTEXT.md` to `[tool.hatch.build.targets.sdist] include` if you want it in source distributions.

---

## Quick commands

```bash
# Tests
PYTHONPATH=. pytest tests/ -q

# Run UI (after system gtk + python3-gobject)
source .venv/bin/activate
pip install --no-deps -e .
reshade-shader-manager
```

---

## Related docs (read order for new contributors)

1. `CONTEXT.md` (this file)
2. `README.md`
3. `PROJECT_SPEC.md`
4. `IMPLEMENTATION_PLAN.md`
