# CONTEXT.md — reshade-shader-manager (RSM)

**Purpose:** Handoff document for humans and AI sessions. Read this first, then `PROJECT_SPEC.md` and `IMPLEMENTATION_PLAN.md` for full detail.

---

## What this project is

**reshade-shader-manager (RSM)** is a standalone Linux application (Python backend + GTK 4 UI + optional **`rsm` CLI**, v0.5+) that:

- Installs / removes / checks **ReShade** into a user-chosen game directory (Wine/Proton-oriented).
- Manages **Git-based shader repositories** (clone/pull, catalog merge).
- **Projects** enabled repos into `<game>/reshade-shaders/` using **directory symlinks** where possible; non-standard repo layouts use **per-file symlinks** that preserve relative paths (no renaming shader files).

It is **inspired by** SteamTinkerLaunch (STL) behavior only; it does **not** depend on STL or replicate its shell architecture.

---

## Full architecture

### Layers

1. **Core (`reshade_shader_manager/core/`)**  
   Filesystem, network, git, manifest I/O, ReShade download/extract/install, INI patching, PCGW fetch/parse, symlink projection, shared catalog fetch (`catalog_ops`), user-facing error strings (`error_format`). **No GTK imports.**

2. **UI (`reshade_shader_manager/ui/`)**  
   Thin GTK 4 layer: `MainWindow`, `ShaderRepoWindow`, `LogPanel` + logging handler. Long work runs on **background threads**; UI updates via `GLib.idle_add`.

3. **CLI (`reshade_shader_manager/cli.py`)**  
   `argparse` front-end over core only (no PyGObject). Console script **`rsm`**.

4. **GTK entry (`reshade_shader_manager/main.py`)**  
   `gi.require_version("Gtk", "4.0")` then `Gtk.Application` → `MainWindow`.

### Data flow (conceptual)

- **Single source of truth:** JSON metadata under `~/.config/.../games/<slug>-<fp8>.json` (`GameManifest`; `fp8` = first 8 hex chars of SHA-256 of the canonical game directory), not marker files in the game tree. Pre–v0.3 `games/<full-sha256>.json` names are still found on load and migrated when touched.
- **Filesystem** (DLLs, symlinks, `ReShade.ini`) is **derived** from manifest + user actions; repair/drift is informational only unless code explicitly rescans (minimal by design).

### XDG layout

| Location | Contents |
|----------|----------|
| `~/.config/reshade-shader-manager/` | `config.json`, `repos.json` (user shader repos only), `games/<slug>-<fp8>.json` per game (v0.3+; legacy `games/<sha256>.json` still loaded and migrated lazily) |
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
5. **One active ReShade runtime per game** — On **install**, previously tracked DLLs are removed from disk before copying new ones; `installed_reshade_files` is **replaced** (no multi-runtime merge).
6. **`latest` version** — Resolved from GitHub **tags** (`/repos/crosire/reshade/tags?per_page=100`), highest semver (not `releases/latest`, which 404’d). On failure, use `~/.cache/.../reshade_latest_cache.json`; else require explicit version.
7. **DX8** — **d3d8to9** (`d3d8.dll`) + ReShade as `d3d9.dll`; cached under `data/d3d8to9/`. Upstream release is **32-bit PE only** — 64-bit arch → clear `RSMError` (no guess).
8. **Git concurrency** — `threading.Lock` in `git_sync.py` (in-process only).
9. **PyGObject** — Declared in `pyproject.toml`; many Fedora users install with `pip install --no-deps -e .` after `dnf install python3-gobject gtk4` to avoid building PyGObject/pycairo from pip.

### Plugin add-ons (official upstream only)

These are ReShade **plugin** DLLs (e.g. `.addon32` / `.addon64`), not the ReShade installer “addon” EXE variant.

- **Source of truth:** **Only** the official **`Addons.ini`** from the reshade-shaders repo (`https://raw.githubusercontent.com/crosire/reshade-shaders/list/Addons.ini`), fetched and cached as `plugin_addons_catalog.json`. There is **no** `plugin_addons.json`, no user-defined add-on list, and no merge with custom entries.
- **Install:** **Artifact-only** — HTTP(S) download by URL from that catalog, cache under `~/.local/share/.../addons/downloads/`, optional ZIP extract. No git clone for plugin add-ons; no custom add-on UI.
- **`repository_url`:** On upstream rows, **metadata only** (stable ids, reference). Not an install mechanism.
- **Git** applies only to **shader repos** (`repos/<id>/`, “Update local clones”).

---

## File structure

```
reshadeshadermanager/
├── CONTEXT.md                 # This file (AI/human handoff)
├── README.md                  # GitHub quickstart
├── CHANGELOG.md               # Release notes (e.g. v0.5.0)
├── PROJECT_SPEC.md            # Product goals, non-goals, data examples
├── IMPLEMENTATION_PLAN.md     # Locked decisions + validation notes
├── pyproject.toml             # hatchling, deps, entry point, pytest
├── .gitignore                 # .venv, __pycache__, etc.
├── reshade_shader_manager/
│   ├── __init__.py
│   ├── main.py                # GTK Application entry
│   ├── cli.py                 # argparse CLI; console script rsm
│   ├── core/
│   │   ├── __init__.py
│   │   ├── exceptions.py      # RSMError, VersionResolutionError
│   │   ├── error_format.py    # format_exception_for_ui (shared with CLI)
│   │   ├── catalog_ops.py     # fetch_merged_catalogs (GUI + CLI)
│   │   ├── paths.py           # XDG, manifest paths `{slug}-{fp8}.json` + legacy hash id
│   │   ├── config.py          # config.json
│   │   ├── manifest.py        # GameManifest, load/save games/*.json
│   │   ├── targets.py         # GraphicsAPI, PE arch, proxy DLL names, DX8 wrapper constant
│   │   ├── d3d8to9.py         # Download/cache crosire d3d8.dll, PE arch check
│   │   ├── plugin_addons_parse.py   # Addons.ini → stable ids + normalized rows
│   │   ├── plugin_addons_catalog.py # Fetch/cache official Addons.ini (XDG cache)
│   │   ├── plugin_addons_install.py # copy DLLs, ZIP fail-closed, manifest updates
│   │   ├── ini.py             # ReShade.ini [GENERAL] search paths only
│   │   ├── reshade.py         # GitHub tags, download, zip extract, install/remove/check
│   │   ├── repos.py           # BUILTIN_REPOS, user repos.json, merged_catalog
│   │   ├── pcgw.py            # MediaWiki API, parse HTML → repo list, cache
│   │   ├── git_sync.py        # clone/pull + lock; pull_existing_clones_for_catalog
│   │   ├── ui_state.py        # window geometry JSON (no GTK)
│   │   ├── recent_games.py    # Recent games list (mtime scan of games/*.json)
│   │   └── link_farm.py       # apply_shader_projection, enable/disable, layouts
│   └── ui/
│       ├── __init__.py
│       ├── log_view.py        # LogPanel, GtkLogHandler, setup_gui_logging
│       ├── error_format.py    # re-exports core.error_format
│       ├── main_window.py     # Target, Recent games, ReShade, shader buttons, workers
│       ├── shader_dialog.py   # ShaderRepoWindow checklist + apply
│       ├── plugin_addon_dialog.py  # Plugin add-on checklist + Apply (DLL copies)
│       └── add_repo_dialog.py # Add user repo → repos.json
└── tests/
    ├── conftest.py
    ├── test_paths.py
    ├── test_ini.py
    ├── test_manifest.py
    ├── test_recent_games.py
    ├── test_ui_state.py
    ├── test_reshade_version.py
    ├── test_git_sync.py
    ├── test_repos.py
    ├── test_error_format.py
    ├── test_cli.py
    ├── test_catalog_ops.py
    ├── test_backend_flows.py  # Integration-style: fake zip, mock git, PCGW fixture
    └── fixtures/pcgw_sample.html
```

**Console scripts:** `reshade-shader-manager` → `reshade_shader_manager.main:main`; **`rsm`** → `reshade_shader_manager.cli:main`

---

## Important constraints (do not violate casually)

- **Non-goals:** No Steam integration, no game launching, no `WINEDLLOVERRIDES` automation, no SpecialK, no STL dependency.
- **No marker files** for repo enablement.
- **No flattening** shader repos; **no renaming** shader files.
- **STL = reference only** — do not port shell/YAD patterns as architecture.
- **Backend/UI split** — Keep core importable without GTK; avoid heavy logic in UI files.
- **Release v0.5 (current)** — **`rsm` CLI** (`argparse`): catalog refresh, shader apply / update-clones, add-on apply / refresh-catalog, ReShade install/update/remove/check, `game inspect` — all calling existing core; **`fetch_merged_catalogs`** shared with GUI.
- **v0.4** — **Recent games** in the Target section (mtime-ordered manifests; no new manifest fields).
- **v0.3** — Startup **catalog hydration**; human-readable **`games/{slug}-{fp8}.json`** manifests with lazy legacy migration.
- **v0.2** — Official **Addons.ini**–only plugin add-ons, ReShade + shader flows, GTK UI. **Not** in scope: user-defined plugin add-on catalogs, multi-profile per game.
- **Deferred** — Multi-profile per game remains a non-goal until explicitly planned. ReShade updates: use **Update / Reinstall Latest** or explicit version; no RSM background version notifier.

---

## Current progress (as of this document)

- **Backend:** ReShade install/remove/check, INI search paths, PCGW fetch/cache, `merged_catalog`, **plugin add-ons** from official cached **`Addons.ini`** only (`plugin_addons_catalog.json`), `apply_shader_projection` (full rebuild on Apply; `git_pull=False` on Apply), non-standard repo layouts (nested dirs + file fallback), safe symlink removal under `reshade-shaders/`. Tests: `pytest tests/` (fake zip, mocked git; optional live PCGW with `RSM_NETWORK_TEST=1`).
- **GTK UI:** Game dir + optional exe, **Recent games** list (v0.4), arch, API/variant/version, Install, **Update / Reinstall Latest** (resolve upstream `latest` at click time, same API/variant), Remove/Check, **startup catalog hydration** + Refresh catalog (forced refresh), **Update local clones** (`git pull` for existing clones in the current catalog), **Add repository…** (user `repos.json`), Manage shaders (checklist + Apply), **Manage plugin add-ons…** (DLL copies + manifest), log panel, **window geometry** persistence (`ui_state.json`).
- **CLI (v0.5):** Same operations via `rsm` for scripting and headless use (see README).
- **README / packaging:** See [README.md](README.md) and [packaging/README.md](packaging/README.md) for install and distribution notes.
- **Known environment:** `latest` resolved via GitHub tags (not `releases/latest`); system `python3-gobject` + `pip install --no-deps -e .` avoids pip-building PyGObject without cairo.

---

## Next steps (optional polish, post–v0.2)

These are **not** required to ship v0.2; track for hardening and packaging follow-up.

1. **Hardening:** Empty ReShade extract, addon filename drift, duplicate INI keys in `[GENERAL]` (current INI merge updates first occurrence only).
2. **Tests:** Headless GTK smoke; HTTP-mocked test for full `fetch_latest_reshade_version_from_github` (parser-only tests exist).
3. **Multi-instance:** Git lock is in-process only; document or add file locking if two RSM instances become a problem.
4. **Flatpak:** Example manifest in [packaging/](packaging/); publish to Flathub when ready.

---

## Future milestones (post–v0.5)

Aligned with [PROJECT_SPEC.md](PROJECT_SPEC.md) deferrals and non-goals:

- **CLI** enhancements (JSON output, shell completion, optional config path) beyond the v0.5 `rsm` surface.
- **DirectX 8 x64 wrapper** if upstream ships a 64-bit `d3d8.dll` (today: 32-bit only).
- **Multi-profile per game** (explicitly a non-goal unless scope changes).

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
3. `CHANGELOG.md`
4. `PROJECT_SPEC.md`
5. `IMPLEMENTATION_PLAN.md`
