"""Modal window: merged repo catalog with enable/disable checkboxes."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from gi.repository import GLib, Gtk

from reshade_shader_manager.core.config import AppConfig
from reshade_shader_manager.core.link_farm import disable_shader_repo, enable_shader_repo
from reshade_shader_manager.core.manifest import load_game_manifest, new_game_manifest
from reshade_shader_manager.core.paths import RsmPaths

log = logging.getLogger(__name__)


class ShaderRepoWindow(Gtk.Window):
    """Checklist of repos; Apply runs backend enable/disable on a worker thread."""

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
            title="Shader repositories",
            default_width=520,
            default_height=420,
        )
        self._paths = paths
        self._app_config = app_config
        self._game_dir = game_dir
        self._catalog = catalog
        self._on_done = on_done
        self._checks: dict[str, Gtk.CheckButton] = {}
        self._apply_btn: Gtk.Button | None = None

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_start(12)
        outer.set_margin_end(12)
        outer.set_margin_top(12)
        outer.set_margin_bottom(12)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(list_box)

        m = load_game_manifest(paths, game_dir) or new_game_manifest(game_dir)
        enabled = set(m.enabled_repo_ids)

        for repo in catalog:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(4)
            row.set_margin_bottom(4)
            cb = Gtk.CheckButton()
            cb.set_active(repo["id"] in enabled)
            self._checks[repo["id"]] = cb
            row.append(cb)
            lbl = Gtk.Label(
                label=f"{repo['name']}  ({repo['id']}) — {repo.get('source', '')}",
                xalign=0.0,
                hexpand=True,
                wrap=True,
            )
            row.append(lbl)
            list_box.append(row)

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

        outer.append(scroll)
        outer.append(btn_row)
        self.set_child(outer)

    def _on_apply_clicked(self, _btn: Gtk.Button) -> None:
        apply_b = self._apply_btn
        if apply_b:
            apply_b.set_sensitive(False)

        desired = {rid for rid, cb in self._checks.items() if cb.get_active()}

        def work() -> None:
            m0 = load_game_manifest(self._paths, self._game_dir) or new_game_manifest(
                self._game_dir
            )
            current = set(m0.enabled_repo_ids)
            by_id = {r["id"]: r for r in self._catalog}

            for rid in sorted(current - desired):
                log.info("Disabling repo %s", rid)
                m = load_game_manifest(self._paths, self._game_dir) or new_game_manifest(
                    self._game_dir
                )
                disable_shader_repo(paths=self._paths, manifest=m, repo_id=rid)

            for rid in sorted(desired - current):
                if rid not in by_id:
                    log.warning("Unknown repo id %r — skipped", rid)
                    continue
                url = by_id[rid]["git_url"]
                log.info("Enabling repo %s", rid)
                m = load_game_manifest(self._paths, self._game_dir) or new_game_manifest(
                    self._game_dir
                )
                enable_shader_repo(
                    paths=self._paths,
                    manifest=m,
                    repo_id=rid,
                    git_url=url,
                    pull=self._app_config.shader_download_enabled,
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
                text=f"Shader apply failed:\n{exc}",
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
            except Exception as e:  # noqa: BLE001
                log.exception("Shader apply failed")

                def dispatch_err() -> bool:
                    err(e)
                    return False

                GLib.idle_add(dispatch_err)

        threading.Thread(target=run, daemon=True).start()
