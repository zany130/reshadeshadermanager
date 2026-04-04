# Packaging reshade-shader-manager

## Pip / editable (default)

From the repository root:

```bash
# System GTK 4 + PyGObject (e.g. Fedora)
sudo dnf install gtk4 python3-gobject

python3 -m venv .venv
source .venv/bin/activate
pip install --no-deps -e .
reshade-shader-manager
```

`--no-deps` avoids pip trying to build PyGObject from source when your distro already provides `gi`.

## Wheel / sdist

```bash
pip install build
python -m build
```

Install the wheel in an environment that already has PyGObject and GTK 4.

## Flatpak (not published yet)

A full Flatpak needs:

- GNOME Platform (or Freedesktop) runtime with GTK 4
- Python on the runtime or a bundled CPython
- Application manifest listing `reshade_shader_manager` and metadata

Contributors can start from the [Flatpak Python guide](https://docs.flatpak.org/en/latest/python.html) and this project’s `pyproject.toml` entry point `reshade-shader-manager`.

## Distro packages

Downstream maintainers can vendor this repo and depend on:

- `python3` ≥ 3.10
- GTK 4 and GObject introspection (`python3-gobject`, `gtk4`)

Ensure the console script `reshade-shader-manager` is on `PATH`.

## AppImage (optional)

From the repository root on a **Fedora-like** build machine with `gtk4`, `python3-gobject`, and network access (first run downloads `appimagetool`):

```bash
./packaging/appimage/build_appimage.sh
```

This runs PyInstaller (onedir) and produces `packaging/appimage/reshade-shader-manager-0.5.0-x86_64.AppImage` by default (override with `RSM_APPIMAGE_VERSION`). The bundle is compressed to roughly tens of megabytes; the unpacked tree is much larger because PyInstaller’s GObject/GTK hooks collect typelibs and related data. **GTK 4 is still expected on the host** at runtime.

`packaging/appimage/AppDir/`, `packaging/appimage/tools/`, and `*.AppImage` outputs are gitignored; only the scripts, spec, desktop entry, and icon in `packaging/appimage/` are source-controlled.

To run the artifact: `chmod +x …AppImage && ./…AppImage`. On some systems you may need FUSE or `--appimage-extract-and-run` (see [AppImage docs](https://docs.appimage.org/user-guide/run-appimages.html)).
