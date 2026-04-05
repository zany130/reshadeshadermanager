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

RSM does **not** create or edit `ReShade.ini`. Configure search paths in ReShade’s own UI or by editing the INI ReShade writes.

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

## v0.2 (release)

**Plugin add-ons (ReShade plugin DLLs, not the installer “addon” EXE):**

- **Source:** Official **`Addons.ini`** only — `https://raw.githubusercontent.com/crosire/reshade-shaders/list/Addons.ini`, fetched and cached. RSM lists installable entries (with download URLs for the game architecture) under **Manage plugin add-ons…** and copies artifacts into the game directory; manifest tracks enabled add-ons and companion symlinks when present in downloaded archives.
- **Non-goals for plugin add-ons:** No user-defined add-on catalog file, no merging custom entries with upstream, no git clone of add-on repositories. **`RepositoryUrl`** in `Addons.ini` remains metadata for stable ids / reference, not an install transport.

v0.2 includes the GTK UI and core behavior described for v0.1 above, plus this plugin add-on flow. See [CHANGELOG.md](CHANGELOG.md).

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

🐶 Final Concept

This project captures STL’s most powerful idea:

«global shader sources + per-game projection»

But implements it cleanly in Python with a modern architecture.

---
