# RSM implementation plan (locked)

This document is the **authoritative implementation plan** for *reshade-shader-manager*. It subsumes the earlier draft plan and incorporates **locked architecture decisions** (see §0). **No code** lives here—only structure, schemas, flows, and execution order.

**Reference:** `PROJECT_SPEC.md` (product goals and non-goals).

---

## 0. Locked decisions (do not revisit without explicit change)

1. **Directory symlinks only (per repo)**  
   For each enabled repo, create at most:
   - `<game>/reshade-shaders/Shaders/<repo-id>` → `<data>/repos/<repo-id>/Shaders`  
   - `<game>/reshade-shaders/Textures/<repo-id>` → `<data>/repos/<repo-id>/Textures`  
   Use **absolute** symlink targets (see item 6).  
   **Do not** create per-file symlinks unless a **documented exception** applies (e.g. a repo layout that cannot be represented by these two directory links—treat as edge case in `link_farm` with explicit user-visible error or fallback policy in code comments only after discovery).

2. **Per-game metadata: `symlinks_by_repo_id`**  
   Replace any flat `created_symlinks` list with:
   ```json
   "symlinks_by_repo_id": { "<repo-id>": ["<absolute symlink path>", ...] }
   ```  
   Disable/remove operations use this map as the **only** authoritative record of what RSM created for that repo.

3. **Catalog sources**  
   - **Built-in repos:** defined **only in code** (constant / module).  
   - **`repos.json`:** **user-added** repos only (persisted).  
   - **PCGamingWiki:** fetched/parsed, stored in **cache** (`~/.cache/.../pcgw_repos.json`); merged **at runtime** with built-in + user. User repos win on `id` collision per spec.

4. **`ReShade.ini` (v0.1)**  
   - Manage **only** RSM-owned search-path entries (`EffectSearchPaths`, `TextureSearchPaths` per spec’s recursive pattern).  
   - **Preserve** all other keys/sections.  
   - **Do not** delete `ReShade.ini` on ReShade uninstall by default.

5. **DirectX 8**  
   If full DX8 support (e.g. multiple DLLs / d3d8to9 policy) adds too much complexity, **defer implementation** for v0.1 while keeping **`dx8` in the UI and in the data model** (`graphics_api` enum). Runtime behavior for `dx8`: clear “not implemented” path (message + no install) until a later version.

6. **Symlink targets**  
   Prefer **absolute** paths to `<data>/repos/<repo-id>/...` as symlink targets.

---

## 0b. Additional locked ambiguities (v0.1)

1. **Remove ReShade behavior**  
   - “Remove ReShade” removes **only** files listed in `installed_reshade_files`.  
   - Do **not** remove shader symlinks.  
   - Do **not** clear `enabled_repo_ids`.  
   - Do **not** delete `ReShade.ini` by default.

2. **`latest` resolution**  
   - Resolve `latest` using the **current upstream ReShade tags** from GitHub (e.g. `v6.7.3`), then pick the highest semver.  
   - If lookup fails, fall back to the **last successfully cached** resolved version in `~/.cache/reshade-shader-manager/reshade_latest_cache.json`.  
   - If there is no cache, **require an explicit version** and raise / surface a **clear error** (no silent fallback).

3. **INI merge strategy (v0.1)**  
   - If `EffectSearchPaths` exists (in the active INI parsing model), **replace only its value** (same key line).  
   - If `TextureSearchPaths` exists, **replace only its value**.  
   - If either key is missing, **add** it (under `[GENERAL]`; create `[GENERAL]` if needed).  
   - Preserve **all** other INI content.  
   - Do **not** add marker comments or a dedicated “managed block” in v0.1.

4. **Unsupported repo layout**  
   - If a repo has **neither** `Shaders` nor `Textures` at the clone root (case-insensitive directory names), **log a warning** and **skip** enabling that repo in v0.1.

5. **DX8**  
   - Keep `dx8` in the model/UI.  
   - Do **not** install anything for `dx8` in v0.1.  
   - Surface a clear **“not implemented”** message (constant usable by UI).

6. **Git concurrency**  
   - v0.1: **simple in-process serialization** (a module-level `threading.Lock` around `git clone` / `git pull` in `git_sync.py`). No file locks or multi-process coordination yet.

### Implementation note (Remove ReShade, locked)

“Remove ReShade” is **binary-only**: delete paths in `installed_reshade_files` only; **do not** remove shader directory symlinks, **do not** clear `enabled_repo_ids`, **do not** delete `ReShade.ini` unless a future explicit action is added.

---

## 1. Final package / module structure

```
reshade_shader_manager/
├── __init__.py
├── main.py                 # GtkApplication; wires UI → core
├── core/
│   ├── __init__.py
│   ├── paths.py            # XDG roots, subpaths, stable game_id
│   ├── config.py           # config.json load/save + defaults
│   ├── targets.py          # GameTarget: paths, arch, API, variant
│   ├── manifest.py         # Per-game JSON load/save, validation, atomic write
│   ├── reshade.py          # Download, extract, install/remove/check/update
│   ├── ini.py              # RSM-owned ReShade.ini lines only; preserve rest
│   ├── repos.py            # Built-in (code) + user repos.json + runtime merge w/ PCGW
│   ├── pcgw.py             # Fetch, TTL, parse → cache file; no overwrite of repos.json
│   ├── git_sync.py         # clone/pull under ~/.local/share/.../repos/<id>
│   └── link_farm.py        # Directory symlinks + symlinks_by_repo_id updates
└── ui/
    ├── __init__.py
    ├── main_window.py
    ├── shader_dialog.py
    └── log_view.py
```

Tests: `tests/core/...` (recommended alongside steps below).

---

## 2. Module responsibilities

| Module | Responsibility |
|--------|----------------|
| `paths.py` | Resolve XDG dirs; subpaths for data/cache/config; `game_id_from_game_dir()` (stable, documented); helpers for symlink paths under game and clone roots. |
| `config.py` | `config.json` I/O, defaults, validation. |
| `manifest.py` | `games/<game-id>.json` I/O; atomic writes; validate `symlinks_by_repo_id`, `enabled_repo_ids`, installed files; no disk scan as source of truth. |
| `targets.py` | Canonical absolute `game_dir`, optional `game_exe`, PE arch → `reshade_arch`; holds selected `graphics_api` / `reshade_variant` for calls into `reshade.py`. |
| `reshade.py` | Version resolution, download to data `reshade/downloads/`, extract to `reshade/extracted/<version>/`, API→DLL mapping, copy files, update `installed_reshade_files`; remove/check; **DX8: stub only** until implemented. |
| `ini.py` | Read INI; patch **only** managed search-path keys; leave all other content unchanged; honor `create_ini_if_missing`. Never delete INI on uninstall (default). |
| `repos.py` | Export built-in list from code; read/write **user-only** `repos.json`; `merged_catalog()` = built-in ∪ user ∪ PCGW (PCGW from `pcgw.py` reader); collision: user wins. |
| `pcgw.py` | Network fetch + parse; write `~/.cache/.../pcgw_repos.json` with TTL from config; stale cache on failure. |
| `git_sync.py` | `clone_or_pull(data_dir/repos/<id>, url)`. |
| `link_farm.py` | For enable: ensure `Shaders/` and `Textures/` exist under game `reshade-shaders/`; for each repo, if `<data>/repos/<id>/Shaders` exists, symlink `game/.../Shaders/<id>` → absolute `.../Shaders`; same for `Textures`; record paths under `symlinks_by_repo_id[id]`. For disable: remove only paths listed for that id; prune empty dirs if safe. Collision: target exists and is not our symlink → log + skip. **No per-file symlinks** per decision §0.1. |
| `main.py` | Application entry; dependency wiring. |
| `main_window.py` | Target selection, ReShade actions, log panel, **graphics API combo including dx8 (disabled or “not in v0.1” messaging)**. |
| `shader_dialog.py` | Merged catalog checklist; apply → `git_sync` + `link_farm` + manifest. |
| `log_view.py` | Log sink for UI. |

---

## 3. On-disk layout

### `~/.local/share/reshade-shader-manager/`

```
reshade-shader-manager/
├── repos/
│   └── <repo-id>/                 # git working tree (full clone)
├── reshade/
│   ├── downloads/
│   │   └── ReShade_Setup_<version>[_Addon].exe
│   └── extracted/
│       └── <version>/             # unzip output; discover DLLs here
└── logs/
    └── rsm.log                    # or rotation policy—pick one at implementation
```

### `~/.cache/reshade-shader-manager/`

```
reshade-shader-manager/
├── pcgw_repos.json                # PCGW snapshot + fetch metadata
└── tmp/                           # optional; omit in v0.1 if unused
```

### `~/.config/reshade-shader-manager/`

```
reshade-shader-manager/
├── config.json
├── repos.json                     # **user-added repos only**
└── games/
    └── <game-id>.json
```

### Managed game directory (projection)

```
<GameDir>/
├── ReShade.ini
├── <reshade proxy dll(s) per API>  # v0.1: not dx8 until implemented
├── d3dcompiler_47.dll              # if install policy includes it
└── reshade-shaders/
    ├── Shaders/
    │   └── <repo-id>  →  <absolute path>/.../repos/<repo-id>/Shaders
    └── Textures/
        └── <repo-id>  →  <absolute path>/.../repos/<repo-id>/Textures
```

If `Shaders` or `Textures` is missing in the clone, **only create the symlink(s) for paths that exist**; do not invent marker dirs (no marker files).

---

## 4. JSON schemas (exact)

### `config.json`

Same as prior plan: `default_reshade_version`, `default_variant` (`standard`|`addon`), `create_ini_if_missing`, `shader_download_enabled`, `pcgw_cache_ttl_hours`.  
`additionalProperties: false` at top level.

### `repos.json` (user only)

```json
{
  "repos": [
    {
      "id": "my-shaders",
      "name": "…",
      "git_url": "https://…",
      "author": "…",
      "description": "…",
      "source": "user"
    }
  ]
}
```

- `source` for this file is always `"user"` for persisted entries.  
- Built-in and PCGW entries **never** written here.

### `pcgw_repos.json` (cache)

Unchanged intent: `fetched_at_utc`, `repos[]` with `source: "pcgw"`, optional error field.

### `games/<game-id>.json` (per-game)

**Required / locked fields:**

```json
{
  "schema_version": 1,
  "game_dir": "/absolute/path",
  "game_exe": "/absolute/path/Game.exe",
  "graphics_api": "dx11",
  "reshade_version": "6.7.3",
  "reshade_variant": "standard",
  "reshade_arch": "64",
  "enabled_repo_ids": ["quint"],
  "installed_reshade_files": ["dxgi.dll", "d3dcompiler_47.dll"],
  "symlinks_by_repo_id": {
    "quint": [
      "/absolute/game/reshade-shaders/Shaders/quint",
      "/absolute/game/reshade-shaders/Textures/quint"
    ]
  }
}
```

- **`symlinks_by_repo_id`:** only keys for **enabled** repos should have non-empty lists after a successful apply; on disable, remove symlink paths for that id and remove id from `enabled_repo_ids` (and optionally remove empty key).  
- No `created_symlinks` flat list.  
- `game_exe` may be `null` if unset (use `null` in JSON).  
- **`graphics_api`:** includes `"dx8"` for forward compatibility; v0.1 code path for dx8 = not implemented (decision §0.5).

---

## 5. Execution flows (with locked decisions applied)

### ReShade install

1. Resolve target + arch + API + variant + version.  
2. If `graphics_api == "dx8"`: show not-implemented (v0.1); **do not** install.  
3. Download/extract to data cache; copy DLLs + optional `d3dcompiler_47.dll`; append to `installed_reshade_files`.  
4. `ini.py`: apply **§0b.3** (replace-or-add the two keys only; preserve all other content).  
5. Save manifest.

### ReShade remove

Per **§0b.1**: remove **only** files in `installed_reshade_files`; do **not** remove shader symlinks; do **not** clear `enabled_repo_ids`; do **not** delete `ReShade.ini` by default. Warn if a listed file is missing.

### ReShade check

1. Verify manifest files exist; optional PE/arch warnings; report orphan symlinks **vs** `symlinks_by_repo_id` as informational only.

### Shader repo fetch/sync

1. `repos.py` merged catalog = built-in (code) + `repos.json` (user) + PCGW (from cache/live per TTL).  
2. `git_sync` on `~/.local/share/.../repos/<id>`.

### Enable repo

1. Clone/pull.  
2. `link_farm`: create **directory** symlinks with **absolute** targets; append symlink paths to `symlinks_by_repo_id[repo_id]`; add `repo_id` to `enabled_repo_ids`.  
3. Skip symlink creation for a missing `Shaders` or `Textures` half. If **both** are missing, **§0b.4**: log a warning and skip the repo.

### Disable repo

1. Remove filesystem entries listed in `symlinks_by_repo_id[repo_id]`.  
2. Remove `repo_id` from `enabled_repo_ids`; clear or delete the map entry for `repo_id`.  
3. Prune empty parent dirs under `reshade-shaders/` when safe.

---

## 6. Implementation order (by module)

1. `paths.py` (+ `game_id` tests)  
2. `config.py`  
3. `manifest.py` (schema with `symlinks_by_repo_id`)  
4. `targets.py` (arch; **dx8 allowed in enum**, stub in `reshade.py`)  
5. `reshade.py` (non-dx8 APIs first; dx8 → explicit stub)  
6. `ini.py` (RSM-only keys, preserve rest)  
7. `repos.py` (built-in in code; user `repos.json` only)  
8. `git_sync.py`  
9. `pcgw.py` + cache merge  
10. `link_farm.py` (directory symlinks, absolute targets, map updates)  
11. Integration tests / manual script: install → enable → disable → remove binaries  
12. `ui/log_view.py` → `main_window.py` → `shader_dialog.py` → `main.py`  
13. ReShade update / version override UI

---

## 7. Risks and follow-ups (post-lock)

- **Duplicate INI keys:** If `EffectSearchPaths` appears more than once, v0.1 should replace the **first** occurrence in `[GENERAL]` only (documented behavior); revisit if ReShade generates duplicates.  
- **ReShade installer layout changes:** DLL discovery stays heuristic (`ReShade64.dll` / `ReShade32.dll` / `d3dcompiler_47.dll` walk); adjust if upstream changes.  
- **Multi-process GUI:** In-process git lock does not coordinate two app instances; document or add file locks later.

---

## 8. v0.1 backend assumptions (explicit)

- **One active ReShade runtime per game directory:** at most one coherent proxy + companion DLL set managed by RSM at a time. Re-installing **deletes files listed in the previous** `installed_reshade_files` **from disk** before copying the new set, then **replaces** that list in the manifest (no merge across APIs or versions).
- **No multi-runtime merge:** side-by-side tracking of multiple ReShade proxy names beyond a single install pass is **not** required in v0.1.
- **Remove ReShade** remains **binary-only** (manifest list); it does not clear shader symlinks, `enabled_repo_ids`, or `ReShade.ini`.

---

## 9. Backend validation — observed behavior (tests: `tests/test_backend_flows.py`)

Verified offline (fake ReShade zip + mocked `clone_or_pull`) unless `RSM_NETWORK_TEST=1` for live PCGW.

### `installed_reshade_files`

- After **install** (DX11, 64-bit, standard variant, fake payload with compiler): `["dxgi.dll", "d3dcompiler_47.dll"]` — basenames **relative to `game_dir`**.
- After **remove binaries**: `[]`; listed files are gone from disk; **INI and shader state unchanged**.
- After **reinstall** with a different API: prior tracked files (e.g. `dxgi.dll`) are **removed** before the new proxy is written; manifest list **replaces** to e.g. `["opengl32.dll", "d3dcompiler_47.dll"]`.

### `symlinks_by_repo_id`

- After **enable** for repo `testrepo` with both `Shaders/` and `Textures/`: one map entry, e.g. `{"testrepo": ["<abs>/.../reshade-shaders/Shaders/testrepo", "<abs>/.../Textures/testrepo"]}` — values are **absolute paths to the symlink inodes** under the game tree (not `Path.resolve()` through the link, so disable can `unlink` the correct entry). Symlink targets point at the global clone’s `Shaders` / `Textures` directories.
- After **disable**: key removed; `enabled_repo_ids` no longer contains the repo; symlink paths **removed** from disk.

### `ReShade.ini` output

- Created or patched under `game_dir/ReShade.ini` with a `[GENERAL]` section containing:
  - `EffectSearchPaths=.\reshade-shaders\Shaders**`
  - `TextureSearchPaths=.\reshade-shaders\Textures**`
- Other sections/keys are preserved when present; first matching key in `[GENERAL]` is updated (see §0b.3).

### PCGW parsed repo records

- **Fixture HTML** (`tests/fixtures/pcgw_sample.html`): parser emits dicts with `id` (slug from repo name, lowercase), `name` (last URL segment), `git_url` (`.git` suffix added), `author` / `description` often `""`, `source` always `"pcgw"`. Duplicate GitHub links that map to the same `id` appear **once**.
- **Live fetch** (`fetch_pcgw_repos_raw`, with `RSM_NETWORK_TEST=1`): returns `(repos, error)`; on success `error is None`, non-empty list of the same record shape; on failure `repos` may be empty with `error` set.

---

*End of locked implementation plan.*
