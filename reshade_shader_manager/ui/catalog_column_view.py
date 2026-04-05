"""Gtk.ColumnView + SortListModel + FilterListModel helpers for catalog dialogs (GTK 4)."""

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


def _string_sorter_for_property(prop: str) -> Gtk.StringSorter:
    """Case-insensitive string sort on a ``CatalogRow`` property."""
    expr = Gtk.PropertyExpression.new(CatalogRow.__gtype__, None, prop)
    sorter = Gtk.StringSorter.new(expr)
    sorter.set_ignore_case(True)
    return sorter


def populate_catalog_store(store: Gio.ListStore, catalog: list[dict[str, str]]) -> None:
    """Append ``CatalogRow`` items in stable ``id`` order (``Gtk.SortListModel`` owns display order)."""
    for d in sorted(catalog, key=lambda x: x["id"].casefold()):
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
    Build a scrolled ``Gtk.ColumnView`` over ``store`` with sort + search filter.

    Sorting uses ``Gtk.SortListModel`` driven by ``Gtk.ColumnView.get_sorter()`` so
    header clicks update order; filtering uses ``Gtk.FilterListModel`` on top of that.
    Enable/disable state is read and written via ``enabled_by_id`` (stable ids).

    **Enabled column sort:** ascending puts **unchecked** rows first; descending
    puts **checked** rows first.

    Connect :func:`connect_search_invalidate` to the search entry so typing
    updates the filter.
    """

    def match_func(item: GObject.Object, _user_data: Any) -> bool:
        row = item
        if not isinstance(row, CatalogRow):
            return True
        return catalog_entry_matches(get_query(), _row_match_dict(row))

    custom_filter = Gtk.CustomFilter.new(match_func, None)

    # Ascending: disabled (False) before enabled (True); descending reverses.
    def cmp_enabled(o1: GObject.Object, o2: GObject.Object, _ud: Any = None) -> Gtk.Ordering:
        if not isinstance(o1, CatalogRow) or not isinstance(o2, CatalogRow):
            return Gtk.Ordering.EQUAL
        e1 = enabled_by_id.get(o1.props.repo_id, False)
        e2 = enabled_by_id.get(o2.props.repo_id, False)
        if e1 == e2:
            return Gtk.Ordering.EQUAL
        if not e1 and e2:
            return Gtk.Ordering.SMALLER
        return Gtk.Ordering.LARGER

    enabled_sorter = Gtk.CustomSorter.new(cmp_enabled)

    column_view = Gtk.ColumnView()
    column_view.set_vexpand(True)

    # --- Enabled column
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
            enabled_sorter.changed(Gtk.SorterChange.DIFFERENT)

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

    col_enable = Gtk.ColumnViewColumn(title="Enabled", factory=cb_factory)
    col_enable.set_sorter(enabled_sorter)
    col_enable.set_fixed_width(88)
    col_enable.set_resizable(True)
    column_view.append_column(col_enable)

    # --- Text columns (Name column reference needed for default sort)
    def add_text_column(title: str, attr: str) -> Gtk.ColumnViewColumn:
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
        col.set_sorter(_string_sorter_for_property(attr))
        col.set_resizable(True)
        column_view.append_column(col)
        return col

    col_name = add_text_column("Name", "name")
    add_text_column("Author", "author")
    add_text_column("Description", "description")
    add_text_column("Source", "source")

    # SortListModel must use the view's sorter so header clicks affect row order (GTK docs).
    sort_model = Gtk.SortListModel.new(store, column_view.get_sorter())
    filter_model = Gtk.FilterListModel.new(sort_model, custom_filter)
    selection = Gtk.NoSelection.new(filter_model)
    column_view.set_model(selection)
    column_view.sort_by_column(col_name, Gtk.SortType.ASCENDING)

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
