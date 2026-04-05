# reshade-shader-manager (RSM)

Standalone Linux tool to manage:

- ReShade installation/update/removal (binary + `ReShade.ini` search paths)
- Git-based shader repositories (clone/pull)
- Per-game shader enable/disable via directory symlinks

App icon assets: `packaging/appimage/icons/hicolor/` (source logo: `packaging/appimage/branding/`).

The **GTK 4** UI is a thin frontend over the same metadata-driven backend as the CLI.

## Features

- Pick a game directory (+ optional `.exe` to detect 32/64-bit)
- Select graphics API (`opengl`, `dx8`, `dx9`, `dx10`, `dx11`, `dx12`) and ReShade variant (`standard`/`addon`)
- Install / remove ReShade binaries; **Update / Reinstall Latest** resolves current upstream `latest` (GitHub tags / cache) for the selected standard or addon variant and reinstalls
- Check that installed ReShade binaries exist
- Refresh shader catalog (built-in + user `repos.json` + cached PCGamingWiki); same action refreshes the **plugin add-on** list from official upstream `Addons.ini` only (cached)
- **Add repository…** to append a custom Git repo to `~/.config/.../repos.json`
- **Update local clones** — `git pull` for catalog repos that already have a clone (Apply does not pull)
- Manage shaders: enable/disable repos for the selected game (full symlink rebuild on Apply)
- **Manage plugin add-ons…**: copy selected **plugin** DLLs from the official **Addons.ini** catalog into the game folder (fail-closed ZIP handling; does not overwrite unmanaged files; not the ReShade installer “addon” variant)
- Log panel showing backend progress/errors

## Requirements

System packages (Fedora / similar):

- `gtk4`, `gtk4-devel`
- `python3-gobject` (provides the `gi` module)
- `cairo` / `cairo-devel` (usually pulled in as dependencies)

Python:

- Python 3.10+

## Setup / Run (from source)

```bash
cd reshade-shader-manager   # your clone of this repository
python3 -m venv .venv
source .venv/bin/activate

# Install backend + UI without asking pip to build PyGObject
pip install --no-deps -e .
```

Then run:

```bash
reshade-shader-manager
# or: python3 -m reshade_shader_manager.main
```

## Command-line interface

After `pip install --no-deps -e .`, the **`rsm`** command is available (no display required). It uses the same core as the GUI:

```bash
rsm --help
rsm catalog refresh
rsm shaders apply --game-dir /path/to/game --repo quint --git-pull
rsm shaders update-clones
rsm addons apply --game-dir /path/to/game --addon some-id
rsm reshade install --game-dir /path/to/game --exe /path/to/game.exe --api dx11
rsm game inspect --game-dir /path/to/game --json
```

See `rsm --help` and [CHANGELOG.md](CHANGELOG.md) for the full command set.

### CLI exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | User error (invalid input, missing manifest, ReShade **check** found missing files, etc.) |
| `2` | Unexpected internal error (use `rsm -v …` for a traceback) |
| `130` | Interrupted (Ctrl+C) |

## Testing against a real game

1. In the UI, click **Game directory…** and choose the game/prefix folder where the `.exe` is located.
2. Optionally choose **Game executable…** (or rely on the directory scan) so architecture becomes `32-bit` or `64-bit`.
3. Choose **Graphics API**, **Variant**, and **Version**.
   - If you leave version as `latest`, RSM resolves it via GitHub *tags*; if the network fails and no cached value exists, you must enter an explicit version like `6.7.3`.
4. Click **Install**, or use **Update / Reinstall Latest** anytime to pull the newest ReShade build for the selected API and variant (no background updater in RSM; ReShade notifies in-game when applicable).
5. Click **Refresh catalog**. Use **Update local clones** if you want newer commits from Git before applying.
6. **Manage shaders…** to enable/disable repos for that game, then **Apply** (recreates projection; does not run `git pull`).
7. Optionally **Manage plugin add-ons…** to enable official add-ons from the cached **Addons.ini** list, then **Apply** (downloads by URL; does not pull git for add-ons).

## Data locations (XDG)

Backend uses these defaults:

- Config: `~/.config/reshade-shader-manager/config.json`, `repos.json`, and per-game manifests under `games/`
- Data: `~/.local/share/reshade-shader-manager/` (git clones and downloaded/extracted ReShade)
- Cache: `~/.cache/reshade-shader-manager/pcgw_repos.json`, `plugin_addons_catalog.json` (parsed upstream `Addons.ini`)

Per-game projection happens under:

- `<game>/ReShade.ini`
- `<game>/<ReShade proxy dll>.dll` + optional `d3dcompiler_47.dll`
- `<game>/reshade-shaders/Shaders/<repo-id>` and `.../Textures/<repo-id>` — usually *directory* symlinks; non-standard repos may use per-file symlinks preserving paths

## Notes / limitations

- RSM supports **one active ReShade install state per game directory** (reinstall replaces the tracked proxy binaries list; no multi-runtime merging).
- **DirectX 8** uses **d3d8to9** (`d3d8.dll`) plus ReShade as **`d3d9.dll`**. The pinned crosire release currently ships a **32-bit** `d3d8.dll` only; **64-bit games** get a clear error at install time.
- “Remove ReShade” is binary-only: it deletes files tracked in `installed_reshade_files` and does **not** remove shader symlinks, enabled repo state, or `ReShade.ini` by default.

## Packaging

See [packaging/README.md](packaging/README.md) for pip, wheels, optional **AppImage** build steps, Flatpak notes, and distro hints.

## Roadmap

- **v1.0:** Stabilization and polish (see [CHANGELOG.md](CHANGELOG.md)); broader CLI test coverage and optional AppStream metadata for AppImage are possible follow-ups.
- Multi-profile per game (currently a non-goal)

Details: [CONTEXT.md](CONTEXT.md), [PROJECT_SPEC.md](PROJECT_SPEC.md), and [CHANGELOG.md](CHANGELOG.md).

## Development

See:

- `docs/MANUAL_QA.md` (manual regression checklist before a release tag)
- `CHANGELOG.md`
- `PROJECT_SPEC.md`
- `IMPLEMENTATION_PLAN.md`
- `CONTEXT.md`

