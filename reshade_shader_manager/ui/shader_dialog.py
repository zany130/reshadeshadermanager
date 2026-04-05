"""Modal window: merged repo catalog with enable/disable checkboxes."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from gi.repository import Gio, GLib, Gtk

from reshade_shader_manager.core.config import AppConfig
from reshade_shader_manager.core.exceptions import RSMError
from reshade_shader_manager.core.link_farm import apply_shader_projection
from reshade_shader_manager.core.manifest import load_game_manifest, new_game_manifest
from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.ui.catalog_column_view import (
    CatalogRow,
    build_catalog_column_view,
    connect_search_invalidate,
    populate_catalog_store,
)
from reshade_shader_manager.ui.error_format import format_exception_for_ui

log = logging.getLogger(__name__)


class ShaderRepoWindow(Gtk.Window):
    """Catalog table with search; Apply runs backend enable/disable on a worker thread."""

    def __init__(
        self,
        *,
        parent: Gtk.Window,
        paths: RsmPaths,
        app_config: AppConfig,
        game_dir: Path,
        catalog: list[dict[str, str]],
        on_done: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            transient_for=parent,
            modal=True,
            title="Manage shaders",
            default_width=800,
            default_height=420,
        )
        self._paths = paths
        self._app_config = app_config
        self._game_dir = game_dir
        self._catalog = catalog
        self._on_done = on_done
        self._enabled_by_id: dict[str, bool] = {}
        self._apply_btn: Gtk.Button | None = None

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_start(12)
        outer.set_margin_end(12)
        outer.set_margin_top(12)
        outer.set_margin_bottom(12)

        m = load_game_manifest(paths, game_dir) or new_game_manifest(game_dir)
        enabled = set(m.enabled_repo_ids)

        for repo in catalog:
            rid = repo["id"]
            self._enabled_by_id[rid] = rid in enabled

        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search by name, author, description, source…")
        search.set_hexpand(True)

        store = Gio.ListStore(item_type=CatalogRow)
        populate_catalog_store(store, catalog)

        scroll, custom_filter = build_catalog_column_view(
            store,
            self._enabled_by_id,
            lambda: search.get_text(),
        )
        connect_search_invalidate(search, custom_filter)

        outer.append(search)
        outer.append(scroll)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        apply_b = Gtk.Button(label="Apply")
        self._apply_btn = apply_b
        apply_b.add_css_class("suggested-action")
        apply_b.connect("clicked", self._on_apply_clicked)
        btn_row.append(cancel)
        btn_row.append(apply_b)

        outer.append(btn_row)
        self.set_child(outer)

    def _on_apply_clicked(self, _btn: Gtk.Button) -> None:
        apply_b = self._apply_btn
        if apply_b:
            apply_b.set_sensitive(False)

        desired = {rid for rid, on in self._enabled_by_id.items() if on}

        def work() -> None:
            by_id = {r["id"]: r for r in self._catalog}
            log.info(
                "Applying shader projection for %d repo(s) (full rebuild; no git pull)",
                len(desired),
            )
            apply_shader_projection(
                paths=self._paths,
                game_dir=self._game_dir,
                desired_repo_ids=desired,
                catalog_by_id=by_id,
                git_pull=False,
            )

        def ok(_: object = None) -> None:
            if self._apply_btn:
                self._apply_btn.set_sensitive(True)
            if self._on_done:
                self._on_done()
            self.close()

        def err(exc: BaseException) -> None:
            if self._apply_btn:
                self._apply_btn.set_sensitive(True)
            md = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=f"Shader apply failed:\n{format_exception_for_ui(exc)}",
            )
            md.present()
            md.connect("response", lambda w, *_: w.destroy())

        def run() -> None:
            try:
                work()

                def dispatch_ok() -> bool:
                    ok()
                    return False

                GLib.idle_add(dispatch_ok)
            except RSMError as e:
                log.warning("Shader apply failed: %s", e)

                def dispatch_err() -> bool:
                    err(e)
                    return False

                GLib.idle_add(dispatch_err)
            except Exception as e:  # noqa: BLE001
                log.exception("Shader apply failed")

                def dispatch_err() -> bool:
                    err(e)
                    return False

                GLib.idle_add(dispatch_err)

        threading.Thread(target=run, daemon=True).start()
