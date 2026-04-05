# Changelog

All notable changes to this project are documented in this file.

## 0.8.0

Release-candidate stabilization: clarity, consistency, and regression coverage—no new major features.

### Changed

- **CLI (`rsm`):** Clearer subcommand descriptions; `--game-dir` documented consistently with `DIR` metavar; `--help` epilog documents exit codes (`0` / `1` / `2` / `130`). `GameManifest` import fixed for type accuracy; `ValueError` paths use the same exception formatter as other user-facing errors.
- **GTK:** “Manage shaders” / “Manage plugin add-ons” dialog titles align with buttons; search fields clarify which columns are filtered; recent-games empty state wording (“No recent games yet.”).

### Added

- **Tests:** CLI coverage for `reshade check` / `reshade remove` without a manifest, and `addons apply` without `--addon`.

### Documentation

- **README:** GTK/CLI wording updated (removed stale version labels); **dx8** listed in graphics APIs; **CLI exit codes** table; roadmap note for v1.0 direction.

## 0.7.1

### Fixed

- **AppImage / desktop integration:** The packaged `.desktop` file is named `io.github.rsm.reshade_shader_manager.desktop` so its basename matches the GTK `application_id` in `main.py`. This aligns with the [GTK requirement](https://docs.gtk.org/gtk4/class.Application.html) that the desktop entry ID match the application ID, fixing missing or generic icons in the Wayland titlebar and in app menus that resolve icons via the desktop file.

## 0.7.0

### Added

- **AppImage:** Pre-rendered hicolor PNGs (64–512), `reshade-shader-manager.png` at AppDir root, desktop `Categories`/`Keywords`, and `make_icon.py` validation so the build does not require ImageMagick.
- **GTK:** Main window sets `icon_name` to `reshade-shader-manager` for window and taskbar integration when the icon theme provides that name.

### Documentation

- `packaging/README.md`: where AppImage icons live and how to regenerate PNGs offline.

### Packaging

- `build_appimage.sh` reads the AppImage filename version from `pyproject.toml` unless `RSM_APPIMAGE_VERSION` is set.

## 0.6.0

### Changed

- **Manage shaders…** and **Manage plugin add-ons…** use a **searchable table** (`Gtk.ColumnView`) with columns **Enabled**, **Name**, **Author**, **Description**, and **Source**, default **Name** sort, and a **search bar** (case-insensitive substring over those fields). **Column headers** sort the table (`Gtk.SortListModel` / `Gtk.StringSorter`); click a header to sort, click again to reverse. The **Enabled** column sorts unchecked-before-checked when ascending (and the opposite when descending). Enable/disable toggles and **Apply** behavior are unchanged; selection state is kept when filtering rows.

### Added

- **`ui/catalog_search`** — shared substring matching helper (used by both dialogs).
- **`ui/catalog_column_view`** — shared list model, filter, and column view setup.

## 0.5.0

### Added

- **CLI (`rsm`):** A stdlib `argparse` command-line interface over the same backend as the GTK app (no GTK import). Console script **`rsm`** alongside **`reshade-shader-manager`**. Commands include:
  - `rsm catalog refresh` — re-fetch PCGW shader list, merged shader catalog, and official Addons.ini plugin catalog (same as GUI **Refresh catalog**).
  - `rsm shaders apply` / `rsm shaders update-clones` — shader projection with optional `--git-pull`; bulk `git pull` for existing clones (same as **Update local clones**).
  - `rsm addons apply` / `rsm addons refresh-catalog` — plugin add-on install/reconcile and optional Addons.ini-only metadata refresh.
  - `rsm reshade install|update|remove|check` — ReShade binary install/update/remove/check.
  - `rsm game inspect` — print saved manifest (optional `--json`).
- **`core/catalog_ops.fetch_merged_catalogs`** — shared catalog fetch used by the GUI and CLI.
- **`core/error_format`** — exception formatting shared by CLI and UI (UI module re-exports for compatibility).

## 0.4.0

### Added

- **Recent games:** The Target section lists up to **6** previously saved games from `~/.config/.../games/*.json`, ordered by manifest **file modification time** (newest first). Invalid files are skipped while scanning so the list can still fill with valid entries; duplicate installs are deduplicated by canonical game directory (newest manifest file wins). Each row shows a short display name (from `game_exe` when set, otherwise the game folder name) and an optional shortened path. Click a row to select that game the same way as **Game directory…**. If the folder no longer exists, a clear error is shown. **No new manifest fields or schema changes.**

### Notes

- Version 0.4 is a usability-focused release: quicker game switching without extra configuration. Shader repositories, plugin add-ons (Addons.ini), ReShade install flows, and manifest formats from v0.3 are unchanged aside from this UI addition.

## 0.3.0

### Added

- **Startup catalog hydration:** Shader and plugin add-on catalogs load in the background after the window appears (cache-first, same TTL/stale behavior as before). **Manage shaders…**, **Manage plugin add-ons…**, and **Update local clones** are disabled until that load finishes.
- **Human-readable game manifests:** Preferred path `games/{slug}-{fp8}.json` (`fp8` = first 8 hex chars of the existing per-directory hash). Legacy `games/<full-sha256>.json` files are still found when loading a game and are migrated lazily on load/save (no full-directory scan at startup).

### Changed

- **Refresh catalog** is the only action that forces a network refresh (`force_refresh=True`); its tooltip describes that behavior.
- **PCGW user-agent** string uses the installed package version from metadata.

## 0.2.0

### Added

- **Plugin add-ons (official upstream only):** Fetch and cache ReShade `Addons.ini` from the reshade-shaders repository, present entries in **Manage plugin add-ons…**, and install/remove plugin DLLs (and optional companion files from archives) into the game directory with manifest tracking. No user-defined add-on catalog; no `plugin_addons.json`.

### Notes

- Version 0.2 focuses on shipping the official Addons.ini–based plugin add-on flow alongside existing ReShade and shader-repository management. Deferred items (CLI, multi-profile per game, Flatpak publication) remain out of scope unless listed in a future release.

## 0.1.0

Initial public shape: GTK 4 UI, ReShade install/remove/check, shader repo catalog (built-in, user `repos.json`, PCGW cache), per-game symlink projection, DX8 (d3d8to9) path where applicable.
