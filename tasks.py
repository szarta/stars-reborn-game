"""
tasks.py — build automation for Stars Reborn (invoke)

Usage:
    invoke build             # full AppImage build (engine + AppDir + image)
    invoke build-engine      # compile stars-server only
    invoke build-appdir      # assemble AppDir only (requires built engine)
    invoke build-appimage    # run appimage-builder only (requires AppDir)
    invoke clean             # remove build artefacts
"""

import os
import sys
from pathlib import Path

from invoke import task

# ---------------------------------------------------------------------------
# Paths (all relative to this file, i.e. stars-reborn-game/)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent
ENGINE_DIR = ROOT / "engine"
UI_DIR = ROOT / "ui"
BUILD_DIR = ROOT / "build"
APPDIR = BUILD_DIR / "AppDir"
RECIPE = BUILD_DIR / "AppImageBuilder.yml"

ENGINE_BIN_SRC = ENGINE_DIR / "target" / "release" / "stars-server"
ENGINE_BIN_DEST = APPDIR / "usr" / "bin" / "stars-server"

UI_PYTHON = APPDIR / "usr" / "lib" / "stars-reborn" / "venv"
UI_SITE_PACKAGES = None  # resolved at runtime after venv creation

ICON_SRC = UI_DIR / "assets" / "png" / "entry.png"
ICON_DEST = APPDIR / "stars-reborn.png"

APP_ID = "io.github.szarta.StarsReborn"
# appimage-builder requires exec to be a real ELF binary; the Python interpreter
# qualifies.  launcher.py (written into AppDir during build-appdir) handles
# starting the engine subprocess before handing off to the UI.
APP_EXEC = "usr/lib/stars-reborn/venv/bin/python3"
APP_EXEC_ARGS = "$APPDIR/usr/lib/stars-reborn/launcher.py $@"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app_version() -> str:
    """Read version from ui/src/_version.py without importing the full package."""
    version_file = UI_DIR / "src" / "_version.py"
    namespace: dict = {}
    exec(version_file.read_text(), namespace)  # noqa: S102
    return namespace["__version__"]


def _python_version() -> str:
    return f"python{sys.version_info.major}.{sys.version_info.minor}"


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(help={"release": "Build in release mode (default: True)"})
def build_engine(c, release=True):
    """Compile the stars-server Rust binary."""
    mode = "--release" if release else ""
    with c.cd(str(ENGINE_DIR)):
        c.run(f"cargo build {mode}".strip(), pty=True)
    if release and not ENGINE_BIN_SRC.exists():
        sys.exit(f"ERROR: expected binary at {ENGINE_BIN_SRC} — cargo build may have failed")
    print(f"Engine binary: {ENGINE_BIN_SRC}")


@task
def build_appdir(c):
    """Assemble the AppDir tree (Python venv, UI source, engine binary, launchers)."""
    if not ENGINE_BIN_SRC.exists():
        sys.exit(
            f"ERROR: {ENGINE_BIN_SRC} not found — run `invoke build-engine` first"
        )

    version = _app_version()
    pyver = _python_version()

    # --- directory skeleton ------------------------------------------------
    for d in [
        APPDIR / "usr" / "bin",
        APPDIR / "usr" / "lib" / "stars-reborn",
        APPDIR / "usr" / "share" / "applications",
        APPDIR / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # --- engine binary -----------------------------------------------------
    c.run(f"install -m 0755 {ENGINE_BIN_SRC} {ENGINE_BIN_DEST}")
    print(f"Installed engine -> {ENGINE_BIN_DEST}")

    # --- Python venv with UI deps ------------------------------------------
    venv_path = APPDIR / "usr" / "lib" / "stars-reborn" / "venv"
    if not (venv_path / "bin" / "python3").exists():
        # --copies ensures the interpreter is a real ELF binary inside AppDir,
        # not a symlink back to the host system — appimage-builder requires this.
        c.run(f"python3 -m venv --copies {venv_path}")
    c.run(f"{venv_path}/bin/pip install --quiet -r {UI_DIR}/requirements.txt")
    print(f"Python venv ready: {venv_path}")

    # --- UI source ---------------------------------------------------------
    ui_src_dest = APPDIR / "usr" / "lib" / "stars-reborn" / "src"
    c.run(f"rsync -a --delete {UI_DIR}/src/ {ui_src_dest}/")
    print(f"UI source -> {ui_src_dest}")

    # --- icon --------------------------------------------------------------
    if ICON_SRC.exists():
        c.run(f"cp {ICON_SRC} {ICON_DEST}")
        c.run(
            f"cp {ICON_SRC} "
            f"{APPDIR}/usr/share/icons/hicolor/256x256/apps/stars-reborn.png"
        )
    else:
        print(f"WARNING: icon not found at {ICON_SRC}; AppImage will have no icon")

    # --- .desktop file -----------------------------------------------------
    desktop_content = f"""\
[Desktop Entry]
Type=Application
Name=Stars Reborn
Comment=Faithful clone of Stars! (1995)
Exec=stars-reborn
Icon=stars-reborn
Categories=Game;StrategyGame;
Version={version}
"""
    desktop_path = APPDIR / "stars-reborn.desktop"
    desktop_path.write_text(desktop_content)
    (APPDIR / "usr" / "share" / "applications" / "stars-reborn.desktop").write_text(
        desktop_content
    )
    print(f"Desktop file: {desktop_path}")

    # --- launcher.py -------------------------------------------------------
    # This is the Python entry point called by appimage-builder's generated
    # AppRun binary.  It starts the engine subprocess, sets STARS_ENGINE_URL
    # for the UI to pick up, then runs the UI in-process.
    launcher = APPDIR / "usr" / "lib" / "stars-reborn" / "launcher.py"
    launcher.write_text(
        '"""Stars Reborn AppImage launcher — starts engine then UI."""\n'
        "import os\n"
        "import signal\n"
        "import socket\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "\n"
        "\n"
        "def _free_port() -> int:\n"
        '    with socket.socket() as s:\n'
        '        s.bind(("", 0))\n'
        "        return s.getsockname()[1]\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        '    appdir = os.environ.get("APPDIR", os.path.dirname(os.path.abspath(__file__)))\n'
        '    engine_bin = os.path.join(appdir, "usr", "bin", "stars-server")\n'
        "    port = _free_port()\n"
        "\n"
        "    engine = subprocess.Popen(\n"
        "        [engine_bin],\n"
        '        env={**os.environ, "STARS_PORT": str(port)},\n'
        "    )\n"
        "\n"
        "    def _shutdown(sig=None, frame=None):\n"
        "        engine.terminate()\n"
        "        try:\n"
        "            engine.wait(timeout=5)\n"
        "        except subprocess.TimeoutExpired:\n"
        "            engine.kill()\n"
        "        sys.exit(0)\n"
        "\n"
        "    signal.signal(signal.SIGINT, _shutdown)\n"
        "    signal.signal(signal.SIGTERM, _shutdown)\n"
        "\n"
        "    # Give the engine a moment to start listening.\n"
        "    time.sleep(0.3)\n"
        "\n"
        "    # Expose engine URL for the UI (wired in once --engine-url arg lands).\n"
        '    os.environ["STARS_ENGINE_URL"] = f"http://127.0.0.1:{port}"\n'
        "\n"
        "    from stars_reborn.main import main as ui_main  # noqa: PLC0415\n"
        "\n"
        "    rc = ui_main()\n"
        "    _shutdown()\n"
        "    return rc or 0\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    sys.exit(main())\n"
    )
    print(f"launcher.py: {launcher}")

    # --- AppRun shell script (for testing AppDir directly) -----------------
    # appimage-builder overwrites this with its own binary AppRun when
    # packaging the final image — this copy is useful for manual AppDir tests.
    apprun = APPDIR / "AppRun"
    apprun.write_text(
        "#!/bin/bash\n"
        "# Manual-test launcher — appimage-builder replaces this with AppRun2.\n"
        'APPDIR="$(dirname "$(readlink -f "$0")")"\n'
        'export PYTHONPATH="$APPDIR/usr/lib/stars-reborn/src"\n'
        'exec "$APPDIR/usr/lib/stars-reborn/venv/bin/python3" \\\n'
        '    "$APPDIR/usr/lib/stars-reborn/launcher.py" "$@"\n'
    )
    apprun.chmod(0o755)
    print(f"AppRun: {apprun}")

    print(f"\nAppDir ready: {APPDIR}")


@task
def build_appimage(c):
    """Run appimage-builder to produce the final .AppImage."""
    _write_recipe()
    # Run from build/ so appimage-builder resolves ./AppDir correctly and
    # writes the output .AppImage into build/ alongside the recipe.
    with c.cd(str(BUILD_DIR)):
        c.run("appimage-builder --recipe AppImageBuilder.yml --skip-tests", pty=True)
    images = list(BUILD_DIR.glob("Stars_Reborn*.AppImage"))
    if images:
        print(f"\nAppImage: {max(images, key=lambda p: p.stat().st_mtime)}")


@task(pre=[build_engine, build_appdir, build_appimage])
def build(c):
    """Full build: engine + AppDir + AppImage."""


@task
def clean(c):
    """Remove all build artefacts."""
    c.run(f"rm -rf {BUILD_DIR}")
    print(f"Removed {BUILD_DIR}")


# ---------------------------------------------------------------------------
# AppImageBuilder recipe (generated into build/)
# ---------------------------------------------------------------------------

def _write_recipe():
    """Write (or overwrite) the AppImageBuilder.yml recipe into build/."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    version = _app_version()
    pyver = _python_version()

    recipe = f"""\
# AppImageBuilder.yml — generated by tasks.py, do not edit by hand.
# Re-generate with: invoke build-appimage

version: 1

AppDir:
  # Relative to the recipe file (build/AppImageBuilder.yml → build/AppDir).
  path: ./AppDir

  app_info:
    id: {APP_ID}
    name: Stars Reborn
    icon: stars-reborn
    version: {version}
    exec: {APP_EXEC}
    exec_args: "{APP_EXEC_ARGS}"

  apt:
    arch: amd64
    allow_unauthenticated: true
    sources:
      - sourceline: "deb [arch=amd64] http://archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse"
        key_url: "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x3b4fe6acc0b21f32"
    include:
      - libglib2.0-0
      - libgl1
      - libfontconfig1
      - libfreetype6
      - libx11-6
      - libxcb1
      - libxext6
      - libxi6
      - libxrender1
    exclude:
      - dpkg

  files:
    exclude:
      - usr/share/doc
      - usr/share/man
      - usr/lib/{pyver}/test

  runtime:
    env:
      PYTHONHOME: "$APPDIR/usr/lib/stars-reborn/venv"
      PYTHONPATH: "$APPDIR/usr/lib/stars-reborn/src"
      QT_QPA_PLATFORM_PLUGIN_PATH: "$APPDIR/usr/lib/stars-reborn/venv/lib/{pyver}/site-packages/PySide6/Qt/plugins/platforms"

AppImage:
  arch: x86_64
  file_name: Stars_Reborn-{version}-x86_64.AppImage
"""
    RECIPE.write_text(recipe)
    print(f"Recipe written: {RECIPE}")
