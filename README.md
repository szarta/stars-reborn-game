# Stars Reborn

Stars Reborn is a faithful open-source clone of [Stars!](https://en.wikipedia.org/wiki/Stars!),
the classic 4X (explore, expand, exploit, exterminate) turn-based space strategy game developed
by Jeff Johnson and Jeff McBride (1995–1996). This project is not endorsed by the original
authors or publishers in any way.

## Project Tenets

1. **Open game** — freely distributable, modifiable, and playable across platforms.
2. **Faithful reproduction** — all original mechanics reverse-engineered and implemented. A veteran
   Stars! player should feel immediately at home.
3. **Respectful enhancement** — a *Legacy* mode preserves original behavior exactly; optional fixes
   address known bugs and micromanagement pain points.
4. **Stand on the shoulders of giants** — acknowledge prior clone efforts, community research, and
   every contributor who helps reach the finish line.

---

## Repository Architecture

Stars Reborn is split across multiple focused repositories. **This repo (`stars-reborn-game`) is
the primary release and issue-tracking repository.** It packages the component repos into
distributable game images and is where bugs and feature requests should be filed.

| Repository | Purpose |
|------------|---------|
| `stars-reborn-game` *(this repo)* | Primary release repo — packaging, releases, issue tracker |
| [`stars-reborn-engine`](https://github.com/szarta/stars-reborn-engine) | Rust game engine — HTTP API, turn processing, authoritative data model |
| [`stars-reborn-ui`](https://github.com/szarta/stars-reborn-ui) | Python/PySide6 game client — rendering, player input, local game management |
| [`stars-reborn-schemas`](https://github.com/szarta/stars-reborn-schemas) | JSON schemas defining the engine/UI HTTP contract |
| [`stars-reborn-design`](https://github.com/szarta/stars-reborn-design) | Game mechanics documentation, research notes, open questions |

### Component Architecture

Stars Reborn is a **client/server game**. The engine and UI are fully decoupled services that
communicate exclusively over HTTP:

```
┌──────────────────────────────┐        HTTP        ┌──────────────────────────────┐
│      Game Client (UI)        │ ◄────────────────► │    Game Engine (Rust)        │
│  Python / PySide6            │                    │                              │
│  - Renders universe state    │                    │  - Universe generation       │
│  - Collects player orders    │                    │  - Turn processing           │
│  - Submits orders to engine  │                    │  - Victory detection         │
│  - Displays turn results     │                    │  - Authoritative data model  │
└──────────────────────────────┘                    └──────────────────────────────┘
```

### Submodules

This repo pins specific versions of each component via git submodules:

```
engine/   →  stars-reborn-engine  (Rust)
ui/       →  stars-reborn-ui      (Python/PySide6)
schemas/  →  stars-reborn-schemas (JSON)
design/   →  stars-reborn-design  (docs)
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Rust toolchain (`rustup` recommended)
- PySide6 (installed automatically via pip)

### Clone

```bash
git clone --recurse-submodules git@github.com:szarta/stars-reborn-game.git
cd stars-reborn-game
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

### Run from Source

Build the engine and install UI dependencies, then launch:

```bash
cd engine && cargo build --release && cd ..
pip install -r ui/requirements.txt
python -m stars_reborn
```

---

## Building the AppImage (Linux)

The AppImage bundles the engine binary and the Python UI into a single self-contained executable.
Build tasks are managed with [invoke](https://www.pyinvoke.org/).

### Additional Prerequisites

- `appimage-builder` 1.1+ — [installation guide](https://appimage-builder.readthedocs.io/en/latest/intro/install.html)

### Install Build Dependencies

```bash
pip install -r requirements.txt
```

### Build

```bash
invoke build
```

This runs three steps in order:

| Step | Command | What it does |
|------|---------|--------------|
| 1 | `invoke build-engine` | `cargo build --release` in `engine/` |
| 2 | `invoke build-appdir` | Assembles `build/AppDir/` — Python venv, UI source, engine binary, launcher |
| 3 | `invoke build-appimage` | Writes `build/AppImageBuilder.yml` and runs `appimage-builder` |

The finished image is written to `build/Stars_Reborn-<version>-x86_64.AppImage`.

### Individual Steps

```bash
invoke build-engine     # compile stars-server only
invoke build-appdir     # assemble AppDir only (requires built engine)
invoke build-appimage   # produce AppImage only (requires assembled AppDir)
invoke clean            # remove build/
```

### Known Build Issues

#### `packaging.version.InvalidVersion` during apt deploy

**Affects:** `appimage-builder` 1.1.0 with `packaging` 22.0+

`appimage-builder` uses the `packaging` library to compare apt package version strings.
Ubuntu-style versions (e.g. `1.21.1ubuntu2`) are not valid PEP 440, but older versions of
`packaging` accepted them via a `LegacyVersion` fallback that was removed in `packaging` 22.0.
On any modern Python environment this causes a crash during the apt deploy step:

```
packaging.version.InvalidVersion: Invalid version: '1.21.1ubuntu2'
```

**Fix:** patch `appimage-builder`'s `package.py` to fall back to string comparison on invalid
versions. Find the file in your environment:

```bash
python -c "import appimagebuilder.modules.deploy.apt.package as m; print(m.__file__)"
```

Edit the `__gt__` method:

```python
def __gt__(self, other):
    if isinstance(other, Package):
        try:
            return version.parse(self.version) > version.parse(other.version)
        except version.InvalidVersion:
            return self.version > other.version
```

This issue has been reported upstream. If you are on `packaging` < 22 you will not encounter it.

---

## Releases

Pre-built releases are available on the [Releases](https://github.com/szarta/stars-reborn-game/releases) page:

- **Linux** — AppImage (no installation required)
- **Windows** — `.exe` installer

---

## Reporting Bugs & Requesting Features

Please file issues in **this repository** (`stars-reborn-game`), regardless of which component
is affected. Use the issue templates to provide reproduction steps, expected vs. actual behavior,
and your platform/version information.

---

## Useful Links

- [Stars! Wikipedia article](https://en.wikipedia.org/wiki/Stars!)
- [Stars! community wiki](http://wiki.starsautohost.org/wiki/Main_Page)
- [Stars! strategy guide](http://stars.arglos.net/articles/ssg/ssg.htm)
- [Stars! community forum](http://starsautohost.org/sahforum2/)

---

## Credits

Stars! was created by **Jeff Johnson and Jeff McBride** and published by Empire Interactive
Entertainment (1996). This project is not endorsed by the original authors or publishers.

For full credits, community research acknowledgements, prior clone attributions, and asset
licenses, see [`design/docs/credits.rst`](design/docs/credits.rst).

## License

See [LICENSE.txt](LICENSE.txt).
