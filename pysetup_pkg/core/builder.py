"""
core/builder.py - De build-pipeline.

Stappen:
  1. Nuitka --standalone compileert het hoofd-py naar app.dist/
  2. payload.zip met app/ + extras/ + meta/icon.ico
  3. installer_stub.py wordt gerenderd uit templates en
     gecompileerd met Nuitka --standalone --onefile naar
     <setup_name>.exe

Werkt op een achtergrond-thread (QThread / QObject moveToThread).
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from core.uninstaller_template import render_uninstaller
from core.installer_stub_template import render_installer_stub


# Windows: voorkom CMD-flits bij subprocess.
# CREATE_NO_WINDOW alleen werkt niet altijd op cmd-based processes,
# dus we combineren met STARTUPINFO + SW_HIDE.
_NO_WINDOW = 0x08000000


def _hidden_startupinfo():
    """STARTUPINFO met SW_HIDE - werkt op Windows, None op andere OS."""
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        return si
    except AttributeError:
        # STARTUPINFO bestaat niet op Linux/macOS
        return None


class BuildWorker(QObject):
    """
    Voert de complete build uit op een achtergrond-thread.

    Signalen:
      log_message(str)      - regel voor het console-venster
      progress(int)         - 0..100
      finished(bool, str)   - True/False + pad-of-fout
    """
    log_message = Signal(str)
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(
        self,
        project_folder: str,
        main_py: str,
        icon: Optional[str],
        extra_files: List[str],
        setup_name: str,
        output_folder: str,
        app_display_name: Optional[str] = None,
        brand_logo: Optional[str] = None,
    ):
        super().__init__()
        self.project_folder = project_folder
        self.main_py = main_py
        self.icon = icon
        self.brand_logo = brand_logo
        self.extra_files = extra_files or []
        self.setup_name = setup_name
        self.output_folder = output_folder
        self.app_display_name = app_display_name or setup_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _log(self, msg: str):
        self.log_message.emit(msg)

    def _check_cancel(self):
        if self._cancelled:
            raise RuntimeError("Geannuleerd door gebruiker")

    def _make_brand_ico(self, work_dir: Path) -> Optional[Path]:
        """
        Converteer het brand-logo (PNG of JPG) naar een Windows .ico
        bestand met meerdere groottes (16, 24, 32, 48, 64, 128, 256).
        Dit wordt gebruikt als exe-icoon voor BOTH de installer EN
        de uninstaller, zodat ze visueel als Dravenlock-product te
        herkennen zijn.

        Returns: Path naar het .ico, of None als er geen brand-logo
        is meegegeven of de conversie faalt.
        """
        if not self.brand_logo:
            return None
        src = Path(self.brand_logo)
        if not src.is_file():
            return None

        try:
            from PIL import Image
        except ImportError:
            self._log("  WAARSCHUWING: Pillow (PIL) niet geinstalleerd, "
                      "kan brand-logo niet naar .ico converteren.")
            self._log("  Installeer met: pip install Pillow")
            return None

        try:
            img = Image.open(src)
            # ICO ondersteunt geen JPG transparantie - converteer
            # naar RGBA voor het geval er een transparantie-channel is
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            # Standaard Windows icon-groottes
            sizes = [(16, 16), (24, 24), (32, 32), (48, 48),
                     (64, 64), (128, 128), (256, 256)]

            # KRITIEK: schrijf brand_icon.ico in een APARTE map,
            # niet in work_dir zelf. Reden: Nuitka draait met
            # --output-dir=work_dir EN --remove-output, en kan
            # daarbij onze .ico opruimen tussen build-stappen door.
            assets_dir = work_dir / "_brand_assets"
            assets_dir.mkdir(exist_ok=True)
            ico_path = assets_dir / "brand_icon.ico"
            img.save(ico_path, format="ICO", sizes=sizes)
            self._log("  -> " + str(ico_path) + " (multi-resolution)")
            return ico_path
        except Exception as e:
            self._log("  WAARSCHUWING: brand-logo conversie naar "
                      ".ico faalde: " + str(e))
            return None

    # === Stap 1: Nuitka onefile-build van het hoofd-script ===

    def _run_nuitka_onefile(self, work_dir: Path) -> Path:
        """
        Bouw de doel-app als 1 enkele exe via --standalone --onefile.

        Resultaat: <work_dir>/<app_name>.exe (geen .dist map met
        losse DLL's). Bij install komt deze .exe + de extras in
        de install-map - geen tientallen losse files meer.
        """
        self._log("=== STAP 1/4: Nuitka build van je app (--onefile) ===")
        self.progress.emit(5)

        main_py = Path(self.main_py)
        app_name = main_py.stem

        cmd = [
            "python", "-m", "nuitka",
            "--standalone",
            "--onefile",
            "--enable-plugin=pyside6",
            "--windows-console-mode=disable",
            "--output-dir=" + str(work_dir),
            "--output-filename=" + app_name + ".exe",
            "--assume-yes-for-downloads",
            "--remove-output",
            # Product-metadata: maakt de exe minder verdacht voor
            # Windows Defender. Een onbekende exe ZONDER metadata
            # wordt vaak als SmartScreen-onbekend gemarkeerd.
            "--product-name=" + self.app_display_name,
            "--product-version=1.0.0",
            "--file-version=1.0.0",
            "--file-description=" + self.app_display_name,
            "--company-name=" + self.app_display_name,
            # Deterministische tempdir-naam ipv random onefile_XXXX.
            # Helpt ook tegen Defender heuristieken (random temp
            # uitpak is een malware-patroon).
            "--onefile-tempdir-spec=%TEMP%/%PRODUCT%-%PID%",
            "--onefile-cache-mode=temporary",
        ]
        if self.icon and Path(self.icon).is_file():
            cmd.append("--windows-icon-from-ico=" + str(self.icon))

        cmd.append(str(main_py))

        self._log("  Commando: " + " ".join(cmd))
        self._log("")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(main_py.parent),
                creationflags=_NO_WINDOW,

                startupinfo=_hidden_startupinfo(),
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Nuitka niet gevonden. Installeer met: "
                "pip install nuitka"
            )

        assert proc.stdout is not None
        for line in proc.stdout:
            self._check_cancel()
            self._log("  " + line.rstrip())

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                "Nuitka build mislukt (exit " +
                str(proc.returncode) + ")"
            )

        # Onefile-output is gewoon <app_name>.exe in work_dir
        exe_path = work_dir / (app_name + ".exe")
        if not exe_path.is_file():
            raise RuntimeError(
                "Verwachte .exe niet gevonden: " + str(exe_path)
            )

        size_mb = exe_path.stat().st_size / (1024 * 1024)
        self._log("")
        self._log("  -> " + exe_path.name + " (" +
                  f"{size_mb:.1f}" + " MB)")
        self.progress.emit(50)
        return exe_path

    # === Stap 1B: Uninstaller pre-bouwen tot uninstall.exe ===

    def _build_uninstaller_exe(self, work_dir: Path) -> Path:
        """
        Bouw uninstall.exe nu, tijdens de PySetup_Maker build.
        Zo hoeft de installer op de doel-pc niets te compileren
        (geen Nuitka nodig, geen timeout, geen .bat fallback).
        """
        self._log("")
        self._log("=== STAP 2/4: Uninstaller voorbouwen ===")
        self.progress.emit(52)

        # Inbakken van brand-logo in de uninstaller (base64)
        # zodat 'ie altijd zichtbaar is in de bevestigings-dialog,
        # ongeacht Windows icon-cache of andere quirks.
        brand_logo_b64 = ""
        brand_logo_ext = ""
        if self.brand_logo and Path(self.brand_logo).is_file():
            ext = Path(self.brand_logo).suffix.lower()
            if ext in (".png", ".jpg", ".jpeg"):
                with open(self.brand_logo, "rb") as f:
                    brand_logo_b64 = base64.b64encode(
                        f.read()).decode("ascii")
                brand_logo_ext = ext.lstrip(".")

        uninstaller_code = render_uninstaller(
            app_name=self.app_display_name,
            brand_logo_b64=brand_logo_b64,
            brand_logo_ext=brand_logo_ext,
        )
        uninst_py = work_dir / "uninstall.py"
        uninst_py.write_text(uninstaller_code, encoding="utf-8")

        cmd = [
            "python", "-m", "nuitka",
            "--standalone",
            "--onefile",
            "--enable-plugin=pyside6",
            "--windows-console-mode=disable",
            "--output-dir=" + str(work_dir / "uninst_build"),
            "--output-filename=uninstall.exe",
            "--assume-yes-for-downloads",
            "--remove-output",
            "--product-name=" + self.app_display_name + " Uninstaller",
            "--product-version=1.0.0",
            "--file-version=1.0.0",
            "--file-description=" + self.app_display_name + " Uninstaller",
            "--company-name=" + self.app_display_name,
            "--onefile-tempdir-spec=%TEMP%/%PRODUCT%-%PID%",
            "--onefile-cache-mode=temporary",
        ]
        # Voor uninstall.exe: gebruik Dravenlock brand-icon (consistent
        # over alle Dravenlock-apps). Fallback naar app-icon als er
        # geen brand-logo meegegeven is.
        ico_to_use = (self._brand_ico_path
                      if getattr(self, "_brand_ico_path", None)
                      else self.icon)
        if ico_to_use and Path(ico_to_use).is_file():
            cmd.append("--windows-icon-from-ico=" + str(ico_to_use))
            self._log("  Uninstaller exe-icoon: " + str(ico_to_use))
        else:
            self._log("  Uninstaller: GEEN icoon meegegeven aan Nuitka")
        cmd.append(str(uninst_py))

        self._log("  Commando: " + " ".join(cmd))
        self._log("")

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            creationflags=_NO_WINDOW,

            startupinfo=_hidden_startupinfo(),
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            self._check_cancel()
            self._log("  " + line.rstrip())

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                "Uninstaller-build mislukt (exit "
                + str(proc.returncode) + ")"
            )

        exe_path = work_dir / "uninst_build" / "uninstall.exe"
        if not exe_path.is_file():
            raise RuntimeError(
                "uninstall.exe niet gevonden: " + str(exe_path)
            )
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        self._log("")
        self._log("  -> uninstall.exe (" + f"{size_mb:.1f}" + " MB)")
        self.progress.emit(62)
        return exe_path

    def _create_payload_zip(self, app_exe: Path, uninstall_exe: Path,
                             work_dir: Path) -> Path:
        """
        Pak de single-exe app + pre-built uninstall.exe + extras +
        icon in 1 payload.zip. Bij install komt er 1 .exe +
        uninstall.exe + extras in de install-map.
        """
        self._log("")
        self._log("=== STAP 3/4: Payload samenstellen ===")

        zip_path = work_dir / "payload.zip"
        with zipfile.ZipFile(zip_path, "w",
                              compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(app_exe, arcname="app/" + app_exe.name)
            self._log("  + app/" + app_exe.name)

            zf.write(uninstall_exe, arcname="app/uninstall.exe")
            self._log("  + app/uninstall.exe")

            for extra in self.extra_files:
                self._check_cancel()
                ep = Path(extra)
                if not ep.exists():
                    self._log("  WAARSCHUWING: " + extra +
                              " bestaat niet, overgeslagen")
                    continue
                if ep.is_file():
                    zf.write(ep, arcname="extras/" + ep.name)
                    self._log("  + extras/" + ep.name)
                elif ep.is_dir():
                    cnt = 0
                    for r2, _d, files in os.walk(ep):
                        for f in files:
                            self._check_cancel()
                            full = Path(r2) / f
                            rel = full.relative_to(ep.parent)
                            zf.write(full, arcname="extras/" + str(rel))
                            cnt += 1
                    self._log("  + extras/" + ep.name + "/  (" +
                              str(cnt) + " bestanden)")

            if self.icon and Path(self.icon).is_file():
                zf.write(self.icon, arcname="meta/icon.ico")
                self._log("  + meta/icon.ico")

            # Merk-logo (Dravenlock) - PNG of JPG, behoud extensie
            if self.brand_logo and Path(self.brand_logo).is_file():
                ext = Path(self.brand_logo).suffix.lower()
                if ext in (".png", ".jpg", ".jpeg"):
                    arc_name = "meta/brand_logo" + ext
                    zf.write(self.brand_logo, arcname=arc_name)
                    self._log("  + " + arc_name)
                else:
                    self._log("  WAARSCHUWING: merk-logo extensie "
                              + ext + " niet ondersteund, overgeslagen")

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        self._log("  -> payload.zip: " + f"{size_mb:.1f}" + " MB")
        self.progress.emit(72)
        return zip_path

    def _render_stub(self, payload_zip: Path,
                     work_dir: Path) -> Path:
        self._log("")
        self._log("  Installer-stub renderen...")

        with open(payload_zip, "rb") as f:
            payload_b64 = base64.b64encode(f.read()).decode("ascii")

        main_py = Path(self.main_py)
        app_exe_name = main_py.stem + ".exe"

        stub_code = render_installer_stub(
            app_display_name=self.app_display_name,
            app_exe_name=app_exe_name,
            payload_b64=payload_b64,
        )

        stub_path = work_dir / "installer_stub.py"
        stub_path.write_text(stub_code, encoding="utf-8")
        size_kb = stub_path.stat().st_size // 1024
        self._log("  -> " + stub_path.name +
                  " (" + str(size_kb) + " KB)")
        return stub_path

    # === Stap 3: stub compileren naar installer.exe ===

    def _compile_stub_to_exe(self, stub_path: Path,
                              work_dir: Path) -> Path:
        self._log("")
        self._log("=== STAP 4/4: Installer-exe bouwen ===")
        self.progress.emit(75)

        installer_build = work_dir / "installer_build"
        cmd = [
            "python", "-m", "nuitka",
            "--standalone",
            "--onefile",
            "--enable-plugin=pyside6",
            "--windows-console-mode=disable",
            "--include-module=base64",
            "--include-module=zipfile",
            "--include-module=tempfile",
            "--include-module=winreg",
            "--output-dir=" + str(installer_build),
            "--output-filename=" + self.setup_name + ".exe",
            "--assume-yes-for-downloads",
            "--remove-output",
            "--product-name=" + self.app_display_name + " Installer",
            "--product-version=1.0.0",
            "--file-version=1.0.0",
            "--file-description=" + self.app_display_name + " Installer",
            "--company-name=" + self.app_display_name,
            "--onefile-tempdir-spec=%TEMP%/%PRODUCT%-%PID%-Installer",
            "--onefile-cache-mode=temporary",
        ]
        # Voor installer.exe: gebruik Dravenlock brand-icon (zodat
        # je voor install al ziet dat 't een Dravenlock-product is).
        # Fallback naar app-icon als er geen brand-logo is.
        ico_to_use = (self._brand_ico_path
                      if getattr(self, "_brand_ico_path", None)
                      else self.icon)
        if ico_to_use and Path(ico_to_use).is_file():
            cmd.append("--windows-icon-from-ico=" + str(ico_to_use))
            self._log("  Installer exe-icoon: " + str(ico_to_use))
        else:
            self._log("  Installer: GEEN icoon meegegeven aan Nuitka")
        cmd.append(str(stub_path))

        self._log("  Commando: " + " ".join(cmd))
        self._log("")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=_NO_WINDOW,

            startupinfo=_hidden_startupinfo(),
        )

        assert proc.stdout is not None
        for line in proc.stdout:
            self._check_cancel()
            self._log("  " + line.rstrip())

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                "Installer-stub compilatie mislukt "
                "(exit " + str(proc.returncode) + ")"
            )

        built = installer_build / (self.setup_name + ".exe")
        if not built.is_file():
            raise RuntimeError(
                "Installer-exe niet gevonden: " + str(built)
            )

        out_dir = Path(self.output_folder)
        out_dir.mkdir(parents=True, exist_ok=True)
        final = out_dir / (self.setup_name + ".exe")
        if final.exists():
            final.unlink()
        shutil.move(str(built), str(final))

        size_mb = final.stat().st_size / (1024 * 1024)
        self._log("")
        self._log("  -> " + str(final) + " (" +
                  f"{size_mb:.1f}" + " MB)")
        self.progress.emit(100)
        return final

    # === Orchestrator ===

    def run(self):
        work_dir = Path(tempfile.mkdtemp(prefix="pysetup_"))
        self._log("Werk-map: " + str(work_dir))
        self._log("")

        try:
            # Bereid Dravenlock brand-icoon voor (PNG/JPG -> .ico met
            # multi-resolution) - wordt gebruikt voor installer.exe
            # en uninstall.exe.
            if self.brand_logo:
                self._log("Brand-logo naar .ico converteren voor "
                          "installer/uninstaller icoon...")
                self._brand_ico_path = self._make_brand_ico(work_dir)
                self._log("")
            else:
                self._brand_ico_path = None

            app_exe = self._run_nuitka_onefile(work_dir)
            self._check_cancel()
            uninstall_exe = self._build_uninstaller_exe(work_dir)
            self._check_cancel()
            payload_zip = self._create_payload_zip(
                app_exe, uninstall_exe, work_dir
            )
            self._check_cancel()
            stub_path = self._render_stub(payload_zip, work_dir)
            self._check_cancel()
            final = self._compile_stub_to_exe(stub_path, work_dir)

            self._log("")
            self._log("=" * 50)
            self._log("KLAAR")
            self._log("Installer: " + str(final))
            self._log("=" * 50)
            self.finished.emit(True, str(final))

        except Exception as e:
            self._log("")
            self._log("=" * 50)
            self._log("FOUT: " + str(e))
            self._log("=" * 50)
            self.finished.emit(False, str(e))
        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass
