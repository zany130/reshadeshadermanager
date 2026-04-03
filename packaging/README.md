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
