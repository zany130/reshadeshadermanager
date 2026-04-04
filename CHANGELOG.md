# Changelog

All notable changes to this project are documented in this file.

## 0.2.0

### Added

- **Plugin add-ons (official upstream only):** Fetch and cache ReShade `Addons.ini` from the reshade-shaders repository, present entries in **Manage plugin add-ons…**, and install/remove plugin DLLs (and optional companion files from archives) into the game directory with manifest tracking. No user-defined add-on catalog; no `plugin_addons.json`.

### Notes

- Version 0.2 focuses on shipping the official Addons.ini–based plugin add-on flow alongside existing ReShade and shader-repository management. Deferred items (CLI, multi-profile per game, Flatpak publication) remain out of scope unless listed in a future release.

## 0.1.0

Initial public shape: GTK 4 UI, ReShade install/remove/check, shader repo catalog (built-in, user `repos.json`, PCGW cache), per-game symlink projection, DX8 (d3d8to9) path where applicable.
