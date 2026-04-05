"""Command-line interface (no GTK). Entry: ``rsm`` console script."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from reshade_shader_manager.core.catalog_ops import fetch_merged_catalogs
from reshade_shader_manager.core.config import AppConfig, load_config
from reshade_shader_manager.core.error_format import format_exception_for_ui
from reshade_shader_manager.core.exceptions import RSMError, VersionResolutionError
from reshade_shader_manager.core.git_sync import pull_existing_clones_for_catalog
from reshade_shader_manager.core.link_farm import apply_shader_projection
from reshade_shader_manager.core.manifest import GameManifest, load_game_manifest, new_game_manifest
from reshade_shader_manager.core.paths import RsmPaths, get_paths
from reshade_shader_manager.core.plugin_addons_catalog import get_upstream_plugin_addons
from reshade_shader_manager.core.plugin_addons_install import (
    apply_plugin_addon_installation,
    filter_catalog_installable_for_arch,
)
from reshade_shader_manager.core.reshade import check_reshade, install_reshade, remove_reshade_binaries
from reshade_shader_manager.core.targets import detect_game_arch

EXIT_OK = 0
EXIT_USER = 1
EXIT_BUG = 2


def _package_version() -> str:
    try:
        return version("reshade-shader-manager")
    except PackageNotFoundError:
        return "0.0.0"


def _parse_id_list(parts: list[str]) -> set[str]:
    out: set[str] = set()
    for raw in parts:
        for piece in raw.split(","):
            p = piece.strip()
            if p:
                out.add(p)
    return out


def _load_paths_cfg() -> tuple[RsmPaths, AppConfig]:
    paths = get_paths()
    cfg = load_config(paths)
    return paths, cfg


def _resolve_game_dir(s: str) -> Path:
    return Path(s).expanduser().resolve()


def _resolve_manifest(
    paths: RsmPaths,
    cfg: AppConfig,
    game_dir: Path,
    *,
    exe: str | None,
    api: str | None,
    variant: str | None,
) -> GameManifest:
    m = load_game_manifest(paths, game_dir, game_exe=exe) or new_game_manifest(game_dir, game_exe=exe)
    if exe:
        m.game_exe = exe
    exe_path = Path(m.game_exe).expanduser() if m.game_exe else None
    if exe_path and not exe_path.is_file():
        exe_path = None
    try:
        arch = detect_game_arch(game_dir, exe_path)
    except ValueError:
        if m.reshade_arch in ("32", "64"):
            arch = m.reshade_arch
        else:
            raise RSMError(
                "Could not detect 32/64-bit architecture. Use --exe with a Windows .exe, or place "
                "an .exe in the game directory."
            ) from None
    m.reshade_arch = arch
    if api:
        m.graphics_api = api
    if variant:
        m.reshade_variant = variant
    return m


def _cmd_catalog_refresh(_args: argparse.Namespace) -> int:
    paths, cfg = _load_paths_cfg()
    shader_cat, plugin_cat = fetch_merged_catalogs(paths, cfg, force_refresh=True)
    print(
        f"Catalog refreshed: {len(shader_cat)} shader repos; {len(plugin_cat)} plugin add-ons (Addons.ini).",
        file=sys.stdout,
    )
    return EXIT_OK


def _cmd_shaders_update_clones(args: argparse.Namespace) -> int:
    paths, cfg = _load_paths_cfg()
    shader_cat, _ = fetch_merged_catalogs(paths, cfg, force_refresh=args.force_catalog)
    failures = pull_existing_clones_for_catalog(paths, shader_cat)
    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        raise RSMError(f"{len(failures)} repository update(s) failed.")
    print("Local shader clones updated (git pull for each existing clone).", file=sys.stdout)
    return EXIT_OK


def _cmd_shaders_apply(args: argparse.Namespace) -> int:
    desired = _parse_id_list(args.repo)
    if not desired:
        raise RSMError("Specify at least one --repo id.")
    paths, cfg = _load_paths_cfg()
    shader_cat, _ = fetch_merged_catalogs(paths, cfg, force_refresh=False)
    by_id = {r["id"]: r for r in shader_cat}
    game_dir = _resolve_game_dir(args.game_dir)
    apply_shader_projection(
        paths=paths,
        game_dir=game_dir,
        desired_repo_ids=desired,
        catalog_by_id=by_id,
        git_pull=args.git_pull,
    )
    print(f"Shader projection applied for {len(desired)} repo(s).", file=sys.stdout)
    return EXIT_OK


def _cmd_addons_refresh_catalog(_args: argparse.Namespace) -> int:
    paths, cfg = _load_paths_cfg()
    rows = get_upstream_plugin_addons(
        paths,
        ttl_hours=cfg.plugin_addons_catalog_ttl_hours,
        force_refresh=True,
    )
    print(f"Plugin add-on catalog refreshed ({len(rows)} entries from Addons.ini).", file=sys.stdout)
    return EXIT_OK


def _cmd_addons_apply(args: argparse.Namespace) -> int:
    desired = _parse_id_list(args.addon)
    if not desired:
        raise RSMError("Specify at least one --addon id.")
    paths, cfg = _load_paths_cfg()
    _, plugin_cat = fetch_merged_catalogs(paths, cfg, force_refresh=False)
    game_dir = _resolve_game_dir(args.game_dir)
    m = _resolve_manifest(paths, cfg, game_dir, exe=args.exe, api=None, variant=None)
    arch = m.reshade_arch
    if arch not in ("32", "64"):
        raise RSMError("Manifest has invalid reshade_arch; cannot apply plugin add-ons.")
    eligible = filter_catalog_installable_for_arch(plugin_cat, arch=arch)
    catalog_by_id = {r["id"]: r for r in eligible}
    apply_plugin_addon_installation(
        paths=paths,
        manifest=m,
        game_dir=game_dir,
        desired_plugin_addon_ids=desired,
        catalog_by_id=catalog_by_id,
    )
    print(f"Plugin add-ons applied for {len(desired)} id(s).", file=sys.stdout)
    return EXIT_OK


def _cmd_reshade_install(args: argparse.Namespace) -> int:
    paths, cfg = _load_paths_cfg()
    game_dir = _resolve_game_dir(args.game_dir)
    m = _resolve_manifest(paths, cfg, game_dir, exe=args.exe, api=args.api, variant=args.variant)
    ver = (getattr(args, "reshade_version", None) or cfg.default_reshade_version).strip()
    install_reshade(
        paths=paths,
        manifest=m,
        graphics_api=m.graphics_api,
        reshade_version=ver,
        variant=m.reshade_variant,
        create_ini_if_missing=cfg.create_ini_if_missing,
    )
    print(f"ReShade installed ({m.reshade_version}).", file=sys.stdout)
    return EXIT_OK


def _cmd_reshade_update(args: argparse.Namespace) -> int:
    args.reshade_version = "latest"
    return _cmd_reshade_install(args)


def _cmd_reshade_remove(_args: argparse.Namespace) -> int:
    paths, _cfg = _load_paths_cfg()
    game_dir = _resolve_game_dir(_args.game_dir)
    m = load_game_manifest(paths, game_dir)
    if not m:
        raise RSMError("No saved profile (manifest) for this directory.")
    warnings = remove_reshade_binaries(paths=paths, manifest=m)
    for w in warnings:
        print(w, file=sys.stderr)
    print("Removed ReShade binaries (INI and shader links unchanged).", file=sys.stdout)
    return EXIT_OK


def _cmd_reshade_check(_args: argparse.Namespace) -> int:
    paths, _cfg = _load_paths_cfg()
    game_dir = _resolve_game_dir(_args.game_dir)
    m = load_game_manifest(paths, game_dir)
    if not m:
        raise RSMError("No manifest for this directory.")
    cr = check_reshade(m)
    if cr.ok:
        print("Check OK: all tracked ReShade files present.", file=sys.stdout)
        return EXIT_OK
    print("Missing files:", file=sys.stderr)
    for f in cr.missing_files:
        print(f"  {f}", file=sys.stderr)
    return EXIT_USER


def _cmd_game_inspect(args: argparse.Namespace) -> int:
    paths, _cfg = _load_paths_cfg()
    game_dir = _resolve_game_dir(args.game_dir)
    m = load_game_manifest(paths, game_dir, game_exe=args.exe)
    if not m:
        raise RSMError(f"No manifest for {game_dir}")
    if args.json:
        print(json.dumps(m.to_json_dict(), indent=2))
        return EXIT_OK
    print(f"game_dir: {m.game_dir}")
    print(f"game_exe: {m.game_exe}")
    print(f"graphics_api: {m.graphics_api}")
    print(f"reshade_version: {m.reshade_version}")
    print(f"reshade_variant: {m.reshade_variant}")
    print(f"reshade_arch: {m.reshade_arch}")
    print(f"enabled_repo_ids: {m.enabled_repo_ids}")
    print(f"enabled_plugin_addon_ids: {m.enabled_plugin_addon_ids}")
    return EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rsm",
        description="ReShade Shader Manager — command-line interface (uses the same backend as the GTK app).",
        epilog="Exit codes: 0 success, 1 user error, 2 internal error, 130 interrupted (Ctrl+C).",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging on stderr; show tracebacks for unexpected errors.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")

    sub = p.add_subparsers(dest="cmd", required=True)

    cat = sub.add_parser(
        "catalog",
        help="Refresh upstream catalog caches (same as GUI Refresh catalog: PCGW, shader merge, Addons.ini).",
    )
    cat_sub = cat.add_subparsers(dest="catalog_cmd", required=True)
    cat_sub.add_parser("refresh", help="Network refresh of PCGW list, merged shader catalog, and plugin add-on catalog.")

    sh = sub.add_parser(
        "shaders",
        help="Shader repos: apply symlink projection to the game tree, or bulk-update local git clones.",
    )
    sh_sub = sh.add_subparsers(dest="shaders_cmd", required=True)
    sap = sh_sub.add_parser(
        "apply",
        help="Rebuild game reshade-shaders/ symlinks to match selected repo ids (same as GUI Apply).",
    )
    sap.add_argument(
        "--game-dir",
        required=True,
        metavar="DIR",
        help="Game installation root (Wine/Proton prefix path).",
    )
    sap.add_argument(
        "--repo",
        action="append",
        default=[],
        metavar="ID",
        help="Shader repository id (repeat or comma-separated list).",
    )
    sap.add_argument(
        "--git-pull",
        action="store_true",
        help="Run git pull (or clone) for each selected repo before linking.",
    )
    suc = sh_sub.add_parser(
        "update-clones",
        help="git pull every existing shader clone under the data dir (matches GUI “Update local clones”).",
    )
    suc.add_argument(
        "--force-catalog",
        action="store_true",
        help="Refresh network catalogs before updating clones.",
    )

    ad = sub.add_parser(
        "addons",
        help="Official plugin add-ons from the Addons.ini-derived catalog (DLL copies into the game folder).",
    )
    ad_sub = ad.add_subparsers(dest="addons_cmd", required=True)
    adap = ad_sub.add_parser("apply", help="Install or reconcile plugin DLLs for selected add-on ids.")
    adap.add_argument(
        "--game-dir",
        required=True,
        metavar="DIR",
        help="Game installation root (Wine/Proton prefix path).",
    )
    adap.add_argument(
        "--addon",
        action="append",
        default=[],
        metavar="ID",
        help="Plugin add-on id (repeat or comma-separated).",
    )
    adap.add_argument("--exe", help="Optional game .exe for architecture detection.")
    ad_sub.add_parser("refresh-catalog", help="Re-fetch only the official Addons.ini-derived plugin catalog.")

    rs = sub.add_parser("reshade", help="Install, remove, or check ReShade binaries.")
    rs_sub = rs.add_subparsers(dest="reshade_cmd", required=True)

    def add_reshade_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--game-dir",
            required=True,
            metavar="DIR",
            help="Game installation root (Wine/Proton prefix path).",
        )
        sp.add_argument("--exe", help="Optional path to game .exe (helps PE arch detection).")
        sp.add_argument(
            "--api",
            choices=["opengl", "dx8", "dx9", "dx10", "dx11", "dx12"],
            help="Graphics API (default: from manifest or dx11).",
        )
        sp.add_argument("--variant", choices=["standard", "addon"], help="Installer variant.")
        sp.add_argument(
            "--version",
            dest="reshade_version",
            metavar="VER",
            help='ReShade version or "latest" (default: from config or manifest).',
        )

    r_in = rs_sub.add_parser("install", help="Download and install ReShade proxy DLLs into the game dir.")
    add_reshade_common(r_in)
    r_up = rs_sub.add_parser("update", help='Install latest upstream ReShade (same as install with version "latest").')
    add_reshade_common(r_up)
    r_rm = rs_sub.add_parser("remove", help="Remove only files listed in the manifest (ReShade binaries).")
    r_rm.add_argument(
        "--game-dir",
        required=True,
        metavar="DIR",
        help="Game installation root (Wine/Proton prefix path).",
    )
    r_ck = rs_sub.add_parser("check", help="Verify tracked ReShade files exist on disk.")
    r_ck.add_argument(
        "--game-dir",
        required=True,
        metavar="DIR",
        help="Game installation root (Wine/Proton prefix path).",
    )

    gm = sub.add_parser("game", help="Inspect saved per-game profile.")
    gm_sub = gm.add_subparsers(dest="game_cmd", required=True)
    gin = gm_sub.add_parser("inspect", help="Print manifest fields for a game directory.")
    gin.add_argument(
        "--game-dir",
        required=True,
        metavar="DIR",
        help="Game installation root (Wine/Proton prefix path).",
    )
    gin.add_argument("--exe", help="Optional; passed to manifest resolution.")
    gin.add_argument("--json", action="store_true", help="Print JSON (schema matches saved manifest).")

    return p


def _dispatch(args: argparse.Namespace) -> int:
    cmd = args.cmd
    if cmd == "catalog":
        if args.catalog_cmd == "refresh":
            return _cmd_catalog_refresh(args)
    if cmd == "shaders":
        if args.shaders_cmd == "apply":
            return _cmd_shaders_apply(args)
        if args.shaders_cmd == "update-clones":
            return _cmd_shaders_update_clones(args)
    if cmd == "addons":
        if args.addons_cmd == "apply":
            return _cmd_addons_apply(args)
        if args.addons_cmd == "refresh-catalog":
            return _cmd_addons_refresh_catalog(args)
    if cmd == "reshade":
        if args.reshade_cmd == "install":
            return _cmd_reshade_install(args)
        if args.reshade_cmd == "update":
            return _cmd_reshade_update(args)
        if args.reshade_cmd == "remove":
            return _cmd_reshade_remove(args)
        if args.reshade_cmd == "check":
            return _cmd_reshade_check(args)
    if cmd == "game":
        if args.game_cmd == "inspect":
            return _cmd_game_inspect(args)
    raise RuntimeError(f"Unhandled command: {cmd}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    try:
        return _dispatch(args)
    except (RSMError, VersionResolutionError) as e:
        print(format_exception_for_ui(e), file=sys.stderr)
        return EXIT_USER
    except ValueError as e:
        print(format_exception_for_ui(e), file=sys.stderr)
        return EXIT_USER
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        if args.verbose:
            traceback.print_exc()
        else:
            print(f"Internal error: {e}", file=sys.stderr)
        return EXIT_BUG


if __name__ == "__main__":
    raise SystemExit(main())
