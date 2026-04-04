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
            default_height=560,
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

        self._mode_combo = Gtk.ComboBoxText()
        self._mode_combo.append("artifact", "Artifact (download URLs)")
        self._mode_combo.append("repo", "Repository (git clone)")
        self._mode_combo.set_active_id("artifact")
        self._mode_combo.set_tooltip_text(
            "Artifact: download a ZIP or raw DLL by URL. Repository: one global git clone; RSM copies "
            "paths from that clone into the game (same idea as shader repos)."
        )
        row(3, "Install mode", self._mode_combo)

        self._stack = Gtk.Stack()
        self._stack.set_hexpand(True)

        artifact_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        artifact_grid.set_hexpand(True)

        def arow(r: int, label: str, widget: Gtk.Widget) -> None:
            artifact_grid.attach(Gtk.Label(label=label, xalign=1.0), 0, r, 1, 1)
            artifact_grid.attach(widget, 1, r, 1, 1)

        self._u32_entry = Gtk.Entry()
        self._u32_entry.set_hexpand(True)
        self._u32_entry.set_placeholder_text("https://… (optional)")
        arow(0, "Download URL (32-bit)", self._u32_entry)

        self._u64_entry = Gtk.Entry()
        self._u64_entry.set_hexpand(True)
        self._u64_entry.set_placeholder_text("https://… (optional)")
        arow(1, "Download URL (64-bit)", self._u64_entry)

        self._u1_entry = Gtk.Entry()
        self._u1_entry.set_hexpand(True)
        self._u1_entry.set_placeholder_text("https://… (optional)")
        self._u1_entry.set_tooltip_text(
            "Single URL used when no arch-specific URL applies, or as fallback for the chosen arch."
        )
        arow(2, "Download URL (single)", self._u1_entry)

        self._repo_artifact_entry = Gtk.Entry()
        self._repo_artifact_entry.set_hexpand(True)
        self._repo_artifact_entry.set_placeholder_text("(optional)")
        self._repo_artifact_entry.set_tooltip_text("Optional project URL (metadata only for artifact mode).")
        arow(3, "Repository URL", self._repo_artifact_entry)

        self._stack.add_named(artifact_grid, "artifact")

        repo_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        repo_grid.set_hexpand(True)

        def rrow(r: int, label: str, widget: Gtk.Widget) -> None:
            repo_grid.attach(Gtk.Label(label=label, xalign=1.0), 0, r, 1, 1)
            repo_grid.attach(widget, 1, r, 1, 1)

        self._repo_url_entry = Gtk.Entry()
        self._repo_url_entry.set_hexpand(True)
        self._repo_url_entry.set_placeholder_text("https://github.com/org/project.git")
        rrow(0, "Git repository URL", self._repo_url_entry)

        self._dll32_entry = Gtk.Entry()
        self._dll32_entry.set_hexpand(True)
        self._dll32_entry.set_placeholder_text("e.g. build/Release/foo.addon32")
        self._dll32_entry.set_tooltip_text("Path to the 32-bit add-on DLL, relative to the repository root.")
        rrow(1, "DLL path (32-bit)", self._dll32_entry)

        self._dll64_entry = Gtk.Entry()
        self._dll64_entry.set_hexpand(True)
        self._dll64_entry.set_placeholder_text("e.g. build/Release/foo.addon64")
        self._dll64_entry.set_tooltip_text("Path to the 64-bit add-on DLL, relative to the repository root.")
        rrow(2, "DLL path (64-bit)", self._dll64_entry)

        self._shader_root_entry = Gtk.Entry()
        self._shader_root_entry.set_hexpand(True)
        self._shader_root_entry.set_placeholder_text("(optional) e.g. Shaders")
        self._shader_root_entry.set_tooltip_text(
            "Optional directory under the repo whose files are symlinked as companion shaders (skips .git)."
        )
        rrow(3, "Shader root (optional)", self._shader_root_entry)

        self._companion_paths_entry = Gtk.Entry()
        self._companion_paths_entry.set_hexpand(True)
        self._companion_paths_entry.set_placeholder_text("(optional) comma-separated or JSON array")
        self._companion_paths_entry.set_tooltip_text(
            "Extra companion shader paths relative to repo root (comma-separated or JSON array of strings)."
        )
        rrow(4, "Companion shader paths (optional)", self._companion_paths_entry)

        self._stack.add_named(repo_grid, "repo")

        grid.attach(self._stack, 0, 4, 2, 1)

        self._artifact_hint = (
            "Artifact mode: provide at least one download URL. RSM copies the add-on DLL into the game "
            "folder; companion shaders inside ZIPs are symlinked under reshade-shaders/…/addons/."
        )
        self._repo_hint = (
            "Repository mode: RSM keeps one clone under your RSM data directory. Use Update local clones "
            "to git pull. Apply copies the DLL paths into the game and optionally symlinks companion shaders."
        )
        self._hint = Gtk.Label(label=self._artifact_hint, xalign=0.0, wrap=True)
        self._hint.add_css_class("dim-label")

        self._mode_combo.connect("changed", self._on_install_mode_changed)
        self._on_install_mode_changed(self._mode_combo)

        outer.append(grid)
        outer.append(self._hint)

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

    def _on_install_mode_changed(self, combo: Gtk.ComboBoxText) -> None:
        mid = combo.get_active_id()
        name = mid if mid in ("artifact", "repo") else "artifact"
        self._stack.set_visible_child_name(name)
        self._hint.set_label(self._repo_hint if name == "repo" else self._artifact_hint)

    def _on_save_clicked(self, _btn: Gtk.Button) -> None:
        rid = self._id_entry.get_text().strip().lower()
        name = self._name_entry.get_text().strip()
        desc = self._desc_entry.get_text().strip()
        mode = self._mode_combo.get_active_id() or "artifact"
        if not rid:
            self._show_error("Add-on name is required.")
            return
        if not name:
            name = rid

        if mode == "repo":
            repo_url = self._repo_url_entry.get_text().strip()
            dll32 = self._dll32_entry.get_text().strip()
            dll64 = self._dll64_entry.get_text().strip()
            shader_root = self._shader_root_entry.get_text().strip()
            companions = self._companion_paths_entry.get_text().strip()
            row = {
                "id": rid,
                "name": name,
                "description": desc,
                "download_url_32": "",
                "download_url_64": "",
                "download_url": "",
                "repository_url": repo_url,
                "effect_install_path": "",
                "upstream_section": "",
                "source": "user",
                "install_mode": "repo",
                "dll_32_path": dll32,
                "dll_64_path": dll64,
                "shader_root": shader_root,
                "companion_shader_paths": companions,
            }
        else:
            u32 = self._u32_entry.get_text().strip()
            u64 = self._u64_entry.get_text().strip()
            u1 = self._u1_entry.get_text().strip()
            repo = self._repo_artifact_entry.get_text().strip()
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
                "install_mode": "artifact",
                "dll_32_path": "",
                "dll_64_path": "",
                "shader_root": "",
                "companion_shader_paths": "",
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
