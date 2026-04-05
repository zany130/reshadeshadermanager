# Manual QA checklist (release / RC)

Run after `python3 -m pytest tests/` is green. Use before tagging a release candidate or stable tag.

| Area | Verify |
|------|--------|
| ReShade install / remove / check | GUI: install, **Check** OK, **Remove** binaries only; CLI: `rsm reshade install`, `check`, `remove` |
| DX8 flow | Select **dx8**; install/check and d3d8to9 + proxy behavior as expected |
| Shaders apply | GUI **Manage shaders…** → **Apply**; CLI `rsm shaders apply --game-dir … --repo …` |
| Shaders + `--git-pull`** | CLI `rsm shaders apply … --git-pull` |
| Add-ons apply | GUI **Manage plugin add-ons…**; CLI `rsm addons apply …` |
| Recent games | List, row activation, missing-folder error |
| Shader / add-on tables | Search, column sort, **Enabled** while filtered |
| AppImage | Build or CI artifact launches; basic window/desktop sanity |
| Key CLI | `rsm --help`, `catalog refresh`, `shaders update-clones`, `addons refresh-catalog`, `game inspect` |

Record failures in the issue tracker or release notes.
