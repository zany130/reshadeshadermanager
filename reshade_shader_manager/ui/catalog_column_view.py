"""Gtk.ColumnView + FilterListModel helpers for catalog dialogs (GTK 4)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gi.repository import Gio, GObject, Gtk, Pango

from reshade_shader_manager.ui.catalog_search import catalog_entry_matches


class CatalogRow(GObject.Object):
    """One row in the merged catalog list store (display + filter fields)."""

    __gtype_name__ = "RsmCatalogRow"

    repo_id = GObject.Property(type=str, default="")
    name = GObject.Property(type=str, default="")
    author = GObject.Property(type=str, default="")
    description = GObject.Property(type=str, default="")
    source = GObject.Property(type=str, default="")


def sort_catalog_by_name(catalog: list[dict[str, str]]) -> list[dict[str, str]]:
    """Stable sort by display name (case-insensitive), then id."""

    def key(d: dict[str, str]) -> tuple[str, str]:
        name = (d.get("name") or d.get("id") or "").casefold()
        rid = (d.get("id") or "").casefold()
        return (name, rid)

    return sorted(catalog, key=key)


def populate_catalog_store(store: Gio.ListStore, catalog: list[dict[str, str]]) -> None:
    """Append ``CatalogRow`` items for each catalog entry (sorted by name)."""
    for d in sort_catalog_by_name(catalog):
        rid = d["id"]
        store.append(
            CatalogRow(
                repo_id=rid,
                name=d.get("name", "") or rid,
                author=d.get("author", ""),
                description=d.get("description", ""),
                source=d.get("source", ""),
            )
        )


def _row_match_dict(row: CatalogRow) -> dict[str, str]:
    return {
        "name": row.props.name,
        "author": row.props.author,
        "description": row.props.description,
        "source": row.props.source,
    }


def _invalidate_filter(custom_filter: Gtk.CustomFilter) -> None:
    custom_filter.changed(Gtk.FilterChange.DIFFERENT)


def build_catalog_column_view(
    store: Gio.ListStore,
    enabled_by_id: dict[str, bool],
    get_query: Callable[[], str],
) -> tuple[Gtk.ScrolledWindow, Gtk.CustomFilter]:
    """
    Build a scrolled ``Gtk.ColumnView`` over ``store`` with a search filter.

    Enable/disable state is read and written via ``enabled_by_id`` (stable ids).
    Connect :func:`connect_search_invalidate` to the search entry so typing
    updates the filter.
    """

    def match_func(item: GObject.Object, _user_data: Any) -> bool:
        row = item
        if not isinstance(row, CatalogRow):
            return True
        return catalog_entry_matches(get_query(), _row_match_dict(row))

    custom_filter = Gtk.CustomFilter.new(match_func, None)
    filter_model = Gtk.FilterListModel.new(store, custom_filter)
    selection = Gtk.NoSelection.new(filter_model)

    column_view = Gtk.ColumnView(model=selection)
    column_view.set_vexpand(True)

    # --- Enable column
    cb_factory = Gtk.SignalListItemFactory()

    def cb_setup(_f: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        list_item.set_child(Gtk.CheckButton())

    def cb_bind(_f: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        cb = list_item.get_child()
        if not isinstance(cb, Gtk.CheckButton):
            return
        row = list_item.get_item()
        if not isinstance(row, CatalogRow):
            return
        rid = row.props.repo_id

        def toggled(b: Gtk.CheckButton) -> None:
            enabled_by_id[rid] = b.get_active()

        hid = cb.connect("toggled", toggled)
        setattr(list_item, "_rsm_toggle_hid", hid)
        cb.handler_block(hid)
        cb.set_active(enabled_by_id.get(rid, False))
        cb.handler_unblock(hid)

    def cb_unbind(_f: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        cb = list_item.get_child()
        if isinstance(cb, Gtk.CheckButton):
            hid = getattr(list_item, "_rsm_toggle_hid", None)
            if hid is not None:
                cb.disconnect(hid)
        setattr(list_item, "_rsm_toggle_hid", None)

    cb_factory.connect("setup", cb_setup)
    cb_factory.connect("bind", cb_bind)
    cb_factory.connect("unbind", cb_unbind)

    col_enable = Gtk.ColumnViewColumn(title="", factory=cb_factory)
    col_enable.set_fixed_width(48)
    col_enable.set_resizable(False)
    column_view.append_column(col_enable)

    # --- Text columns
    def add_text_column(title: str, attr: str) -> None:
        factory = Gtk.SignalListItemFactory()

        def setup(_f: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
            label = Gtk.Label(xalign=0.0, hexpand=True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_single_line_mode(True)
            list_item.set_child(label)

        def bind(_f: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
            label = list_item.get_child()
            if not isinstance(label, Gtk.Label):
                return
            row = list_item.get_item()
            if not isinstance(row, CatalogRow):
                return
            text = row.get_property(attr) or ""
            label.set_label(text)
            if attr == "name":
                tip = f"{row.props.repo_id}\n{text}" if text else row.props.repo_id
                label.set_tooltip_text(tip)
            else:
                label.set_tooltip_text(text or None)

        def unbind(_f: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
            label = list_item.get_child()
            if isinstance(label, Gtk.Label):
                label.set_tooltip_text(None)

        factory.connect("setup", setup)
        factory.connect("bind", bind)
        factory.connect("unbind", unbind)
        col = Gtk.ColumnViewColumn(title=title, factory=factory)
        col.set_resizable(True)
        column_view.append_column(col)

    add_text_column("Name", "name")
    add_text_column("Author", "author")
    add_text_column("Description", "description")
    add_text_column("Source", "source")

    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.set_child(column_view)

    return scroll, custom_filter


def connect_search_invalidate(search: Gtk.SearchEntry, custom_filter: Gtk.CustomFilter) -> None:
    """Re-run filtering when the search text changes."""

    def _on_changed(_entry: Gtk.SearchEntry) -> None:
        _invalidate_filter(custom_filter)

    search.connect("search-changed", _on_changed)
