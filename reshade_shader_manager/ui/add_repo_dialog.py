"""Dialog to append a user shader repo to ``repos.json``."""

from __future__ import annotations

import logging
from typing import Callable

from gi.repository import Gtk

from reshade_shader_manager.core.paths import RsmPaths
from reshade_shader_manager.core.repos import add_user_repo

log = logging.getLogger(__name__)


class AddRepoDialog(Gtk.Window):
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
            title="Add shader repository",
            default_width=440,
            default_height=360,
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
        self._id_entry.set_placeholder_text("e.g. my-shaders (lowercase id)")
        row(0, "ID", self._id_entry)

        self._name_entry = Gtk.Entry()
        self._name_entry.set_placeholder_text("Display name")
        row(1, "Name", self._name_entry)

        self._url_entry = Gtk.Entry()
        self._url_entry.set_hexpand(True)
        self._url_entry.set_placeholder_text("https://github.com/user/repo.git")
        row(2, "Git URL", self._url_entry)

        self._author_entry = Gtk.Entry()
        self._author_entry.set_placeholder_text("(optional)")
        row(3, "Author", self._author_entry)

        self._desc_entry = Gtk.Entry()
        self._desc_entry.set_placeholder_text("(optional)")
        row(4, "Description", self._desc_entry)

        outer.append(grid)

        hint = Gtk.Label(
            label="ID must be unique among built-in and user repos. "
            "If the same ID exists in the PCGW cache, your entry overrides it in the catalog.",
            xalign=0.0,
            wrap=True,
        )
        hint.add_css_class("dim-label")
        outer.append(hint)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        save = Gtk.Button(label="Add")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_add_clicked)
        btn_row.append(cancel)
        btn_row.append(save)
        outer.append(btn_row)

        self.set_child(outer)

    def _on_add_clicked(self, _btn: Gtk.Button) -> None:
        rid = self._id_entry.get_text().strip().lower()
        name = self._name_entry.get_text().strip()
        url = self._url_entry.get_text().strip()
        author = self._author_entry.get_text().strip()
        desc = self._desc_entry.get_text().strip()
        if not rid:
            self._show_error("Repository ID is required.")
            return
        if not name:
            name = rid
        if not url:
            self._show_error("Git URL is required.")
            return
        try:
            add_user_repo(
                self._paths,
                repo_id=rid,
                name=name,
                git_url=url,
                author=author,
                description=desc,
            )
        except ValueError as e:
            self._show_error(str(e))
            return
        log.info("Added user repo %s", rid)
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
