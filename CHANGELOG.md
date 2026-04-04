# Changelog

All notable changes to this project are documented in this file.

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
