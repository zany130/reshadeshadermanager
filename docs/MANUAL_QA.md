# Manual QA checklist (release)

Run **`python3 -m pytest`** — all tests must pass first.

## Mandatory: real prefix / end-to-end (do not skip before tagging)

On a **real game directory** (Wine or Proton prefix), run this flow at least once per major release:

1. **Install ReShade** (GUI or `rsm reshade install`).
2. **Apply shaders** — **Manage shaders…** → **Apply** (or `rsm shaders apply`). On disk, enabled repos project into a **merged** tree:
   - `reshade-shaders/Shaders/…` and `reshade-shaders/Textures/…`
   - **No** per-repo top-level folder (e.g. not `Shaders/<repo-id>/…` as the only layout).
3. **Launch the game** and confirm **effects load** (ReShade overlay / shaders work). Configure `ReShade.ini` search paths in ReShade if needed — RSM does not edit `ReShade.ini`.
4. **Plugin add-on** (if you use one): **Manage plugin add-ons…** → **Apply**. Companion shaders/textures from ZIPs must land in the **same merged** `Shaders/` / `Textures/` trees, preserving paths inside those roots — **not** under `Shaders/addons/<addon-id>/`.
5. **Remove ReShade** — confirm only tracked **binaries** are removed; **`ReShade.ini` stays**; shader symlinks and manifest state for repos/add-ons behave as documented.

Record failures in the issue tracker or release notes.

## Shader repos (merged layout + conflicts)

| Verify |
|--------|
| Two repos with **no** overlapping relative paths → both install under merged `Shaders/` / `Textures/`. |
| Two repos that would share the same path (e.g. same `includes/foo.fxh`) → **later** repo (sorted id order) is **skipped entirely**; log shows a **Shader path conflict** warning. |

## ReShade binaries

| Verify |
|--------|
| **Install** / **Check** / **Remove** (GUI or `rsm reshade …`). |
| **`d3dcompiler_47.dll`:** After install, present if it was missing (downloaded from Lutris mirror into XDG cache, then copied); never overwritten. Stays on disk after **Remove** (not a managed uninstall target). |
| After **Remove**, message indicates binaries removed and **existing `ReShade.ini` left in place** (shader/add-on state unchanged unless you changed it). |

## Plugin add-ons

| Verify |
|--------|
| GUI **Manage plugin add-ons…** or `rsm addons apply …`. |
| Companion files: merged layout only (see mandatory flow above). |

## Other spot checks (time permitting)

| Area | Verify |
|------|--------|
| DX8 | **dx8** + 32-bit path or documented 64-bit limitation. |
| Recent games | List, activation, missing-folder handling. |
| Shader / add-on tables | Search, column sort, **Enabled** while filtered. |
| CLI | `rsm --help`, `catalog refresh`, `shaders update-clones`, `addons refresh-catalog`, `game inspect`. |
| AppImage | Build launches; window/desktop sanity (if you ship an AppImage). |
