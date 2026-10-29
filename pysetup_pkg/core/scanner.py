"""
core/scanner.py - Scan een project-map voor het hoofd-Python bestand
en een icoon.

Heuristieken voor hoofd-script (van best naar minst):
  1. main.py
  2. app.py
  3. <mapnaam>.py
  4. run.py / start.py / __main__.py
  5. Enige .py in de root (als er maar 1 is)
  6. Eerste .py met 'if __name__ == "__main__"' erin

Voor icoon: eerste .ico bestand in de root.
"""
from pathlib import Path
from typing import Optional, Tuple, List


_MAIN_SCRIPT_PREFERENCES = (
    "main.py",
    "app.py",
    "run.py",
    "start.py",
    "__main__.py",
)


def scan_project_folder(folder: str) -> Tuple[Optional[str],
                                              Optional[str],
                                              List[str]]:
    """
    Scan een map.

    Returns:
        (hoofd_py_pad, icon_pad, lijst_van_alle_py_in_root)

    Beide paden zijn None als niets gevonden is.
    """
    p = Path(folder)
    if not p.is_dir():
        return None, None, []

    # Verzamel alle .py-bestanden in de root (niet subdirs)
    py_files = sorted([f for f in p.iterdir()
                       if f.is_file() and f.suffix.lower() == ".py"])
    py_names = [f.name for f in py_files]

    # 1. Voorkeurslijst
    main_py: Optional[Path] = None
    for pref in _MAIN_SCRIPT_PREFERENCES:
        candidate = p / pref
        if candidate.is_file():
            main_py = candidate
            break

    # 2. <mapnaam>.py
    if main_py is None:
        candidate = p / f"{p.name}.py"
        if candidate.is_file():
            main_py = candidate

    # 3. Enige .py
    if main_py is None and len(py_files) == 1:
        main_py = py_files[0]

    # 4. Eerste met __main__-guard
    if main_py is None:
        for f in py_files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                if '__name__ == "__main__"' in text or \
                   "__name__ == '__main__'" in text:
                    main_py = f
                    break
            except Exception:
                continue

    # Icoon: eerste .ico
    ico_files = sorted([f for f in p.iterdir()
                        if f.is_file() and f.suffix.lower() == ".ico"])
    icon = ico_files[0] if ico_files else None

    return (
        str(main_py) if main_py else None,
        str(icon) if icon else None,
        py_names,
    )


def detect_extra_files(folder: str, main_py: str,
                       icon: Optional[str]) -> List[str]:
    """
    Detecteer welke extra bestanden in dezelfde map mogelijk
    bij het project horen (data, configs, sub-maps).

    Sluit uit: het hoofd-py, het icoon, en typische build-output.
    """
    p = Path(folder)
    if not p.is_dir():
        return []

    excluded_names = {Path(main_py).name if main_py else "",
                      Path(icon).name if icon else ""}
    excluded_dirs = {"__pycache__", "build", "dist", ".git",
                     ".venv", "venv", ".idea", ".vscode",
                     "build_output", "build_output_debug",
                     "build_output_folder", "node_modules"}

    extras: List[str] = []
    for item in sorted(p.iterdir()):
        if item.name in excluded_names:
            continue
        if item.name.startswith("."):
            continue
        if item.is_dir() and item.name in excluded_dirs:
            continue
        if item.suffix.lower() in (".pyc", ".pyo"):
            continue
        extras.append(str(item))

    return extras
