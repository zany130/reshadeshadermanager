"""ReShade.ini: replace or add EffectSearchPaths / TextureSearchPaths only (v0.1)."""

from __future__ import annotations

from pathlib import Path

# Wine/ReShade expect Windows-style paths here (per PROJECT_SPEC.md)
DEFAULT_EFFECT_SEARCH = r".\reshade-shaders\Shaders\**"
DEFAULT_TEXTURE_SEARCH = r".\reshade-shaders\Textures\**"


def _split_key_value(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith(";") or s.startswith("#"):
        return None
    if "=" not in s:
        return None
    key, _, rest = s.partition("=")
    return key.strip(), rest.strip()


def _with_value(line: str, new_value: str) -> str:
    prefix, sep, _old = line.partition("=")
    if not sep:
        return line
    nl = "\n" if line.endswith("\n") else ""
    return f"{prefix.rstrip()}={new_value}{nl}"


def patch_reshade_search_paths(
    content: str | None,
    *,
    effect_search_paths: str = DEFAULT_EFFECT_SEARCH,
    texture_search_paths: str = DEFAULT_TEXTURE_SEARCH,
) -> str:
    """
    In ``[GENERAL]``, replace the first ``EffectSearchPaths`` / ``TextureSearchPaths``
    value each, or add missing keys at the end of that section. All other content
    is preserved.

    If there is no ``[GENERAL]`` section, prepend one. If ``content`` is empty,
    return a minimal INI.
    """
    minimal = (
        "[GENERAL]\n"
        f"EffectSearchPaths={effect_search_paths}\n"
        f"TextureSearchPaths={texture_search_paths}\n"
    )
    if not content or not content.strip():
        return minimal

    lines = content.splitlines(keepends=True)

    general_start: int | None = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "[general]":
            general_start = i
            break

    if general_start is None:
        return minimal + content

    general_end = len(lines)
    for j in range(general_start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("[") and s.endswith("]"):
            general_end = j
            break

    before = lines[:general_start]
    section = list(lines[general_start:general_end])
    after = lines[general_end:]

    effect_idx: int | None = None
    texture_idx: int | None = None
    for k, line in enumerate(section):
        kv = _split_key_value(line)
        if kv is None:
            continue
        key = kv[0].lower()
        if key == "effectsearchpaths" and effect_idx is None:
            effect_idx = k
        elif key == "texturesearchpaths" and texture_idx is None:
            texture_idx = k

    if effect_idx is not None:
        section[effect_idx] = _with_value(section[effect_idx], effect_search_paths)
    else:
        section.insert(1, f"EffectSearchPaths={effect_search_paths}\n")

    texture_idx = None
    for k, line in enumerate(section):
        kv = _split_key_value(line)
        if kv and kv[0].lower() == "texturesearchpaths":
            texture_idx = k
            break
    if texture_idx is not None:
        section[texture_idx] = _with_value(section[texture_idx], texture_search_paths)
    else:
        section.append(f"TextureSearchPaths={texture_search_paths}\n")

    return "".join(before + section + after)


def read_ini(path: Path | str) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def write_ini(path: Path | str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(p)


def ensure_search_paths_in_ini(
    game_dir: Path | str,
    *,
    create_if_missing: bool,
    effect_search_paths: str = DEFAULT_EFFECT_SEARCH,
    texture_search_paths: str = DEFAULT_TEXTURE_SEARCH,
) -> None:
    """Load ``<game_dir>/ReShade.ini``, patch keys, write back."""
    gd = Path(game_dir)
    ini_path = gd / "ReShade.ini"
    existing = read_ini(ini_path)
    if existing is None and not create_if_missing:
        return
    new_body = patch_reshade_search_paths(
        existing,
        effect_search_paths=effect_search_paths,
        texture_search_paths=texture_search_paths,
    )
    write_ini(ini_path, new_body)
