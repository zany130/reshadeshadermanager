"""Main GTK window: target selection, ReShade actions, shader catalog, log panel."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from gi.repository import Gio, GLib, Gtk, Pango

from reshade_shader_manager.core.catalog_ops import fetch_merged_catalogs
from reshade_shader_manager.core.config import load_config
from reshade_shader_manager.core.exceptions import RSMError, VersionResolutionError
from reshade_shader_manager.core.manifest import (
    GameManifest,
    load_game_manifest,
    new_game_manifest,
    save_game_manifest,
)
from reshade_shader_manager.core.paths import get_paths
from reshade_shader_manager.core.recent_games import list_recent_games
from reshade_shader_manager.core.git_sync import pull_existing_clones_for_catalog
from reshade_shader_manager.core.pcgw import get_pcgw_repos
from reshade_shader_manager.core.plugin_addons_catalog import get_upstream_plugin_addons
from reshade_shader_manager.core.repos import merged_catalog
from reshade_shader_manager.core.reshade import check_reshade, install_reshade, remove_reshade_binaries
from reshade_shader_manager.core.targets import detect_game_arch
from reshade_shader_manager.core.ui_state import WindowUiState, load_window_ui_state, save_window_ui_state
from reshade_shader_manager.ui.add_repo_dialog import AddRepoDialog
from reshade_shader_manager.ui.plugin_addon_dialog import PluginAddonWindow
from reshade_shader_manager.ui.error_format import format_exception_for_ui
from reshade_shader_manager.ui.log_view import LogPanel, setup_gui_logging
from reshade_shader_manager.ui.shader_dialog import ShaderRepoWindow

log = logging.getLogger(__name__)

API_ROWS: list[tuple[str, str]] = [
    ("opengl", "OpenGL"),
    ("dx8", "DirectX 8 (d3d8to9 + ReShade as D3D9; 32-bit only)"),
    ("dx9", "DirectX 9"),
    ("dx10", "DirectX 10"),
    ("dx11", "DirectX 11"),
    ("dx12", "DirectX 12"),
]


def _section(title: str) -> Gtk.Label:
    l = Gtk.Label(label=title, xalign=0.0)
    l.add_css_class("title-4")
    return l


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        paths = get_paths()
        cfg = load_config(paths)
        ui = load_window_ui_state(paths.ui_state_json())
        dw = ui.width if ui else 760
        dh = ui.height if ui else 700
        super().__init__(
            application=application,
            title="ReShade Shader Manager",
            default_width=dw,
            default_height=dh,
        )
        self._paths = paths
        self._config = cfg
        self._pending_maximize = bool(ui and ui.maximized)
        self._catalog: list[dict[str, str]] | None = None
        self._plugin_addon_catalog: list[dict[str, str]] | None = None
        self._catalog_hydrated: bool = False
        self._game_dir: Path | None = None
        self._exe_path: Path | None = None
        self._arch_display = "—"
        self._arch_value = ""
        self._recent_paths: list[Path] = []

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_margin_start(14)
        body.set_margin_end(14)
        body.set_margin_top(14)
        body.set_margin_bottom(8)
        body.set_vexpand(True)

        body.append(_section("Target"))
        body.append(self._build_target_section())

        body.append(_section("ReShade"))
        body.append(self._build_reshade_section())

        body.append(_section("Shader repositories"))
        body.append(self._build_shader_section())

        body.append(_section("Plugin add-ons"))
        body.append(self._build_plugin_addon_section())

        outer.append(body)

        log_hdr = Gtk.Label(label="Log", xalign=0.0)
        log_hdr.set_margin_start(14)
        log_hdr.set_margin_top(4)
        outer.append(log_hdr)

        self._log_panel = LogPanel()
        self._log_panel.set_margin_start(10)
        self._log_panel.set_margin_end(10)
        self._log_panel.set_margin_bottom(10)
        outer.append(self._log_panel)

        self.set_child(outer)

        setup_gui_logging(self._log_panel)
        log.info("RSM UI ready (config %s)", self._paths.config_dir)

        self._set_catalog_dependent_sensitive(False)
        GLib.idle_add(self._schedule_initial_catalog_hydration)
        GLib.idle_add(self._idle_refresh_recent_games)

        self.connect("close-request", self._on_close_request)
        if self._pending_maximize:

            def _max_once() -> bool:
                if self._pending_maximize:
                    self._pending_maximize = False
                    self.maximize()
                return False

            GLib.idle_add(_max_once)

    def _build_target_section(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_hexpand(True)

        top = Gtk.Grid(column_spacing=10, row_spacing=8)
        top.set_hexpand(True)
        self._game_label = Gtk.Label(label="(not set)", xalign=0.0, hexpand=True)
        self._game_label.set_ellipsize(Pango.EllipsizeMode.END)
        btn_dir = Gtk.Button(label="Game directory…")
        btn_dir.connect("clicked", self._on_pick_game_dir)
        top.attach(self._game_label, 0, 0, 1, 1)
        top.attach(btn_dir, 1, 0, 1, 1)
        outer.append(top)

        recent_hdr = Gtk.Label(label="Recent games", xalign=0.0)
        recent_hdr.add_css_class("title-4")
        outer.append(recent_hdr)

        self._recent_listbox = Gtk.ListBox()
        self._recent_listbox.set_activate_on_single_click(True)
        self._recent_listbox.set_hexpand(True)
        self._recent_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._recent_listbox.connect("row-activated", self._on_recent_row_activated)
        outer.append(self._recent_listbox)

        self._recent_empty = Gtk.Label(label="No saved games yet.", xalign=0.0)
        self._recent_empty.set_opacity(0.65)
        self._recent_listbox.set_visible(False)
        self._recent_empty.set_visible(True)
        outer.append(self._recent_empty)

        rest = Gtk.Grid(column_spacing=10, row_spacing=8)
        rest.set_hexpand(True)
        self._exe_label = Gtk.Label(label="(none)", xalign=0.0, hexpand=True)
        self._exe_label.set_ellipsize(Pango.EllipsizeMode.END)
        btn_exe = Gtk.Button(label="Game executable…")
        btn_exe.connect("clicked", self._on_pick_exe)
        btn_clear = Gtk.Button(label="Clear EXE")
        btn_clear.connect("clicked", self._on_clear_exe)
        exe_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        exe_row.append(self._exe_label)
        exe_row.append(btn_exe)
        exe_row.append(btn_clear)
        rest.attach(exe_row, 0, 0, 2, 1)

        self._arch_label = Gtk.Label(label="Architecture: —", xalign=0.0)
        rest.attach(self._arch_label, 0, 1, 2, 1)
        outer.append(rest)

        return outer

    def _idle_refresh_recent_games(self) -> bool:
        self._refresh_recent_games()
        return False

    def _refresh_recent_games(self) -> None:
        entries = list_recent_games(self._paths)
        self._recent_paths = [e.game_dir for e in entries]
        self._recent_listbox.remove_all()
        if not entries:
            self._recent_listbox.set_visible(False)
            self._recent_empty.set_visible(True)
            return
        self._recent_listbox.set_visible(True)
        self._recent_empty.set_visible(False)
        for entry in entries:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t1 = Gtk.Label(label=entry.display_name, xalign=0.0, hexpand=True)
            t1.set_ellipsize(Pango.EllipsizeMode.END)
            t2 = Gtk.Label(label=entry.path_short, xalign=0.0, hexpand=True)
            t2.set_ellipsize(Pango.EllipsizeMode.END)
            t2.set_opacity(0.75)
            box.append(t1)
            box.append(t2)
            row.set_child(box)
            row.set_tooltip_text(str(entry.game_dir))
            self._recent_listbox.append(row)

    def _on_recent_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        idx = row.get_index()
        if idx < 0 or idx >= len(self._recent_paths):
            return
        path = self._recent_paths[idx]
        if not path.is_dir():
            self._show_error(
                "That game folder no longer exists or is not accessible:\n" + str(path)
            )
            return
        self._apply_game_directory(path)
        self._refresh_recent_games()

    def _build_reshade_section(self) -> Gtk.Widget:
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_hexpand(True)

        grid.attach(Gtk.Label(label="Graphics API", xalign=1.0), 0, 0, 1, 1)
        self._api_combo = Gtk.ComboBoxText()
        for api_id, label in API_ROWS:
            self._api_combo.append(api_id, label)
        self._api_combo.set_active_id("dx11")
        self._api_combo.connect("changed", lambda _c: self._persist_target_metadata())
        grid.attach(self._api_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Variant", xalign=1.0), 0, 1, 1, 1)
        self._variant_combo = Gtk.ComboBoxText()
        self._variant_combo.append("standard", "Standard installer")
        self._variant_combo.append("addon", "Addon installer")
        self._variant_combo.set_active_id(self._config.default_variant)
        self._variant_combo.connect("changed", lambda _c: self._persist_target_metadata())
        grid.attach(self._variant_combo, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Version", xalign=1.0), 0, 2, 1, 1)
        self._version_entry = Gtk.Entry()
        self._version_entry.set_hexpand(True)
        self._version_entry.set_placeholder_text("latest or e.g. 6.7.3")
        self._version_entry.set_text(self._config.default_reshade_version)
        self._version_entry.connect("changed", self._on_version_changed)
        grid.attach(self._version_entry, 1, 2, 1, 1)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bi = Gtk.Button(label="Install")
        bi.add_css_class("suggested-action")
        bi.connect("clicked", self._on_install)
        bu = Gtk.Button(label="Update / Reinstall Latest")
        bu.set_tooltip_text(
            "Resolve the current latest ReShade from GitHub (or cache) and reinstall using the "
            "selected graphics API and standard/addon variant. Does not run in the background."
        )
        bu.connect("clicked", self._on_update_reinstall_latest)
        br = Gtk.Button(label="Remove binaries")
        br.connect("clicked", self._on_remove)
        bc = Gtk.Button(label="Check")
        bc.connect("clicked", self._on_check)
        row.append(bi)
        row.append(bu)
        row.append(br)
        row.append(bc)
        grid.attach(row, 0, 3, 2, 1)

        return grid

    def _on_version_changed(self, _entry: Gtk.Entry) -> None:
        self._persist_target_metadata()

    def _build_shader_section(self) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_hexpand(True)
        self._btn_refresh_catalog = Gtk.Button(label="Refresh catalog")
        self._btn_refresh_catalog.set_tooltip_text(
            "Re-fetch shader and plugin add-on lists from the network (uses cache when offline)."
        )
        self._btn_refresh_catalog.connect("clicked", self._on_refresh_catalog)
        self._btn_update_clones = Gtk.Button(label="Update local clones")
        self._btn_update_clones.set_tooltip_text(
            "Run git pull for repos that already have a clone under ~/.local/share/…/repos/"
        )
        self._btn_update_clones.connect("clicked", self._on_update_local_clones)
        self._btn_add_repo = Gtk.Button(label="Add repository…")
        self._btn_add_repo.connect("clicked", self._on_add_repository)
        self._btn_manage_shaders = Gtk.Button(label="Manage shaders…")
        self._btn_manage_shaders.add_css_class("suggested-action")
        self._btn_manage_shaders.connect("clicked", self._on_manage_shaders)
        row.append(self._btn_refresh_catalog)
        row.append(self._btn_update_clones)
        row.append(self._btn_add_repo)
        row.append(self._btn_manage_shaders)
        return row

    def _build_plugin_addon_section(self) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_hexpand(True)
        self._btn_manage_plugin_addons = Gtk.Button(label="Manage plugin add-ons…")
        self._btn_manage_plugin_addons.set_tooltip_text(
            "Copy official upstream (Addons.ini) ReShade plugin DLLs into the game folder "
            "(not the ReShade installer “addon” variant)."
        )
        self._btn_manage_plugin_addons.connect("clicked", self._on_manage_plugin_addons)
        row.append(self._btn_manage_plugin_addons)
        return row

    def _on_close_request(self, *_args) -> bool:
        try:
            save_window_ui_state(
                self._paths.ui_state_json(),
                WindowUiState(
                    width=self.get_width(),
                    height=self.get_height(),
                    maximized=self.is_maximized(),
                ),
            )
        except OSError as e:
            log.debug("Could not save window geometry: %s", e)
        return False

    def _show_error(self, message: str) -> None:
        md = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=message,
        )
        md.present()
        md.connect("response", lambda w, *_: w.destroy())

    def _show_info(self, message: str) -> None:
        md = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=message,
        )
        md.present()
        md.connect("response", lambda w, *_: w.destroy())

    def _on_pick_game_dir(self, _btn: Gtk.Button) -> None:
        fd = Gtk.FileDialog(title="Select game directory")
        fd.select_folder(self, None, self._on_game_folder_finish)

    def _on_game_folder_finish(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if gfile is None:
            return
        path = gfile.get_path()
        if path:
            self._apply_game_directory(Path(path))

    def _on_pick_exe(self, _btn: Gtk.Button) -> None:
        if not self._game_dir:
            self._show_error("Choose a game directory first.")
            return
        fd = Gtk.FileDialog(title="Select game executable (optional)")
        filt = Gtk.FileFilter()
        filt.set_name("Windows executables")
        filt.add_suffix("exe")
        fd.set_default_filter(filt)
        fd.open(self, None, self._on_exe_finish)

    def _on_exe_finish(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        if gfile is None:
            return
        p = gfile.get_path()
        if p:
            self._exe_path = Path(p)
            self._exe_label.set_text(p)
            self._refresh_arch()
            self._persist_target_metadata()

    def _on_clear_exe(self, _btn: Gtk.Button) -> None:
        self._exe_path = None
        self._exe_label.set_text("(none)")
        self._refresh_arch()
        self._persist_target_metadata()

    def _apply_game_directory(self, path: Path) -> None:
        self._game_dir = path.resolve()
        self._game_label.set_text(str(self._game_dir))
        m = load_game_manifest(self._paths, self._game_dir)
        if m and m.game_exe:
            self._exe_path = Path(m.game_exe)
            self._exe_label.set_text(m.game_exe)
        else:
            self._exe_path = None
            self._exe_label.set_text("(none)")
        if m:
            if any(m.graphics_api == a for a, _ in API_ROWS):
                self._api_combo.set_active_id(m.graphics_api)
            self._variant_combo.set_active_id(m.reshade_variant)
            self._version_entry.set_text(m.reshade_version or self._config.default_reshade_version)
        else:
            self._api_combo.set_active_id("dx11")
            self._variant_combo.set_active_id(self._config.default_variant)
            self._version_entry.set_text(self._config.default_reshade_version)
        self._refresh_arch()
        self._persist_target_metadata()
        self._refresh_recent_games()

    def _refresh_arch(self) -> None:
        if not self._game_dir or not self._game_dir.is_dir():
            self._arch_label.set_text("Architecture: —")
            self._arch_value = ""
            return
        try:
            arch = detect_game_arch(self._game_dir, self._exe_path)
            self._arch_label.set_text(f"Architecture: {arch}-bit (PE)")
            self._arch_value = arch
        except ValueError as e:
            log.warning("%s", e)
            self._arch_label.set_text("Architecture: unknown (add .exe)")
            self._arch_value = ""

    def _sync_manifest_from_ui(self):
        assert self._game_dir is not None
        m = load_game_manifest(self._paths, self._game_dir) or new_game_manifest(
            self._game_dir,
            game_exe=str(self._exe_path) if self._exe_path else None,
        )
        m.game_exe = str(self._exe_path) if self._exe_path else None
        api = self._api_combo.get_active_id()
        if api:
            m.graphics_api = api
        vid = self._variant_combo.get_active_id()
        if vid:
            m.reshade_variant = vid
        ver = self._version_entry.get_text().strip()
        if ver:
            m.reshade_version = ver
        if self._arch_value in ("32", "64"):
            m.reshade_arch = self._arch_value
        return m

    def _persist_target_metadata(self) -> None:
        if not self._game_dir:
            return
        try:
            m = self._sync_manifest_from_ui()
            save_game_manifest(self._paths, m)
        except Exception as e:  # noqa: BLE001
            log.debug("persist target skipped: %s", e)

    def _run_worker(self, task, on_ok, on_err) -> None:
        def work() -> None:
            try:
                result = task()

                def dispatch_ok() -> bool:
                    on_ok(result)
                    return False

                GLib.idle_add(dispatch_ok)
            except Exception as e:  # noqa: BLE001
                log.exception("Background task failed")

                def dispatch_err() -> bool:
                    on_err(e)
                    return False

                GLib.idle_add(dispatch_err)

        threading.Thread(target=work, daemon=True).start()

    def _on_install(self, _btn: Gtk.Button) -> None:
        if not self._game_dir:
            self._show_error("Select a game directory.")
            return
        if self._arch_value not in ("32", "64"):
            self._show_error(
                "Could not detect 32/64-bit architecture. Add a Windows .exe (optional chooser) "
                "or place an .exe in the game folder."
            )
            return
        ver = self._version_entry.get_text().strip() or self._config.default_reshade_version
        m = self._sync_manifest_from_ui()

        def task():
            return install_reshade(
                paths=self._paths,
                manifest=m,
                graphics_api=m.graphics_api,
                reshade_version=ver,
                variant=m.reshade_variant,
                create_ini_if_missing=self._config.create_ini_if_missing,
            )

        def ok(_r) -> None:
            log.info("Install finished.")
            self._show_info("ReShade install finished.")

        def err(e: BaseException) -> None:
            if isinstance(e, VersionResolutionError):
                self._show_error(str(e))
            elif isinstance(e, RSMError):
                self._show_error(str(e))
            else:
                self._show_error(format_exception_for_ui(e))

        self._run_worker(task, ok, err)

    def _on_update_reinstall_latest(self, _btn: Gtk.Button) -> None:
        if not self._game_dir:
            self._show_error("Select a game directory.")
            return
        if self._arch_value not in ("32", "64"):
            self._show_error(
                "Could not detect 32/64-bit architecture. Add a Windows .exe (optional chooser) "
                "or place an .exe in the game folder."
            )
            return
        m = self._sync_manifest_from_ui()

        def task():
            return install_reshade(
                paths=self._paths,
                manifest=m,
                graphics_api=m.graphics_api,
                reshade_version="latest",
                variant=m.reshade_variant,
                create_ini_if_missing=self._config.create_ini_if_missing,
            )

        def ok(result: GameManifest) -> None:
            ver = result.reshade_version
            self._version_entry.set_text(ver)
            self._persist_target_metadata()
            log.info("ReShade update/reinstall finished (%s).", ver)
            self._show_info(f"ReShade updated to {ver}.")

        def err(e: BaseException) -> None:
            if isinstance(e, VersionResolutionError):
                self._show_error(str(e))
            elif isinstance(e, RSMError):
                self._show_error(str(e))
            else:
                self._show_error(format_exception_for_ui(e))

        self._run_worker(task, ok, err)

    def _on_remove(self, _btn: Gtk.Button) -> None:
        if not self._game_dir:
            self._show_error("Select a game directory.")
            return
        m = load_game_manifest(self._paths, self._game_dir)
        if not m:
            self._show_error("No saved profile for this directory.")
            return

        def task():
            return remove_reshade_binaries(paths=self._paths, manifest=m)

        def ok(warnings: list[str]) -> None:
            for w in warnings:
                log.warning("%s", w)
            self._show_info("Removed ReShade binaries (INI and shader links unchanged).")

        def err(e: BaseException) -> None:
            self._show_error(format_exception_for_ui(e))

        self._run_worker(task, ok, err)

    def _on_check(self, _btn: Gtk.Button) -> None:
        if not self._game_dir:
            self._show_error("Select a game directory.")
            return
        m = load_game_manifest(self._paths, self._game_dir)
        if not m:
            self._show_error("No manifest for this directory.")
            return
        cr = check_reshade(m)
        if cr.ok:
            self._show_info("Check OK: all tracked ReShade files present.")
        else:
            self._show_error("Missing files:\n" + "\n".join(cr.missing_files))

    def _fetch_catalogs(self, *, force_refresh: bool) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        return fetch_merged_catalogs(self._paths, self._config, force_refresh=force_refresh)

    def _set_catalog_dependent_sensitive(self, sensitive: bool) -> None:
        if hasattr(self, "_btn_update_clones"):
            self._btn_update_clones.set_sensitive(sensitive)
            self._btn_manage_shaders.set_sensitive(sensitive)
        if hasattr(self, "_btn_manage_plugin_addons"):
            self._btn_manage_plugin_addons.set_sensitive(sensitive)

    def _apply_catalog_result(
        self,
        pair: tuple[list[dict[str, str]], list[dict[str, str]]],
    ) -> None:
        cat, plugin_cat = pair
        self._catalog = cat
        self._plugin_addon_catalog = plugin_cat
        self._catalog_hydrated = True
        self._set_catalog_dependent_sensitive(True)
        log.info(
            "Catalog loaded: %d shader repos; %d plugin add-ons (official Addons.ini)",
            len(cat),
            len(plugin_cat),
        )

    def _schedule_initial_catalog_hydration(self) -> bool:
        self._run_worker(
            lambda: self._fetch_catalogs(force_refresh=False),
            self._on_initial_catalog_ok,
            self._on_initial_catalog_err,
        )
        return False

    def _on_initial_catalog_ok(
        self,
        pair: tuple[list[dict[str, str]], list[dict[str, str]]],
    ) -> None:
        self._apply_catalog_result(pair)

    def _on_initial_catalog_err(self, e: BaseException) -> None:
        log.exception("Initial catalog load failed")
        self._show_error(
            "Could not load shader/plugin catalogs from cache or network:\n"
            f"{format_exception_for_ui(e)}\n\n"
            "Use “Refresh catalog” to retry."
        )

    def _on_refresh_catalog(self, _btn: Gtk.Button) -> None:
        def task():
            return self._fetch_catalogs(force_refresh=True)

        def ok(pair: tuple[list[dict[str, str]], list[dict[str, str]]]) -> None:
            self._apply_catalog_result(pair)

        def err(e: BaseException) -> None:
            self._show_error(f"Catalog refresh failed:\n{format_exception_for_ui(e)}")

        self._run_worker(task, ok, err)

    def _on_update_local_clones(self, _btn: Gtk.Button) -> None:
        if not self._catalog_hydrated or self._catalog is None:
            self._show_error("Catalog is still loading or failed to load. Use “Refresh catalog” to retry.")
            return

        def task():
            return pull_existing_clones_for_catalog(self._paths, self._catalog)

        def ok(failures: list[str]) -> None:
            if failures:
                self._show_error(
                    "Some repositories failed to update:\n\n" + "\n".join(failures[:20])
                    + ("\n…" if len(failures) > 20 else "")
                )
            else:
                self._show_info(
                    "Local clones updated (git pull ran for each catalog repo that already had a clone)."
                )

        def err(e: BaseException) -> None:
            self._show_error(format_exception_for_ui(e))

        self._run_worker(task, ok, err)

    def _on_add_repository(self, _btn: Gtk.Button) -> None:
        def refresh_catalog() -> None:
            try:
                pcgw = get_pcgw_repos(
                    self._paths,
                    ttl_hours=self._config.pcgw_cache_ttl_hours,
                    force_refresh=False,
                )
                self._catalog = merged_catalog(self._paths, pcgw)
                self._plugin_addon_catalog = get_upstream_plugin_addons(
                    self._paths,
                    ttl_hours=self._config.plugin_addons_catalog_ttl_hours,
                    force_refresh=False,
                )
                self._catalog_hydrated = True
                self._set_catalog_dependent_sensitive(True)
                log.info(
                    "Catalog reloaded after adding user repo (%d shader repos, %d plugin add-ons)",
                    len(self._catalog),
                    len(self._plugin_addon_catalog),
                )
            except Exception as e:  # noqa: BLE001
                log.warning("Could not reload catalog: %s", e)

        win = AddRepoDialog(parent=self, paths=self._paths, on_saved=refresh_catalog)
        win.present()

    def _on_manage_shaders(self, _btn: Gtk.Button) -> None:
        if not self._game_dir:
            self._show_error("Select a game directory.")
            return
        if not self._catalog_hydrated or self._catalog is None:
            self._show_error("Catalog is still loading or failed to load. Use “Refresh catalog” to retry.")
            return
        win = ShaderRepoWindow(
            parent=self,
            paths=self._paths,
            app_config=self._config,
            game_dir=self._game_dir,
            catalog=self._catalog,
            on_done=lambda: log.info("Shader dialog closed after apply."),
        )
        win.present()

    def _on_manage_plugin_addons(self, _btn: Gtk.Button) -> None:
        if not self._game_dir:
            self._show_error("Select a game directory.")
            return
        if self._arch_value not in ("32", "64"):
            self._show_error(
                "Could not detect 32/64-bit architecture. Add a Windows .exe so add-on "
                "downloads match the game."
            )
            return
        if not self._catalog_hydrated or self._plugin_addon_catalog is None:
            self._show_error("Catalog is still loading or failed to load. Use “Refresh catalog” to retry.")
            return
        win = PluginAddonWindow(
            parent=self,
            paths=self._paths,
            game_dir=self._game_dir,
            catalog=list(self._plugin_addon_catalog),
            sync_manifest=self._sync_manifest_from_ui,
            on_done=lambda: log.info("Plugin add-on dialog closed after apply."),
        )
        win.present()
