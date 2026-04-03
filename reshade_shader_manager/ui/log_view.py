"""Read-only log panel + logging handler that marshals to the GLib main thread."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gi.repository import GLib, Gtk

if TYPE_CHECKING:
    pass


class LogPanel(Gtk.ScrolledWindow):
    """Bottom panel showing backend log lines."""

    def __init__(self) -> None:
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_min_content_height(160)
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._tv = Gtk.TextView()
        self._tv.set_editable(False)
        self._tv.set_monospace(True)
        self._tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.set_child(self._tv)
        self._buf = self._tv.get_buffer()

    def append(self, line: str) -> None:
        end = self._buf.get_end_iter()
        self._buf.insert(end, line + "\n")
        mark = self._buf.create_mark(None, end, False)
        self._tv.scroll_to_mark(mark, 0.0, False, 0.0, 0.0)
        self._buf.delete_mark(mark)


class GtkLogHandler(logging.Handler):
    """Append log records to a :class:`LogPanel` on the GTK main thread."""

    def __init__(self, panel: LogPanel) -> None:
        super().__init__()
        self._panel = panel

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:  # noqa: BLE001
            msg = f"{record.levelname}: {record.getMessage()}"
        GLib.idle_add(self._panel.append, msg, priority=GLib.PRIORITY_LOW)


def setup_gui_logging(panel: LogPanel, *, level: int = logging.INFO) -> GtkLogHandler:
    root = logging.getLogger()
    handler = GtkLogHandler(panel)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(min(root.level or logging.WARNING, level))
    return handler
