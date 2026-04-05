"""Read-only log panel + logging handler that marshals to the GLib main thread."""

from __future__ import annotations

import logging

from gi.repository import GLib, Gtk

from reshade_shader_manager.core.paths import RsmPaths


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


def attach_file_logging(paths: RsmPaths, *, level: int = logging.INFO) -> logging.Handler | None:
    """
    Write session logs to ``paths.logs_dir() / rsm.log`` (UTF-8).

    Idempotent: skips if the root logger already has a :class:`logging.FileHandler`
    for that path. On ``OSError``, logs a warning and returns ``None``.
    """
    root = logging.getLogger()
    log_path = paths.logs_dir() / "rsm.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        resolved = str(log_path.resolve())
    except OSError as e:
        logging.getLogger(__name__).warning("Could not create logs directory %s: %s", log_path.parent, e)
        return None

    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == resolved:
            return None

    try:
        fh = logging.FileHandler(log_path, encoding="utf-8")
    except OSError as e:
        logging.getLogger(__name__).warning("Could not open log file %s: %s", log_path, e)
        return None

    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    root.setLevel(min(root.level or logging.WARNING, level))
    return fh


def setup_gui_logging(
    panel: LogPanel,
    *,
    paths: RsmPaths | None = None,
    level: int = logging.INFO,
) -> GtkLogHandler:
    if paths is not None:
        attach_file_logging(paths, level=level)
    root = logging.getLogger()
    handler = GtkLogHandler(panel)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(min(root.level or logging.WARNING, level))
    return handler
