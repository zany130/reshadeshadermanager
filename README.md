# reshade-shader-manager (RSM)

Standalone Linux tool to manage:

- ReShade installation/update/removal (binary + `ReShade.ini` search paths)
- Git-based shader repositories (clone/pull)
- Per-game shader enable/disable via directory symlinks

GTK UI (v0.1) is a thin frontend over a metadata-driven backend core.

## Features (v0.1)

- Pick a game directory (+ optional `.exe` to detect 32/64-bit)
- Select graphics API (`opengl`, `dx9`, `dx10`, `dx11`, `dx12`) and ReShade variant (`standard`/`addon`)
- Install / remove ReShade binaries; **Update / Reinstall Latest** resolves current upstream `latest` (GitHub tags / cache) for the selected standard or addon variant and reinstalls
- Check that installed ReShade binaries exist
- Refresh shader catalog (built-in + user `repos.json` + cached PCGamingWiki)
- **Add repository…** to append a custom Git repo to `~/.config/.../repos.json`
- **Update local clones** — `git pull` for catalog repos that already have a clone (Apply does not pull)
- Manage shaders: enable/disable repos for the selected game (full symlink rebuild on Apply)
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
cd /var/home/zany130/Documents/GitHub/reshadeshadermanager
python -m venv .venv
source .venv/bin/activate

# Install backend + UI without asking pip to build PyGObject
pip install --no-deps -e .
```

Then run:

```bash
reshade-shader-manager
```

## Testing against a real game

1. In the UI, click **Game directory…** and choose the game/prefix folder where the `.exe` is located.
2. Optionally choose **Game executable…** (or rely on the directory scan) so architecture becomes `32-bit` or `64-bit`.
3. Choose **Graphics API**, **Variant**, and **Version**.
   - If you leave version as `latest`, RSM resolves it via GitHub *tags*; if the network fails and no cached value exists, you must enter an explicit version like `6.7.3`.
4. Click **Install**, or use **Update / Reinstall Latest** anytime to pull the newest ReShade build for the selected API and variant (no background updater in RSM; ReShade notifies in-game when applicable).
5. Click **Refresh catalog**. Use **Update local clones** if you want newer commits from Git before applying.
6. **Manage shaders…** to enable/disable repos for that game, then **Apply** (recreates projection; does not run `git pull`).

## Data locations (XDG)

Backend uses these defaults:

- Config: `~/.config/reshade-shader-manager/config.json`, `repos.json`, and per-game manifests under `games/`
- Data: `~/.local/share/reshade-shader-manager/` (git clones and downloaded/extracted ReShade)
- Cache: `~/.cache/reshade-shader-manager/pcgw_repos.json`

Per-game projection happens under:

- `<game>/ReShade.ini`
- `<game>/<ReShade proxy dll>.dll` + optional `d3dcompiler_47.dll`
- `<game>/reshade-shaders/Shaders/<repo-id>` and `.../Textures/<repo-id>` — usually *directory* symlinks; non-standard repos may use per-file symlinks preserving paths

## Notes / limitations

- v0.1 supports one active ReShade install state per game directory (reinstall replaces the tracked proxy binaries list; no multi-runtime merging).
- DX8 is reserved in the model/UI but not implemented in v0.1.
- “Remove ReShade” is binary-only: it deletes files tracked in `installed_reshade_files` and does **not** remove shader symlinks, enabled repo state, or `ReShade.ini` by default.

## Packaging

See [packaging/README.md](packaging/README.md) for pip, wheels, Flatpak notes, and distro hints.

## Roadmap (not v0.1)

- CLI for scripting
- DirectX 8 install path (reserved in UI today)
- Multi-profile per game (currently a non-goal)

Details: [CONTEXT.md](CONTEXT.md) and [PROJECT_SPEC.md](PROJECT_SPEC.md).

## Development

See:

- `PROJECT_SPEC.md`
- `IMPLEMENTATION_PLAN.md`
- `CONTEXT.md`

