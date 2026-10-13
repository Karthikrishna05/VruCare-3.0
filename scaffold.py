"""Create VruCare's folder layout and a ready-to-use virtual environment.

Run from the project root with Python 3.13:
    py -3.13 scaffold.py        (Windows)
    python3.13 scaffold.py      (Linux / macOS)

Safe to run again: existing folders, files and the venv are kept; pip only installs what is missing.
Standard library only, so it works before anything is installed.
"""

import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIRED_PYTHON = (3, 13)  # the version requirements*.txt were resolved and tested on

# Python packages: each gets an empty __init__.py so it can be imported.
PACKAGES = [
    "config",
    "config/settings",
    "apps",
    "apps/corpus",
    "apps/corpus/management",
    "apps/corpus/management/commands",
    "apps/retrieval",
    "apps/retrieval/management",
    "apps/retrieval/management/commands",
    "apps/chat",
    "apps/agents",
    "apps/evaluation",
    "apps/evaluation/management",
    "apps/evaluation/management/commands",
    "tests",
]

# Plain folders (not imported as code).
FOLDERS = [
    "configs",  # benchmark YAML configs
    "data/corpus",  # the 17 PDFs — check licensing before committing (docs/SAFETY.md §7)
    "data/eval",  # the 40 evaluation questions
    "templates",  # project-wide HTML templates
    "static/css",  # compiled Tailwind CSS
    "loadtest",  # Locust scenarios
    "deploy/nginx",  # load balancer config
    "deploy/prometheus",  # metrics scrape config
    "deploy/grafana",  # dashboards
    ".github/workflows",  # CI
]

# Deepest file the pinned packages install, relative to site-packages (measured: 126 chars, in transformers).
LONGEST_INSTALLED_PATH = 130
WINDOWS_MAX_PATH = 260


def check_python() -> None:
    if sys.version_info[:2] != REQUIRED_PYTHON:
        want = ".".join(map(str, REQUIRED_PYTHON))
        sys.exit(
            f"Python {want} is required (this is {sys.version.split()[0]}). Run: py -{want} scaffold.py"
        )


def long_paths_enabled() -> bool:
    import winreg  # Windows-only module, imported only on Windows

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as key:
            return winreg.QueryValueEx(key, "LongPathsEnabled")[0] == 1
    except OSError:
        return False


def check_path_length() -> None:
    """pip fails half-way on Windows if a file path would exceed 260 characters."""
    if sys.platform != "win32" or long_paths_enabled():
        return
    deepest = len(str(VENV / "Lib" / "site-packages")) + 1 + LONGEST_INSTALLED_PATH
    if deepest >= WINDOWS_MAX_PATH:
        sys.exit(
            f"Project path is too long for Windows ({deepest} >= {WINDOWS_MAX_PATH} characters once installed).\n"
            "Move the project to a shorter folder, or enable Windows long-path support yourself."
        )


def make_layout() -> None:
    for folder in PACKAGES:
        path = ROOT / folder
        path.mkdir(parents=True, exist_ok=True)
        (path / "__init__.py").touch(exist_ok=True)
    for folder in FOLDERS:
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    print(f"Folders ready: {len(PACKAGES)} packages, {len(FOLDERS)} plain folders.")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(*args: str) -> None:
    print("  $", " ".join(args))
    subprocess.run(args, check=True)


def make_venv() -> None:
    if not venv_python().exists():
        print(f"Creating virtual environment in {VENV} ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    py = str(venv_python())
    run(py, "-m", "pip", "install", "--upgrade", "pip")
    run(py, "-m", "pip", "install", "-r", str(ROOT / "requirements-dev.txt"))
    run(py, "-m", "pip", "check")  # fails loudly if any installed versions conflict


def main() -> None:
    # Keep our messages in order with pip's output, even when piped.
    sys.stdout.reconfigure(line_buffering=True)
    check_python()
    check_path_length()
    make_layout()
    make_venv()
    activate = (
        r".venv\Scripts\activate"
        if sys.platform == "win32"
        else "source .venv/bin/activate"
    )
    print(f"\nDone. Activate the environment with:  {activate}")


if __name__ == "__main__":
    main()
