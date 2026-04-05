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

This runs PyInstaller (onedir) and produces `packaging/appimage/reshade-shader-manager-<version>-x86_64.AppImage` by default (override with `RSM_APPIMAGE_VERSION`). The `<version>` segment, the `VERSION` passed to `appimagetool`, and **`X-AppImage-Version`** in the bundled `.desktop` file all come from **`pyproject.toml` `[project] version`** unless you set **`RSM_APPIMAGE_VERSION`**. The bundle is compressed to roughly tens of megabytes; the unpacked tree is much larger because PyInstaller’s GObject/GTK hooks collect typelibs and related data. **GTK 4 is still expected on the host** at runtime.

### AppImage icons

Pre-rendered PNGs live under [`packaging/appimage/icons/hicolor/`](appimage/icons/hicolor/) (64–512 px) plus [`packaging/appimage/reshade-shader-manager.png`](appimage/reshade-shader-manager.png) (128×128 copy for the AppDir root). [`make_icon.py`](appimage/make_icon.py) **validates** these files at build time; **ImageMagick is not required** to run `./build_appimage.sh`. The canonical raster source used to produce those sizes is [`packaging/appimage/branding/rsm-logo-source.png`](appimage/branding/rsm-logo-source.png). To regenerate icons after changing the artwork, resize/crop to square offline (e.g. ImageMagick once on a maintainer machine), replace the committed PNGs, then run `python3 packaging/appimage/make_icon.py` to verify.

`packaging/appimage/AppDir/`, `packaging/appimage/tools/`, and `*.AppImage` outputs are gitignored; scripts, spec, desktop entry, and icon assets under `packaging/appimage/` are source-controlled. The AppImage desktop file basename must match `GtkApplication` `application_id` in `reshade_shader_manager/main.py` (currently `io.github.rsm.reshade_shader_manager.desktop`).

To run the artifact: `chmod +x …AppImage && ./…AppImage`. On some systems you may need FUSE or `--appimage-extract-and-run` (see [AppImage docs](https://docs.appimage.org/user-guide/run-appimages.html)).
