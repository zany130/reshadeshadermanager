"""Dialog to add or replace a user plugin add-on in ``plugin_addons.json``."""

from __future__ import annotations

import logging
from typing import Callable

from gi.repository import Gtk

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.plugin_addons_user import upsert_user_plugin_addon

log = logging.getLogger(__name__)


class AddPluginAddonDialog(Gtk.Window):
    def __init__(
        self,
        *,
        parent: Gtk.Window,
        paths: RsmPaths,
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            transient_for=parent,
            modal=True,
            title="Add plugin add-on",
            default_width=520,
            default_height=460,
        )
        self._paths = paths
        self._on_saved = on_saved

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_start(14)
        outer.set_margin_end(14)
        outer.set_margin_top(14)
        outer.set_margin_bottom(14)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_hexpand(True)

        def row(r: int, label: str, widget: Gtk.Widget) -> None:
            grid.attach(Gtk.Label(label=label, xalign=1.0), 0, r, 1, 1)
            grid.attach(widget, 1, r, 1, 1)

        self._id_entry = Gtk.Entry()
        self._id_entry.set_placeholder_text("e.g. my-addon")
        self._id_entry.set_tooltip_text(
            "Short catalog name for this add-on (lowercase letters, digits, dashes, underscores). "
            "If this name already exists in your plugin_addons.json, the saved entry is replaced. "
            "A user entry with the same name as an upstream Addons.ini row overrides the upstream row."
        )
        row(0, "Add-on name", self._id_entry)

        self._name_entry = Gtk.Entry()
        self._name_entry.set_placeholder_text("e.g. My custom add-on")
        self._name_entry.set_tooltip_text("Optional label shown in the Manage plugin add-ons list.")
        row(1, "Friendly name", self._name_entry)

        self._desc_entry = Gtk.Entry()
        self._desc_entry.set_placeholder_text("(optional)")
        row(2, "Description", self._desc_entry)

        self._u32_entry = Gtk.Entry()
        self._u32_entry.set_hexpand(True)
        self._u32_entry.set_placeholder_text("https://… (optional)")
        row(3, "Download URL (32-bit)", self._u32_entry)

        self._u64_entry = Gtk.Entry()
        self._u64_entry.set_hexpand(True)
        self._u64_entry.set_placeholder_text("https://… (optional)")
        row(4, "Download URL (64-bit)", self._u64_entry)

        self._u1_entry = Gtk.Entry()
        self._u1_entry.set_hexpand(True)
        self._u1_entry.set_placeholder_text("https://… (optional)")
        self._u1_entry.set_tooltip_text(
            "Single URL used when no arch-specific URL applies, or as fallback for the chosen arch."
        )
        row(5, "Download URL (single)", self._u1_entry)

        self._repo_entry = Gtk.Entry()
        self._repo_entry.set_hexpand(True)
        self._repo_entry.set_placeholder_text("(optional)")
        row(6, "Repository URL", self._repo_entry)

        outer.append(grid)

        hint = Gtk.Label(
            label=(
                "At least one download URL is required. RSM copies the downloaded add-on DLL into "
                "the game folder; companion shaders inside ZIPs are symlinked under reshade-shaders/…/addons/."
            ),
            xalign=0.0,
            wrap=True,
        )
        hint.add_css_class("dim-label")
        outer.append(hint)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save_clicked)
        btn_row.append(cancel)
        btn_row.append(save)
        outer.append(btn_row)

        self.set_child(outer)

    def _on_save_clicked(self, _btn: Gtk.Button) -> None:
        rid = self._id_entry.get_text().strip().lower()
        name = self._name_entry.get_text().strip()
        desc = self._desc_entry.get_text().strip()
        u32 = self._u32_entry.get_text().strip()
        u64 = self._u64_entry.get_text().strip()
        u1 = self._u1_entry.get_text().strip()
        repo = self._repo_entry.get_text().strip()
        if not rid:
            self._show_error("Add-on name is required.")
            return
        if not name:
            name = rid
        row = {
            "id": rid,
            "name": name,
            "description": desc,
            "download_url_32": u32,
            "download_url_64": u64,
            "download_url": u1,
            "repository_url": repo,
            "effect_install_path": "",
            "upstream_section": "",
            "source": "user",
        }
        try:
            upsert_user_plugin_addon(self._paths, row)
        except ValueError as e:
            self._show_error(str(e))
            return
        log.info("Saved user plugin add-on %s", rid)
        if self._on_saved:
            self._on_saved()
        self.close()

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
