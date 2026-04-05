"""Manage ReShade plugin add-ons (DLL copies in game root; not shader repos)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from gi.repository import Gio, GLib, Gtk

from reshade_shader_manager.core.exceptions import RSMError
from reshade_shader_manager.core.manifest import GameManifest
from reshade_shader_manager.core.plugin_addons_install import (
    apply_plugin_addon_installation,
    filter_catalog_installable_for_arch,
)
from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.ui.catalog_column_view import (
    CatalogRow,
    build_catalog_column_view,
    connect_search_invalidate,
    populate_catalog_store,
)
from reshade_shader_manager.ui.error_format import format_exception_for_ui

log = logging.getLogger(__name__)


class PluginAddonWindow(Gtk.Window):
    """Catalog table with search; Apply copies DLLs into the game folder."""

    def __init__(
        self,
        *,
        parent: Gtk.Window,
        paths: RsmPaths,
        game_dir: Path,
        catalog: list[dict[str, str]],
        sync_manifest: Callable[[], GameManifest],
        on_done: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            transient_for=parent,
            modal=True,
            title="Manage plugin add-ons",
            default_width=800,
            default_height=420,
        )
        self._paths = paths
        self._game_dir = game_dir
        self._catalog = catalog
        self._sync_manifest = sync_manifest
        self._on_done = on_done
        self._enabled_by_id: dict[str, bool] = {}
        self._apply_btn: Gtk.Button | None = None

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_start(12)
        outer.set_margin_end(12)
        outer.set_margin_top(12)
        outer.set_margin_bottom(12)

        hint = Gtk.Label(
            label="Copies add-on DLLs into the game directory (not symlinks). "
            "Only entries with a download URL for your game architecture are listed "
            "(repository-only upstream rows are omitted). "
            "This is not the ReShade installer “addon” variant.",
            xalign=0.0,
            wrap=True,
        )
        outer.append(hint)

        m = sync_manifest()
        enabled = set(m.enabled_plugin_addon_ids)
        arch = m.reshade_arch if m.reshade_arch in ("32", "64") else "64"
        eligible = filter_catalog_installable_for_arch(catalog, arch=arch)

        if not eligible:
            scroll = Gtk.ScrolledWindow()
            scroll.set_vexpand(True)
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroll.set_child(
                Gtk.Label(
                    label="No plugin add-ons are available for this game architecture, "
                    "or none list a download URL that matches it.",
                    xalign=0.0,
                    wrap=True,
                )
            )
            outer.append(scroll)
        else:
            for row in eligible:
                rid = row["id"]
                self._enabled_by_id[rid] = rid in enabled

            search = Gtk.SearchEntry()
            search.set_placeholder_text("Search by name, author, description, source…")
            search.set_hexpand(True)

            store = Gio.ListStore(item_type=CatalogRow)
            populate_catalog_store(store, eligible)

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
        by_id = {r["id"]: r for r in self._catalog}

        def work() -> None:
            m = self._sync_manifest()
            log.info("Applying plugin add-ons for %d id(s)", len(desired))
            apply_plugin_addon_installation(
                paths=self._paths,
                manifest=m,
                game_dir=self._game_dir,
                desired_plugin_addon_ids=desired,
                catalog_by_id=by_id,
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
                text=f"Plugin add-on apply failed:\n{format_exception_for_ui(exc)}",
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
                log.warning("Plugin add-on apply failed: %s", e)

                def dispatch_err() -> bool:
                    err(e)
                    return False

                GLib.idle_add(dispatch_err)
            except Exception as e:  # noqa: BLE001
                log.exception("Plugin add-on apply failed")

                def dispatch_err() -> bool:
                    err(e)
                    return False

                GLib.idle_add(dispatch_err)

        threading.Thread(target=run, daemon=True).start()
