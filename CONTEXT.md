# CONTEXT.md — reshade-shader-manager (RSM)

**Purpose:** Handoff document for humans and AI sessions. Read this first, then `PROJECT_SPEC.md` and `IMPLEMENTATION_PLAN.md` for full detail.

---

## What this project is

**reshade-shader-manager (RSM)** is a standalone Linux application (Python backend + GTK 4 UI) that:

- Installs / removes / checks **ReShade** into a user-chosen game directory (Wine/Proton-oriented).
- Manages **Git-based shader repositories** (clone/pull, catalog merge).
- **Projects** enabled repos into `<game>/reshade-shaders/` using **directory symlinks** where possible; non-standard repo layouts use **per-file symlinks** that preserve relative paths (no renaming shader files).

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
| `~/.config/reshade-shader-manager/` | `config.json`, `repos.json` (user shader repos only), optional `plugin_addons.json` (user plugin add-on rows), `games/<sha256-of-game_dir>.json` |
| `~/.local/share/reshade-shader-manager/` | `repos/<id>/` (shader git clones), `addons/downloads/` (plugin add-on artifacts), `reshade/downloads/`, `reshade/extracted/<version>/`, `logs/` |
| `~/.cache/reshade-shader-manager/` | `pcgw_repos.json`, `plugin_addons_catalog.json`, `reshade_latest_cache.json` |

### Per-game tree (managed)

- `<game>/ReShade.ini` — RSM patches only `EffectSearchPaths` / `TextureSearchPaths` under `[GENERAL]` (Windows-style recursive globs `.\reshade-shaders\Shaders\**` and `.\reshade-shaders\Textures\**`).
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
7. **DX8** — **d3d8to9** (`d3d8.dll`) + ReShade as `d3d9.dll`; cached under `data/d3d8to9/`. Upstream release is **32-bit PE only** — 64-bit arch → clear `RSMError` (no guess).
8. **Git concurrency (v0.1)** — `threading.Lock` in `git_sync.py` (in-process only).
9. **PyGObject** — Declared in `pyproject.toml`; many Fedora users install with `pip install --no-deps -e .` after `dnf install python3-gobject gtk4` to avoid building PyGObject/pycairo from pip.

### Plugin add-ons (v0.2 — artifact-only)

These are ReShade **plugin** DLLs (e.g. `.addon32` / `.addon64`), not the ReShade installer “addon” EXE variant.

- **Model:** **Artifact-only.** RSM downloads by HTTP(S) URL (per-arch and/or single URL), caches under `~/.local/share/.../addons/downloads/`, and may extract ZIPs. There is **no** git clone and **no** install path keyed off a bare `repository_url`.
- **Upstream:** Official rows come from cached **Addons.ini** (`plugin_addons_catalog.json` after fetch/parse).
- **User rows:** Optional `plugin_addons.json` merges with upstream (same field shape); user wins on `id` collision.
- **`repository_url`:** Present on catalog rows for **metadata** (e.g. stable id hashing, upstream reference). It is **not** an install mechanism; do not add repo-based or `git pull` flows for plugin add-ons.
- **Git** remains for **shader repos** only (`repos/<id>/` and “Update local clones”).

Future UI or tooling for “add a custom plugin add-on” must stay within this model (URLs / ZIPs only).

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
│   │   ├── targets.py         # GraphicsAPI, PE arch, proxy DLL names, DX8 wrapper constant
│   │   ├── d3d8to9.py         # Download/cache crosire d3d8.dll, PE arch check
│   │   ├── plugin_addons_parse.py   # Addons.ini → stable ids + normalized rows
│   │   ├── plugin_addons_catalog.py # Fetch/cache upstream list (XDG cache)
│   │   ├── plugin_addons_user.py    # plugin_addons.json + merged catalog
│   │   ├── plugin_addons_install.py # copy DLLs, ZIP fail-closed, manifest updates
│   │   ├── ini.py             # ReShade.ini [GENERAL] search paths only
│   │   ├── reshade.py         # GitHub tags, download, zip extract, install/remove/check
│   │   ├── repos.py           # BUILTIN_REPOS, user repos.json, merged_catalog
│   │   ├── pcgw.py            # MediaWiki API, parse HTML → repo list, cache
│   │   ├── git_sync.py        # clone/pull + lock; pull_existing_clones_for_catalog
│   │   ├── ui_state.py        # window geometry JSON (no GTK)
│   │   └── link_farm.py       # apply_shader_projection, enable/disable, layouts
│   └── ui/
│       ├── __init__.py
│       ├── log_view.py        # LogPanel, GtkLogHandler, setup_gui_logging
│       ├── error_format.py    # user-facing exception strings
│       ├── main_window.py     # Target, ReShade, shader buttons, workers
│       ├── shader_dialog.py   # ShaderRepoWindow checklist + apply
│       ├── plugin_addon_dialog.py  # Plugin add-on checklist + Apply (DLL copies)
│       └── add_repo_dialog.py # Add user repo → repos.json
└── tests/
    ├── conftest.py
    ├── test_paths.py
    ├── test_ini.py
    ├── test_manifest.py
    ├── test_paths.py
    ├── test_ui_state.py
    ├── test_reshade_version.py
    ├── test_git_sync.py
    ├── test_repos.py
    ├── test_error_format.py
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
- **v0.1 scope** — Avoid scope creep (no CLI required yet per spec deferral). ReShade updates: use **Update / Reinstall Latest** in the UI or Install with version `latest`; no RSM background version notifier (ReShade itself warns in-game when newer builds exist).

---

## Current progress (as of this document)

- **Backend:** ReShade install/remove/check, INI search paths, PCGW fetch/cache, `merged_catalog`, **plugin add-on** upstream `Addons.ini` parse (stable ids) + `plugin_addons_catalog.json` cache + `plugin_addons.json` merge, `apply_shader_projection` (full rebuild on Apply; `git_pull=False` on Apply), non-standard repo layouts (nested dirs + file fallback), safe symlink removal under `reshade-shaders/`. Tests: `pytest tests/` (fake zip, mocked git; optional live PCGW with `RSM_NETWORK_TEST=1`).
- **GTK UI:** Game dir + optional exe, arch, API/variant/version, Install, **Update / Reinstall Latest** (resolve upstream `latest` at click time, same API/variant), Remove/Check, Refresh catalog, **Update local clones** (`git pull` for existing clones in the current catalog), **Add repository…** (user `repos.json`), Manage shaders (checklist + Apply), **Manage plugin add-ons…** (DLL copies + manifest), log panel, **window geometry** persistence (`ui_state.json`).
- **README / packaging:** See [README.md](README.md) and [packaging/README.md](packaging/README.md) for install and distribution notes.
- **Known environment:** `latest` resolved via GitHub tags (not `releases/latest`); system `python3-gobject` + `pip install --no-deps -e .` avoids pip-building PyGObject without cairo.

---

## Next steps (optional polish)

1. **Hardening:** Empty ReShade extract, addon filename drift, duplicate INI keys in `[GENERAL]` (v0.1 only updates first occurrence).
2. **Tests:** Headless GTK smoke; HTTP-mocked test for full `fetch_latest_reshade_version_from_github` (parser-only tests exist).
3. **Multi-instance:** Git lock is in-process only; document or add file locking if two RSM instances become a problem.
4. **Flatpak:** Example manifest in [packaging/](packaging/); publish to Flathub when ready.

---

## Future milestones (not v0.1)

Aligned with [PROJECT_SPEC.md](PROJECT_SPEC.md) deferrals and non-goals:

- **CLI** for scripting installs and shader projection.
- **DirectX 8 x64 wrapper** if upstream ships a 64-bit `d3d8.dll` (today: 32-bit only).
- **Multi-profile per game** (explicitly a non-goal for v0.1).
- **Plugin add-ons (v0.2 UI):** e.g. “Add plugin add-on…” to edit `plugin_addons.json` using **download URLs only** (artifact model). No git-backed add-on installs.

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
