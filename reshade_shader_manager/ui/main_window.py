"""Main GTK window: target selection, ReShade actions, shader catalog, log panel."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from gi.repository import Gio, GLib, Gtk, Pango

from reshade_shader_manager.core.config import load_config
from reshade_shader_manager.core.exceptions import RSMError, VersionResolutionError
from reshade_shader_manager.core.manifest import load_game_manifest, new_game_manifest, save_game_manifest
from reshade_shader_manager.core.paths import get_paths
from reshade_shader_manager.core.pcgw import get_pcgw_repos
from reshade_shader_manager.core.repos import merged_catalog
from reshade_shader_manager.core.reshade import check_reshade, install_reshade, remove_reshade_binaries
from reshade_shader_manager.core.targets import DX8_NOT_IMPLEMENTED_MSG, detect_game_arch
from reshade_shader_manager.ui.log_view import LogPanel, setup_gui_logging
from reshade_shader_manager.ui.shader_dialog import ShaderRepoWindow

log = logging.getLogger(__name__)

API_ROWS: list[tuple[str, str]] = [
    ("opengl", "OpenGL"),
    ("dx8", "DirectX 8 (not implemented in v0.1)"),
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
        super().__init__(
            application=application,
            title="ReShade Shader Manager",
            default_width=760,
            default_height=700,
        )
        self._paths = get_paths()
        self._config = load_config(self._paths)
        self._catalog: list[dict[str, str]] | None = None
        self._game_dir: Path | None = None
        self._exe_path: Path | None = None
        self._arch_display = "—"
        self._arch_value = ""

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

    def _build_target_section(self) -> Gtk.Widget:
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_hexpand(True)

        self._game_label = Gtk.Label(label="(not set)", xalign=0.0, hexpand=True)
        self._game_label.set_ellipsize(Pango.EllipsizeMode.END)
        btn_dir = Gtk.Button(label="Game directory…")
        btn_dir.connect("clicked", self._on_pick_game_dir)
        grid.attach(self._game_label, 0, 0, 1, 1)
        grid.attach(btn_dir, 1, 0, 1, 1)

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
        grid.attach(exe_row, 0, 1, 2, 1)

        self._arch_label = Gtk.Label(label="Architecture: —", xalign=0.0)
        grid.attach(self._arch_label, 0, 2, 2, 1)

        return grid

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
        br = Gtk.Button(label="Remove binaries")
        br.connect("clicked", self._on_remove)
        bc = Gtk.Button(label="Check")
        bc.connect("clicked", self._on_check)
        row.append(bi)
        row.append(br)
        row.append(bc)
        grid.attach(row, 0, 3, 2, 1)

        return grid

    def _on_version_changed(self, _entry: Gtk.Entry) -> None:
        self._persist_target_metadata()

    def _build_shader_section(self) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        b_ref = Gtk.Button(label="Refresh catalog")
        b_ref.connect("clicked", self._on_refresh_catalog)
        b_man = Gtk.Button(label="Manage shaders…")
        b_man.add_css_class("suggested-action")
        b_man.connect("clicked", self._on_manage_shaders)
        row.append(b_ref)
        row.append(b_man)
        return row

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
        api = self._api_combo.get_active_id()
        if api == "dx8":
            self._show_error(DX8_NOT_IMPLEMENTED_MSG)
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
                self._show_error(str(e))

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
            self._show_error(str(e))

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

    def _on_refresh_catalog(self, _btn: Gtk.Button) -> None:
        def task():
            pcgw = get_pcgw_repos(
                self._paths,
                ttl_hours=self._config.pcgw_cache_ttl_hours,
                force_refresh=True,
            )
            return merged_catalog(self._paths, pcgw)

        def ok(cat: list) -> None:
            self._catalog = cat
            log.info("Catalog loaded: %d repos (built-in + PCGW + user)", len(cat))

        def err(e: BaseException) -> None:
            self._show_error(f"Catalog refresh failed:\n{e}")

        self._run_worker(task, ok, err)

    def _on_manage_shaders(self, _btn: Gtk.Button) -> None:
        if not self._game_dir:
            self._show_error("Select a game directory.")
            return
        if not self._catalog:
            self._show_error("Click “Refresh catalog” first.")
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
