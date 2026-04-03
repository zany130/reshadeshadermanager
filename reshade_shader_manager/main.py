"""GTK application entry (requires PyGObject + GTK 4)."""

from __future__ import annotations


def main() -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")

    from gi.repository import Gio, Gtk

    from reshade_shader_manager.ui.main_window import MainWindow

    def on_activate(app: Gtk.Application) -> None:
        win = MainWindow(app)
        win.present()

    app = Gtk.Application(
        application_id="io.github.rsm.reshade_shader_manager",
        flags=Gio.ApplicationFlags.FLAGS_NONE,
    )
    app.connect("activate", on_activate)
    return int(app.run(None))


if __name__ == "__main__":
    raise SystemExit(main())
