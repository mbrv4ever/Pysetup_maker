"""
PySetup_Maker - Wizard om Python projecten via Nuitka naar een
self-extracting installer-exe te bouwen.

Voor persoonlijk gebruik. UI in Dravenlock-stijl (paars accent,
WCAG AAA contrast).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
    QPlainTextEdit, QListWidget, QMessageBox, QSplitter,
    QFrame, QSizePolicy, QProgressBar,
)

from core.styling import (
    COLOR, base_font, mono_font, title_font,
    app_stylesheet, primary_button_style, secondary_button_style,
    input_style, console_style, list_style, progressbar_style,
)
from core.scanner import scan_project_folder, detect_extra_files
from core.builder import BuildWorker


APP_VERSION = "0.4.11"


class _LabelledField(QWidget):
    """Helper: label + invoerveld + bladeren-knop in 1 rij."""

    def __init__(self, label: str, button_text: str = "Bladeren...",
                 read_only: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setFont(base_font(11))
        lbl.setStyleSheet(
            f"color: {COLOR.text}; background: transparent; "
            f"font-weight: bold;"
        )
        layout.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setStyleSheet(input_style())
        self.input.setMinimumHeight(40)
        self.input.setReadOnly(read_only)
        row.addWidget(self.input, stretch=1)

        self.button = QPushButton(button_text)
        self.button.setStyleSheet(secondary_button_style())
        self.button.setMinimumHeight(40)
        self.button.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.button)

        layout.addLayout(row)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PySetup_Maker  v{APP_VERSION}")
        self.resize(1240, 760)
        self.setStyleSheet(app_stylesheet())

        self._build_ui()
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[BuildWorker] = None

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        # Header
        title = QLabel("PySetup_Maker")
        title.setFont(title_font(22))
        title.setStyleSheet(
            f"color: {COLOR.text}; background: transparent;"
        )
        outer.addWidget(title)

        # Splitter: links velden | rechts console
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        outer.addWidget(splitter, stretch=1)

        # === Linker paneel: invoervelden ===
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(14)

        # Project-map kiezen
        self.fld_project = _LabelledField(
            "Project map (bevat .py en .ico)",
            "Map kiezen..."
        )
        self.fld_project.button.clicked.connect(self._on_pick_project)
        left_layout.addWidget(self.fld_project)

        # Hoofd .py
        self.fld_main = _LabelledField(
            "Hoofd .py bestand",
            "Wijzigen..."
        )
        self.fld_main.button.clicked.connect(self._on_pick_main_py)
        left_layout.addWidget(self.fld_main)

        # Icoon
        self.fld_icon = _LabelledField(
            "Icoon (.ico)",
            "Wijzigen..."
        )
        self.fld_icon.button.clicked.connect(self._on_pick_icon)
        left_layout.addWidget(self.fld_icon)

        # Merk-logo (Dravenlock) - apart van app-icon
        self.fld_brand_logo = _LabelledField(
            "Merk-logo (Dravenlock) - .png of .jpg",
            "Kiezen..."
        )
        self.fld_brand_logo.button.clicked.connect(self._on_pick_brand_logo)
        left_layout.addWidget(self.fld_brand_logo)

        # Extra bestanden (lijst + toevoegen/verwijderen)
        extras_label = QLabel("Extra bestanden / mappen")
        extras_label.setFont(base_font(11))
        extras_label.setStyleSheet(
            f"color: {COLOR.text}; background: transparent; "
            f"font-weight: bold;"
        )
        left_layout.addWidget(extras_label)

        self.list_extras = QListWidget()
        self.list_extras.setStyleSheet(list_style())
        self.list_extras.setMinimumHeight(110)
        left_layout.addWidget(self.list_extras)

        row_extras = QHBoxLayout()
        row_extras.setSpacing(8)
        btn_add_file = QPushButton("Bestand toevoegen")
        btn_add_file.setStyleSheet(secondary_button_style())
        btn_add_file.setCursor(Qt.PointingHandCursor)
        btn_add_file.clicked.connect(self._on_add_extra_file)
        row_extras.addWidget(btn_add_file)

        btn_add_dir = QPushButton("Map toevoegen")
        btn_add_dir.setStyleSheet(secondary_button_style())
        btn_add_dir.setCursor(Qt.PointingHandCursor)
        btn_add_dir.clicked.connect(self._on_add_extra_dir)
        row_extras.addWidget(btn_add_dir)

        btn_rm = QPushButton("Verwijderen")
        btn_rm.setStyleSheet(secondary_button_style())
        btn_rm.setCursor(Qt.PointingHandCursor)
        btn_rm.clicked.connect(self._on_remove_extra)
        row_extras.addWidget(btn_rm)
        row_extras.addStretch()
        left_layout.addLayout(row_extras)

        # Setup naam
        self.fld_setup_name = _LabelledField(
            "Naam van de installer (zonder .exe)",
            "Standaard"
        )
        self.fld_setup_name.button.clicked.connect(
            self._on_reset_setup_name
        )
        left_layout.addWidget(self.fld_setup_name)

        # Output-map waar de installer.exe komt
        self.fld_output = _LabelledField(
            "Output-map (waar komt de installer.exe?)",
            "Map kiezen..."
        )
        self.fld_output.button.clicked.connect(self._on_pick_output)
        left_layout.addWidget(self.fld_output)

        left_layout.addStretch()
        splitter.addWidget(left)

        # === Rechter paneel: console + actie-knoppen ===
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        console_label = QLabel("Build-output")
        console_label.setFont(base_font(11))
        console_label.setStyleSheet(
            f"color: {COLOR.text}; background: transparent; "
            f"font-weight: bold;"
        )
        right_layout.addWidget(console_label)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(console_style())
        self.console.setFont(mono_font(10))
        self.console.appendPlainText(
            "PySetup_Maker klaar. Kies een project-map om te beginnen."
        )
        right_layout.addWidget(self.console, stretch=1)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setStyleSheet(progressbar_style())
        right_layout.addWidget(self.progress)

        # Actie-knoppen
        row_actions = QHBoxLayout()
        row_actions.setSpacing(10)
        row_actions.addStretch()

        self.btn_cancel = QPushButton("Annuleren")
        self.btn_cancel.setStyleSheet(secondary_button_style())
        self.btn_cancel.setMinimumHeight(44)
        self.btn_cancel.setMinimumWidth(140)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        row_actions.addWidget(self.btn_cancel)

        self.btn_make = QPushButton("Maken")
        self.btn_make.setStyleSheet(primary_button_style())
        self.btn_make.setMinimumHeight(44)
        self.btn_make.setMinimumWidth(160)
        self.btn_make.setCursor(Qt.PointingHandCursor)
        self.btn_make.clicked.connect(self._on_make)
        row_actions.addWidget(self.btn_make)

        right_layout.addLayout(row_actions)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([580, 580])

    # === Event handlers ===

    def _on_pick_project(self):
        d = QFileDialog.getExistingDirectory(
            self, "Kies project-map",
            self.fld_project.input.text() or str(Path.home())
        )
        if not d:
            return
        self.fld_project.input.setText(d)
        self._auto_fill_from_project(d)

    def _auto_fill_from_project(self, folder: str):
        """Scan map en vul .py / .ico / extra's automatisch."""
        main_py, icon, all_py = scan_project_folder(folder)

        if main_py:
            self.fld_main.input.setText(main_py)
            self._log(f"Hoofd .py gevonden: {Path(main_py).name}")
        else:
            self.fld_main.input.setText("")
            self._log(
                f"Geen duidelijke hoofd-.py gevonden. "
                f"Beschikbare .py: {', '.join(all_py) or '(geen)'}"
            )

        if icon:
            self.fld_icon.input.setText(icon)
            self._log(f"Icoon gevonden: {Path(icon).name}")
        else:
            self.fld_icon.input.setText("")
            self._log("Geen .ico in de map - geen icoon gebruikt.")

        # Auto-detect merk-logo (dravenlock_logo.png/jpg/jpeg in projectmap)
        # OF onthouden van vorige keuze - we slaan dat hier nog niet op,
        # maar bij volgende versie wel via config.
        if not self.fld_brand_logo.input.text():
            for name in ("dravenlock_logo.png", "dravenlock_logo.jpg",
                         "dravenlock_logo.jpeg", "logo.png", "logo.jpg",
                         "logo.jpeg"):
                p = Path(folder) / name
                if p.is_file():
                    self.fld_brand_logo.input.setText(str(p))
                    self._log(f"Merk-logo gevonden: {p.name}")
                    break

        # Extra's voorstellen (niet de hoofd .py en niet het icoon)
        self.list_extras.clear()
        if main_py:
            extras = detect_extra_files(folder, main_py, icon)
            for e in extras:
                self.list_extras.addItem(e)
            if extras:
                self._log(
                    f"{len(extras)} extra bestanden / mappen "
                    f"voorgesteld (verwijder wat niet hoort)."
                )

        # Setup-naam default: mapnaam
        if not self.fld_setup_name.input.text():
            self.fld_setup_name.input.setText(
                f"{Path(folder).name}_setup"
            )

        # Output-map default: <projectmap>/installer
        if not self.fld_output.input.text():
            self.fld_output.input.setText(
                str(Path(folder) / "installer")
            )

    def _on_pick_output(self):
        start = self.fld_output.input.text() or str(Path.home())
        d = QFileDialog.getExistingDirectory(
            self, "Output-map voor de installer", start
        )
        if d:
            self.fld_output.input.setText(d)

    def _on_pick_main_py(self):
        start = self.fld_project.input.text() or str(Path.home())
        f, _ = QFileDialog.getOpenFileName(
            self, "Hoofd .py bestand", start,
            "Python (*.py);;Alle bestanden (*)"
        )
        if f:
            self.fld_main.input.setText(f)

    def _on_pick_icon(self):
        start = self.fld_project.input.text() or str(Path.home())
        f, _ = QFileDialog.getOpenFileName(
            self, "Icoon (.ico)", start,
            "Icoon (*.ico);;Alle bestanden (*)"
        )
        if f:
            self.fld_icon.input.setText(f)

    def _on_pick_brand_logo(self):
        start = (self.fld_brand_logo.input.text()
                 or self.fld_project.input.text()
                 or str(Path.home()))
        if start and Path(start).is_file():
            start = str(Path(start).parent)
        f, _ = QFileDialog.getOpenFileName(
            self, "Merk-logo (Dravenlock)", start,
            "Afbeelding (*.png *.jpg *.jpeg);;Alle bestanden (*)"
        )
        if f:
            self.fld_brand_logo.input.setText(f)

    def _on_add_extra_file(self):
        start = self.fld_project.input.text() or str(Path.home())
        files, _ = QFileDialog.getOpenFileNames(
            self, "Extra bestanden", start
        )
        for f in files:
            self.list_extras.addItem(f)

    def _on_add_extra_dir(self):
        start = self.fld_project.input.text() or str(Path.home())
        d = QFileDialog.getExistingDirectory(
            self, "Extra map", start
        )
        if d:
            self.list_extras.addItem(d)

    def _on_remove_extra(self):
        for item in self.list_extras.selectedItems():
            self.list_extras.takeItem(self.list_extras.row(item))

    def _on_reset_setup_name(self):
        folder = self.fld_project.input.text()
        if folder:
            self.fld_setup_name.input.setText(
                f"{Path(folder).name}_setup"
            )

    # === Build flow ===

    def _log(self, msg: str):
        self.console.appendPlainText(msg)

    def _validate(self) -> Optional[str]:
        """Returns foutmelding of None."""
        main_py = self.fld_main.input.text().strip()
        if not main_py or not Path(main_py).is_file():
            return "Geef een geldig hoofd-.py bestand op."
        setup_name = self.fld_setup_name.input.text().strip()
        if not setup_name:
            return "Geef een naam voor de installer op."
        # Geen ongeldige chars
        bad = set('<>:"/\\|?*')
        if any(c in setup_name for c in bad):
            return ("Setup-naam mag geen van deze tekens bevatten: "
                    '< > : " / \\ | ? *')
        icon = self.fld_icon.input.text().strip()
        if icon and not Path(icon).is_file():
            return "Het opgegeven icoon-bestand bestaat niet."
        return None

    def _on_make(self):
        err = self._validate()
        if err:
            QMessageBox.warning(self, "Niet compleet", err)
            return

        main_py = self.fld_main.input.text().strip()
        icon = self.fld_icon.input.text().strip() or None
        brand_logo = self.fld_brand_logo.input.text().strip() or None
        setup_name = self.fld_setup_name.input.text().strip()
        project_folder = (self.fld_project.input.text().strip()
                          or str(Path(main_py).parent))

        # Extra bestanden
        extras: List[str] = []
        for i in range(self.list_extras.count()):
            extras.append(self.list_extras.item(i).text())

        # Output-map = wat in het veld staat, anders fallback
        output_folder = self.fld_output.input.text().strip()
        if not output_folder:
            output_folder = str(Path(project_folder) / "installer")

        # Reset console + progress
        self.console.clear()
        self.progress.setValue(0)
        self._log(f"=== Build starten: {setup_name} ===")
        self._log(f"Project    : {project_folder}")
        self._log(f"Hoofd      : {main_py}")
        self._log(f"Icoon      : {icon or '(geen)'}")
        self._log(f"Merk-logo  : {brand_logo or '(geen)'}")
        self._log(f"Extras     : {len(extras)} stuks")
        self._log(f"Output     : {output_folder}")
        self._log("")

        # UI in build-mode
        self._set_building(True)

        # Worker op een achtergrond-thread
        self._worker_thread = QThread()
        self._worker = BuildWorker(
            project_folder=project_folder,
            main_py=main_py,
            icon=icon,
            brand_logo=brand_logo,
            extra_files=extras,
            setup_name=setup_name,
            output_folder=output_folder,
            app_display_name=setup_name.replace("_setup", "")
                                       .replace("-setup", ""),
        )
        self._worker.moveToThread(self._worker_thread)
        self._worker.log_message.connect(self._log)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._on_build_done)
        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    def _on_cancel(self):
        if self._worker is not None:
            self._log("")
            self._log(">>> Annuleren aangevraagd...")
            self._worker.cancel()

    def _on_build_done(self, ok: bool, info: str):
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait()
        self._worker_thread = None
        self._worker = None
        self._set_building(False)

        if ok:
            self.progress.setValue(100)
            QMessageBox.information(
                self, "Klaar",
                f"Installer succesvol gemaakt:\n\n{info}"
            )
        else:
            QMessageBox.warning(
                self, "Mislukt",
                f"Build is niet voltooid:\n\n{info}"
            )

    def _set_building(self, building: bool):
        self.btn_make.setEnabled(not building)
        self.btn_cancel.setEnabled(building)
        self.fld_project.button.setEnabled(not building)
        self.fld_main.button.setEnabled(not building)
        self.fld_icon.button.setEnabled(not building)
        self.fld_brand_logo.button.setEnabled(not building)
        self.fld_output.button.setEnabled(not building)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PySetup_Maker")
    win = MainWindow()
    win.show()
    try:  # Dravenlock: stille update-check (uit te zetten; Ctrl+Shift+U = met de hand)
        import drave_update
        drave_update.start(win, 'Pysetup_maker', APP_VERSION)
    except Exception:
        pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
