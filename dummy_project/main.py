"""
Dummy testapp voor PySetup_Maker.

Klein Qt-venster met:
  - Een titel
  - Een knop "Klik mij"
  - Een teller die elke klik telt
  - Leest data.txt en config.json om te testen dat extra bestanden
    correct mee-geinstalleerd worden door de installer.
"""
import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QMessageBox,
)


def _candidate_dirs():
    """
    Geef alle mogelijke locaties terug waar extras kunnen staan,
    op volgorde van waarschijnlijkheid voor Nuitka --onefile:

      1. sys.argv[0]'s parent  <- BIJ NUITKA ONEFILE IS DIT
         de echte install-map. sys.executable wijst dan namelijk
         naar de tempdir waar Nuitka zichzelf uitpakt!
      2. __file__'s parent (bij python script.py development)
      3. sys.executable's parent (alleen voor non-Nuitka builds)
      4. cwd (current working directory)
    """
    dirs = []
    # 1. sys.argv[0] - bij Nuitka --onefile = echte exe-pad
    try:
        argv0 = Path(sys.argv[0]).resolve()
        if argv0.is_file():
            dirs.append(argv0.parent)
        else:
            dirs.append(argv0)
    except Exception:
        pass
    # 2. __file__ - voor development (python main.py)
    try:
        dirs.append(Path(__file__).resolve().parent)
    except NameError:
        pass
    # 3. sys.executable - meestal NIET wat we willen bij Nuitka
    #    onefile (wijst naar temp), maar wel bruikbaar bij plain
    #    Python (wijst naar python.exe map - nutteloos), dus
    #    laatste in de rij.
    try:
        dirs.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    # 4. cwd
    try:
        dirs.append(Path.cwd())
    except Exception:
        pass

    # Dedupe met behoud van volgorde
    seen = set()
    out = []
    for d in dirs:
        key = str(d).lower()
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _read_extras():
    """
    Lees data.txt en config.json. Probeert meerdere locaties
    omdat Nuitka --onefile met paden kan rommelen.
    """
    found = {
        "data_txt": None, "config_json": None,
        "search_dirs": [], "data_from": None, "config_from": None,
    }

    for base in _candidate_dirs():
        found["search_dirs"].append(str(base))

        if found["data_txt"] is None:
            p = base / "data.txt"
            if p.is_file():
                try:
                    found["data_txt"] = p.read_text(encoding="utf-8")
                    found["data_from"] = str(p)
                except Exception as e:
                    found["data_txt"] = f"(leesfout: {e})"

        if found["config_json"] is None:
            p = base / "config.json"
            if p.is_file():
                try:
                    found["config_json"] = json.loads(
                        p.read_text(encoding="utf-8")
                    )
                    found["config_from"] = str(p)
                except Exception as e:
                    found["config_json"] = {"error": str(e)}

    return found


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dummy App - PySetup_Maker test")
        self.resize(640, 520)
        self.setStyleSheet(
            "QMainWindow { background: #111114; } "
            "QWidget { color: #e8eaef; }"
        )
        self._clicks = 0
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(28, 28, 28, 28)
        v.setSpacing(16)

        title = QLabel("Hallo!")
        title.setAlignment(Qt.AlignCenter)
        f = QFont("Segoe UI", 22)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #e8eaef;")
        v.addWidget(title)

        # Toon extra's status
        extras = _read_extras()

        # Toon ALLE zoek-mappen (helpt diagnose bij problemen)
        dirs_text = "Gezocht in:\n" + "\n".join(
            "  " + d for d in extras["search_dirs"]
        )
        search_lbl = QLabel(dirs_text)
        search_lbl.setAlignment(Qt.AlignLeft)
        search_lbl.setFont(QFont("Consolas", 8))
        search_lbl.setStyleSheet("color: #a0a4ad;")
        search_lbl.setWordWrap(True)
        v.addWidget(search_lbl)

        if extras["data_txt"]:
            preview = extras["data_txt"].strip().splitlines()
            preview_text = (preview[0] if preview else "(leeg)")[:50]
            data_status = ("✓ data.txt: " + preview_text +
                           "\n  uit: " + (extras["data_from"] or "?"))
            data_color = "#5ad988"
        else:
            data_status = "✗ data.txt NIET gevonden"
            data_color = "#ff7a6f"

        if extras["config_json"]:
            cfg = extras["config_json"]
            version = (cfg.get("version", "?") if isinstance(cfg, dict)
                       else "?")
            config_status = ("✓ config.json gevonden, version=" + str(version)
                             + "\n  uit: " + (extras["config_from"] or "?"))
            config_color = "#5ad988"
        else:
            config_status = "✗ config.json NIET gevonden"
            config_color = "#ff7a6f"

        for status, color in ((data_status, data_color),
                              (config_status, config_color)):
            lbl = QLabel(status)
            lbl.setAlignment(Qt.AlignLeft)
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet(f"color: {color};")
            lbl.setWordWrap(True)
            v.addWidget(lbl)

        self.lbl_count = QLabel("Klikken: 0")
        self.lbl_count.setAlignment(Qt.AlignCenter)
        self.lbl_count.setFont(QFont("Segoe UI", 14))
        self.lbl_count.setStyleSheet("color: #e8eaef;")
        v.addWidget(self.lbl_count)

        btn = QPushButton("Klik mij")
        btn.setMinimumHeight(48)
        btn.setStyleSheet(
            "QPushButton { background: #c0c8d4; color: #111114; "
            "border: none; border-radius: 10px; padding: 10px 28px; "
            "font-weight: bold; font-size: 13pt; } "
            "QPushButton:hover { background: #d4dae3; }"
        )
        btn.clicked.connect(self._on_click)
        v.addWidget(btn)

        v.addStretch()

    def _on_click(self):
        self._clicks += 1
        self.lbl_count.setText("Klikken: " + str(self._clicks))
        if self._clicks == 10:
            QMessageBox.information(
                self, "Tien!",
                "Je hebt 10 keer geklikt. De installer + de extra "
                "bestanden lijken te werken."
            )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Dummy App")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
