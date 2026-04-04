Reshade Shader Manager (RSM)

Final Project Specification

---

🧠 Overview

reshade-shader-manager (RSM) is a standalone Linux application that manages:

- ReShade installation, update, and removal
- Shader repository discovery (including PCGamingWiki), cloning, and updating
- Per-game shader enable/disable using a safe, reversible filesystem model

The project is inspired by SteamTinkerLaunch (STL), but:

- does NOT replicate STL’s shell-based architecture
- does NOT depend on STL
- uses STL only as a behavioral reference

The system is built as:

- a modular Python backend core
- a thin GTK frontend
- metadata-driven state management (no marker files)

---

🎯 Goals

- Provide a simple ReShade manager for Linux / Proton games
- Support Git-based shader repositories
- Support automatic repo discovery via PCGamingWiki
- Allow per-game shader configuration without duplication
- Keep all operations safe, reversible, and predictable
- Maintain clean separation between backend and UI

---

❌ Non-Goals

- No Steam integration or game launching
- No Proton/Wine runtime automation ("WINEDLLOVERRIDES")
- No SpecialK integration
- No dependency on SteamTinkerLaunch
- No marker-file-based state tracking
- No multi-profile system per game

---

🏗️ Architecture

Design Principles

- Backend-first design
- GUI is a thin layer over core logic
- Metadata is the single source of truth
- Filesystem state is derived (never authoritative)
- Prefer STL behavior, not STL implementation
- Keep v0.1 minimal and extensible

---

📁 Filesystem Layout

Global Data (XDG Data)

~/.local/share/reshade-shader-manager/
├── repos/
│   ├── <repo-id>/
│   └── ...
├── reshade/
│   ├── downloads/
│   ├── extracted/
│   │   ├── <version>/
│   │   └── ...
└── logs/

---

Cache (XDG Cache)

~/.cache/reshade-shader-manager/
├── pcgw_repos.json

---

Config (XDG Config)

~/.config/reshade-shader-manager/
├── config.json
├── repos.json
└── games/
    ├── <game-id>.json

---

Per-Game Layout

<GameDir>/
├── ReShade.ini
├── <runtime DLL>
├── d3dcompiler_47.dll
└── reshade-shaders/
    ├── Shaders/
    │   ├── <repo-id>/
    │   │   └── ...
    └── Textures/
        ├── <repo-id>/
        │   └── ...

---

🧩 Data Model

config.json

{
  "default_reshade_version": "latest",
  "default_variant": "standard",
  "create_ini_if_missing": true,
  "shader_download_enabled": true,
  "pcgw_cache_ttl_hours": 24
}

---

repos.json

{
  "repos": [
    {
      "id": "quint",
      "name": "qUINT",
      "git_url": "https://github.com/martymcmodding/qUINT.git",
      "author": "Marty McFly",
      "description": "qUINT shaders",
      "source": "built-in"
    }
  ]
}

---

per-game metadata

{
  "game_dir": "/path/to/game",
  "game_exe": "/path/to/game/Game.exe",
  "graphics_api": "dx11",
  "reshade_version": "6.7.3",
  "reshade_variant": "addon",
  "reshade_arch": "64",
  "enabled_repo_ids": ["quint"],
  "installed_reshade_files": [],
  "created_symlinks": []
}

---

🎮 Target Detection

User selects:

- game directory
- optional executable

System:

1. detects architecture (32/64)
2. prompts user for graphics API

---

🎯 Supported Graphics APIs

- OpenGL
- DirectX 8
- DirectX 9
- DirectX 10
- DirectX 11
- DirectX 12

---

⚙️ ReShade Runtime DLL Mapping

OpenGL  -> opengl32.dll
DX8     -> d3d8.dll (d3d8to9) + d3d9.dll
DX9     -> d3d9.dll
DX10    -> dxgi.dll (optional override: d3d10.dll)
DX11    -> dxgi.dll (optional override: d3d11.dll)
DX12    -> dxgi.dll

---

🔄 ReShade Variants

Supported installers:

Standard: ReShade_Setup_<version>.exe
Addon:    ReShade_Setup_<version>_Addon.exe

User must choose variant.

---

🌐 Shader Repository Sources (v0.1)

Repos come from:

1. Built-in list
2. User-added repos
3. PCGamingWiki

---

PCGamingWiki Integration

Behavior

- Fetch repo list from PCGamingWiki
- Use STL parser behavior as reference
- Rewrite parser in Python
- Merge with existing repo catalog
- Do NOT overwrite user repos

---

Caching

~/.cache/reshade-shader-manager/pcgw_repos.json

Rules:

- refresh if older than TTL (default 24h)
- allow manual refresh
- fallback to cache if network fails
- fallback to built-in if no cache

---

🔗 Shader Layout Strategy

reshade-shaders/
├── Shaders/<repo-id>/
├── Textures/<repo-id>/

---

Rules

- preserve filenames
- preserve internal repo structure
- no renaming
- no flattening
- no marker files
- metadata is source of truth

---

⚙️ ReShade.ini

EffectSearchPaths=.\reshade-shaders\Shaders\**
TextureSearchPaths=.\reshade-shaders\Textures\**

Recursive lookup is required.

---

🔄 Apply / Remove Logic

Enable Repo

- clone/pull repo if needed
- create symlinks into game directory
- preserve structure
- update metadata

Disable Repo

- remove repo symlinks
- clean empty directories
- update metadata

---

⚠️ Collision Handling

- no file renaming
- namespace isolation via repo folders
- enforce unique repo IDs
- log and skip conflicts

---

🧱 Module Structure

core/
  paths.py
  config.py
  targets.py
  manifest.py
  reshade.py
  ini.py
  repos.py
  git_sync.py
  link_farm.py

ui/
  main_window.py
  shader_dialog.py
  log_view.py

main.py

---

🖥️ UI Overview

Main Window

- target selection
- ReShade controls
- shader controls
- log panel

---

ReShade Controls

- Install
- Remove
- Check
- Update
- Version override
- Variant selector
- API selector

---

Shader Dialog

- repo checklist
- enable/disable
- apply

---

🚀 v0.1 Scope

Included

- PCGamingWiki repo fetching
- caching + refresh
- select game directory
- optional exe
- detect arch
- choose API
- install/remove/check ReShade; explicit update/reinstall latest (no automatic bump in RSM)
- addon + standard support
- add custom repo
- clone/update repo
- enable/disable repo
- nested symlink system
- metadata tracking
- GTK UI
- logging

---

Deferred

- Automatic ReShade version bumping or background update notifications in RSM (ReShade’s own UI covers in-game notices; RSM provides **Update / Reinstall Latest** and version field + `latest` on Install)
- CLI interface

---

🧭 Implementation Order

1. Core foundation
2. ReShade backend
3. Repo system
4. PCGamingWiki parser (port from STL behavior)
5. Symlink logic
6. GTK UI
7. Integration

---

🔒 Key Rules

- metadata is the only source of truth
- no marker files
- no file renaming
- no repo flattening
- preserve structure
- backend independent of UI
- API selection required
- ReShade variant tracked explicitly
- STL behavior is reference, not architecture

---

## v0.2 Plugin add-ons (design target)

This section updates the **intended** model for plugin add-ons (ReShade *plugin* DLLs and optional companion effect files—not the ReShade installer “addon” variant). Implementation may lag; treat this as the rule set to converge on.

### Two-tier model

| Source | Default mechanism | Rationale |
|--------|-------------------|-----------|
| **Official upstream** (from cached `Addons.ini`) | **Artifact-based** | Upstream publishes download URLs and sometimes ZIPs; cloning every upstream project is unnecessary. RSM may continue to download artifacts, extract ZIPs, and (when present in the archive) install companion files from the extracted tree. |
| **Custom user add-ons** (user catalog entry) | **Repo-based by default** | Matches shader repos: one global clone per id, explicit paths inside the tree, no reliance on ad-hoc raw file URLs for DLLs. Companion `.fx` / textures live next to binaries in the same repo. |

User-added entries should **not** require hand-crafted GitHub “raw” URLs for DLLs when a git repository exists; the **clone** is the source of truth.

### Repo-based custom add-ons (normative shape)

Conceptually aligned with shader repositories:

- **Global cache:** clone `repository_url` under the RSM data directory (same spirit as `repos/<repo-id>/`, with a **distinct** namespace such as `plugin-addons/<addon-id>/` to avoid conflating shader repos with plugin add-on repos).
- **Refresh / update:** the same user workflows that update shader clones (e.g. “Update local clones” or equivalent) should **pull** existing plugin add-on clones so companion files and DLLs stay current without re-entering URLs.
- **Game root:** copy (not symlink) the **selected** add-on DLL for the game architecture from paths **relative to the clone root** (see metadata below).
- **Shader tree:** symlink optional companion shaders **from the clone** into the game’s `reshade-shaders/` tree (e.g. under `Shaders/addons/<addon-id>/…`), preserving filenames and using metadata to define which subtree(s) participate—consistent with “global source + per-game projection.”

### Metadata (repo-based custom entries)

Planned fields (names are indicative; exact JSON keys may be finalized in implementation):

- **`repository_url`** — Git URL to clone (HTTPS). Required for repo-based custom add-ons.
- **`dll_32_path`** — Path **relative to repository root** to the 32-bit plugin payload (e.g. `AutoHDR32.addon` or `build/Release/foo.addon32`).
- **`dll_64_path`** — Same for 64-bit (e.g. `AutoHDR64.addon`).
- **Optional shader / companion layout** — One or more of:
  - **`shader_root`** — Directory relative to repo root whose contents (or subtree) are projected into the game shader tree; and/or
  - **`companion_shader_paths`** / explicit list of relative file paths; and/or
  - convention-only mode (e.g. fixed subdirs like `Shaders/` under the clone) documented at implementation time.

Exact rules for “which files are companions” vs “payload DLL only” should follow the same clarity as shader `link_farm` (documented, fail-closed where ambiguous).

### Official upstream (artifact-based)

Entries originating from `Addons.ini` may continue to use **download URLs** (per-arch or single), ZIP or flat files, and **optional** companions discovered **only from downloaded artifacts** (e.g. contents of a release ZIP). No git clone is required for this tier.

### Consistency and UX

- **Consistency:** Plugin add-on **custom** flows should feel like shader repos: catalog entry → clone in data dir → update pulls → apply projects into the game.
- **URLs:** Raw per-file GitHub URLs become **optional** for custom add-ons when a repo is specified; they are not the primary configuration path.
- **Coexistence:** The merged catalog may contain both artifact-style upstream rows and repo-style user rows; apply logic selects behavior by entry type (e.g. `source` + discriminator such as `install_mode: artifact|repo`).

### Non-goals for this design note

- This section does not prescribe file-level implementation (modules, manifest field names in JSON on disk). Those belong in `IMPLEMENTATION_PLAN.md` / code once built.
- Backward compatibility with older `plugin_addons.json` artifact-only rows is an implementation detail (deprecate, migrate, or support side-by-side).

---

🐶 Final Concept

This project captures STL’s most powerful idea:

«global shader sources + per-game projection»

But implements it cleanly in Python with a modern architecture.

---
