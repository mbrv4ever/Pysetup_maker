"""
core/uninstaller_template.py - Genereert uninstall.py code.

KRITIEK voor veiligheid: de uninstaller verwijdert ALLEEN bestanden
die in install_manifest.txt staan. Zonder dat manifest weigert de
uninstaller alles - zodat een install in C:/Program Files of C:/
NIET kan leiden tot rampzalige uninstall.
"""

UNINSTALLER_TEMPLATE = '''#!/usr/bin/env python3
"""Uninstaller voor __APP_NAME__."""
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator, QLibraryInfo, Qt
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QMessageBox, QDialog, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QWidget,
)
import base64 as _b64


APP_NAME = "__APP_NAME__"

# Brand-logo (ingebakken als base64) voor gebrande dialog. Leeg
# als er geen logo werd meegegeven bij de build.
BRAND_LOGO_B64 = "__BRAND_LOGO_B64__"
BRAND_LOGO_EXT = "__BRAND_LOGO_EXT__"
BRAND_NAME = "Dravenlock Software"


# === Taal-detectie & vertalingen ===
def _detect_lang():
    try:
        lang = QLocale.system().name()
        if lang.startswith("nl"):
            return "nl"
    except Exception:
        pass
    return "en"


_LANG = None


def _lang():
    global _LANG
    if _LANG is None:
        _LANG = _detect_lang()
    return _LANG


I18N = {
    "blocked_title":     {"nl": " - Verwijderen GEBLOKKEERD",
                           "en": " - Removal BLOCKED"},
    "blocked_body":      {"nl": "De uninstaller weigert te draaien "
                                 "op deze locatie:\\n\\n{path}\\n\\n"
                                 "Reden: {reason}\\n\\n"
                                 "Verwijder de bestanden handmatig "
                                 "als je zeker weet dat het veilig is.",
                           "en": "The uninstaller refuses to run at "
                                 "this location:\\n\\n{path}\\n\\n"
                                 "Reason: {reason}\\n\\n"
                                 "Remove the files manually if you "
                                 "are certain it is safe."},
    "no_manifest_title": {"nl": " - Verwijderen niet mogelijk",
                           "en": " - Cannot uninstall"},
    "no_manifest_body":  {"nl": "install_manifest.txt niet gevonden "
                                 "in:\\n\\n{path}\\n\\nZonder dat "
                                 "bestand kan de uninstaller niet "
                                 "veilig verwijderen. Verwijder de "
                                 "map handmatig als je zeker weet "
                                 "dat het goed is.",
                           "en": "install_manifest.txt not found "
                                 "in:\\n\\n{path}\\n\\nWithout that "
                                 "file the uninstaller cannot safely "
                                 "remove. Delete the folder manually "
                                 "if you are certain it is safe."},
    "confirm_title":     {"nl": " - Dravenlock Software",
                           "en": " - Dravenlock Software"},
    "confirm_body":      {"nl": "{app} wordt verwijderd uit:\\n\\n"
                                 "{path}\\n\\n{n} bestanden worden "
                                 "verwijderd. Andere bestanden in "
                                 "de map blijven staan.\\n\\nDoorgaan?",
                           "en": "{app} will be removed from:\\n\\n"
                                 "{path}\\n\\n{n} files will be "
                                 "deleted. Other files in the folder "
                                 "will remain.\\n\\nContinue?"},
    # Geblokkeerde-pad redenen (van _is_dangerous_path)
    "danger_drive":      {"nl": "Dit is een hele drive ({path}). "
                                 "Een uninstaller mag nooit een "
                                 "drive opruimen.",
                           "en": "This is an entire drive ({path}). "
                                 "An uninstaller must never wipe "
                                 "a drive."},
    "danger_system":     {"nl": "Dit is een Windows system-map "
                                 "({path}). Verwijderen kan andere "
                                 "programma's stuk maken.",
                           "en": "This is a Windows system folder "
                                 "({path}). Deleting may break "
                                 "other programs."},
    "danger_name":       {"nl": "De map heet '{name}', niet '{app}'. "
                                 "Dit is waarschijnlijk geen "
                                 "dedicated install-map.",
                           "en": "The folder is named '{name}', not "
                                 "'{app}'. This is likely not a "
                                 "dedicated install folder."},
    "danger_unknown":    {"nl": "Pad kon niet bepaald worden.",
                           "en": "Path could not be determined."},
    # QMessageBox knoppen (Qt's eigen vertalingen werken niet
    # altijd na Nuitka --onefile - we zetten ze handmatig)
    "btn_yes":           {"nl": "Ja",
                           "en": "Yes"},
    "btn_no":            {"nl": "Nee",
                           "en": "No"},
    "btn_ok":            {"nl": "OK",
                           "en": "OK"},
}


def tr(key, **kwargs):
    val = I18N.get(key, {}).get(_lang())
    if val is None:
        val = I18N.get(key, {}).get("en", key)
    if kwargs:
        try:
            val = val.format(**kwargs)
        except Exception:
            pass
    return val


def _install_dir():
    """De map waar deze uninstaller in staat = de install-map."""
    try:
        argv0 = Path(sys.argv[0]).resolve()
        if argv0.is_file():
            return argv0.parent
    except Exception:
        pass
    try:
        return Path(__file__).resolve().parent
    except NameError:
        pass
    return Path.cwd()


def _read_manifest(install_path):
    """
    Lees install_manifest.txt - de lijst met bestanden die de
    installer heeft aangemaakt. Alleen die mogen we verwijderen.

    KRITIEK: zonder manifest weigert de uninstaller alles. Dat
    voorkomt dat bij een install in C:/Program Files of C:/
    de hele map wordt gewist.
    """
    manifest_path = install_path / "install_manifest.txt"
    if not manifest_path.is_file():
        return None
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip()]
    except Exception:
        return None


def _find_desktop():
    """
    Vind het echte Desktop-pad via dezelfde detectie als de
    installer gebruikte. Cruciaal: als de installer het via
    de registry-locatie heeft geplaatst, moeten we DAAR ook
    weer kijken om te verwijderen.
    """
    # 1. Registry Shell Folders (authoritative)
    try:
        import winreg
        bs = chr(92)
        key_path = ("Software" + bs + "Microsoft" + bs + "Windows" + bs
                    + "CurrentVersion" + bs + "Explorer" + bs
                    + "Shell Folders")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            val, _ = winreg.QueryValueEx(k, "Desktop")
            p = Path(val)
            if p.is_dir():
                return p
    except Exception:
        pass

    # 2. USERPROFILE fallbacks
    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile:
        for sub in (
            Path(userprofile) / "Desktop",
            Path(userprofile) / "OneDrive" / "Desktop",
            Path(userprofile) / "OneDrive" / "Bureaublad",
            Path(userprofile) / "Bureaublad",
        ):
            if sub.is_dir():
                return sub

    # 3. PUBLIC Desktop
    public = os.environ.get("PUBLIC", "")
    if public:
        p = Path(public) / "Desktop"
        if p.is_dir():
            return p

    return None


def _find_start_menu():
    """
    Vind het echte Start Menu Programs pad. APPDATA-env kan in
    bepaalde subprocess-contexten leeg zijn, daarom proberen we
    de registry eerst.
    """
    try:
        import winreg
        bs = chr(92)
        key_path = ("Software" + bs + "Microsoft" + bs + "Windows" + bs
                    + "CurrentVersion" + bs + "Explorer" + bs
                    + "Shell Folders")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            val, _ = winreg.QueryValueEx(k, "Programs")
            p = Path(val)
            if p.is_dir():
                return p
    except Exception:
        pass

    appdata = os.environ.get("APPDATA", "")
    if appdata and Path(appdata).is_absolute():
        p = (Path(appdata) / "Microsoft" / "Windows"
             / "Start Menu" / "Programs")
        if p.is_dir():
            return p
    return None


def _remove_shortcuts():
    """Verwijder start-menu en desktop snelkoppelingen."""
    # Start-menu: hele app-map weghalen
    try:
        sm_parent = _find_start_menu()
        if sm_parent is not None:
            sm = sm_parent / APP_NAME
            # Veiligheidscheck: pad moet absoluut zijn en de
            # naam moet matchen, anders rmtree we per ongeluk
            # iets anders.
            if sm.is_absolute() and sm.is_dir():
                shutil.rmtree(sm, ignore_errors=True)
    except Exception:
        pass

    # Desktop: probeer ZOWEL het registry-pad (waar de installer
    # 'm plaatste) ALS de fallback paden, voor het geval.
    paths_to_try = set()

    d = _find_desktop()
    if d is not None:
        paths_to_try.add(d)

    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile:
        for sub in (
            Path(userprofile) / "Desktop",
            Path(userprofile) / "OneDrive" / "Desktop",
            Path(userprofile) / "OneDrive" / "Bureaublad",
            Path(userprofile) / "Bureaublad",
        ):
            paths_to_try.add(sub)

    for d in paths_to_try:
        try:
            link = d / (APP_NAME + ".lnk")
            if link.exists():
                try:
                    link.unlink()
                except Exception:
                    pass
        except Exception:
            pass


def _delete_key_recursive(root, sub_key):
    """
    Verwijder een registry-key inclusief alle sub-keys.
    winreg.DeleteKey() faalt op keys met children, dus we moeten
    recursief afdalen.
    """
    import winreg
    try:
        with winreg.OpenKey(root, sub_key, 0,
                             winreg.KEY_ALL_ACCESS) as k:
            # Verzamel eerst alle sub-key namen (kan niet itereren
            # tijdens delete - index verschuift)
            sub_names = []
            try:
                i = 0
                while True:
                    sub_names.append(winreg.EnumKey(k, i))
                    i += 1
            except OSError:
                pass

            for name in sub_names:
                _delete_key_recursive(root, sub_key + chr(92) + name)

        # Nu de key zelf, nu 'ie leeg is
        winreg.DeleteKey(root, sub_key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def _remove_registry():
    """
    Verwijder alle registry-sporen van de app.

    We ruimen op:
      - HKCU / Software / Microsoft / Windows / CurrentVersion /
        Uninstall / APP_NAME   (de "Apps en functies"-vermelding)
      - HKCU / Software / APP_NAME
        (eventuele user-settings die de app zelf opslaat)

    Beide worden recursief verwijderd inclusief sub-keys.
    """
    try:
        import winreg
        bs = chr(92)

        # 1. Uninstall-entry voor "Apps en functies"
        uninstall_key = ("Software" + bs + "Microsoft" + bs
                         + "Windows" + bs + "CurrentVersion" + bs
                         + "Uninstall" + bs + APP_NAME)
        _delete_key_recursive(winreg.HKEY_CURRENT_USER, uninstall_key)

        # 2. App's eigen settings-key (als de app er een aanmaakte)
        app_key = "Software" + bs + APP_NAME
        _delete_key_recursive(winreg.HKEY_CURRENT_USER, app_key)

    except Exception:
        pass


def _do_uninstall(install_path, manifest):
    """
    Verwijder ALLEEN de bestanden uit manifest + uninstaller +
    install-map ALS leeg na verwijderen. Veilig voor C:/Program Files.
    """
    _remove_shortcuts()
    _remove_registry()

    try:
        os.chdir(tempfile.gettempdir())
    except Exception:
        pass

    install_str = str(install_path)

    # Bouw een .bat script. Eerder probeerden we PowerShell maar
    # die wordt op veel systemen geblokkeerd door ExecutionPolicy/
    # Defender en faalde dan stil. Batch is universeel.
    #
    # Het 'timeout' commando opent helaas een console, dus we
    # gebruiken de ouwe truc 'ping 127.0.0.1 -n 4' wat 3 seconden
    # vertraging geeft zonder venster.
    bat = tempfile.NamedTemporaryFile(
        mode="w", suffix=".bat", delete=False, encoding="utf-8"
    )

    bat.write("@echo off\\r\\n")
    # Wacht 3 seconden zonder venster (ping ipv timeout)
    bat.write("ping 127.0.0.1 -n 4 > nul\\r\\n")

    # Verwijder elk bestand uit het manifest
    for rel_path in manifest:
        # Veiligheidsfilter: skip parent-traversal en absolute paden
        if ".." in rel_path:
            continue
        if rel_path.startswith(("/", "\\\\")):
            continue
        if len(rel_path) >= 2 and rel_path[1] == ":":
            continue
        full = install_str + "\\\\" + rel_path.replace("/", "\\\\")
        bat.write('del /F /Q "' + full + '" >nul 2>&1\\r\\n')

    # Uninstaller exe + manifest (niet in het manifest zelf opgenomen
    # om recursie te voorkomen)
    bat.write('del /F /Q "' + install_str
              + '\\\\uninstall.exe" >nul 2>&1\\r\\n')
    bat.write('del /F /Q "' + install_str
              + '\\\\install_manifest.txt" >nul 2>&1\\r\\n')

    # Lege sub-mappen opruimen (bottom-up via /S, alleen lege dirs)
    bat.write('for /f "delims=" %%d in (\\'dir /AD /B /S "'
              + install_str + '" 2^>nul ^| sort /R\\') '
              'do @rmdir "%%d" >nul 2>&1\\r\\n')

    # Install-map zelf - rmdir ZONDER /S, faalt netjes bij niet-lege
    # mappen zodat we niet per ongeluk extra bestanden wegharken
    bat.write('cd /d "%TEMP%"\\r\\n')
    bat.write('rmdir "' + install_str + '" >nul 2>&1\\r\\n')

    # Ruim ALLE oude Nuitka uitpak-tempdirs van zowel installer als
    # uninstaller op. Deze stonden vroeger in %LOCALAPPDATA% en
    # konden honderden MB groot worden. Vanaf nu staan ze in
    # %TEMP% met PID-suffix - opruimen voor de zekerheid.
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        # Oude locatie: %LOCALAPPDATA%/<APP_NAME>/...
        old_nuitka_cache = appdata + "\\\\" + APP_NAME
        bat.write('rmdir /S /Q "' + old_nuitka_cache
                  + '" >nul 2>&1\\r\\n')

    # Nieuwe locatie: %TEMP%/<APP_NAME>-* (wildcard onmogelijk
    # in batch, dus we listen alles op met for-loop)
    bat.write('for /d %%d in ("%TEMP%\\\\' + APP_NAME
              + '-*") do @rmdir /S /Q "%%d" >nul 2>&1\\r\\n')
    bat.write('for /d %%d in ("%TEMP%\\\\' + APP_NAME
              + '*Installer*") do @rmdir /S /Q "%%d" >nul 2>&1\\r\\n')

    # Zelf-cleanup van de .bat (en de .vbs launcher die we hieronder
    # genereren) - placeholders die we na vbs-creatie invullen.
    bat.write('del "__VBS_PATH__" >nul 2>&1\\r\\n')
    bat.write('del "%~f0" >nul 2>&1\\r\\n')
    bat.close()

    # Trick voor echt-onzichtbaar starten van een .bat:
    # Een VBScript-wrapper met WScript.Shell.Run(..., 0, False) start
    # de batch met windowStyle=Hidden en bWaitOnReturn=False. Dit
    # is de enige manier die onder Windows 11 GEEN flits geeft -
    # cmd.exe direct via subprocess.Popen flitst altijd kort,
    # ondanks SW_HIDE en alle creationflags.
    vbs = tempfile.NamedTemporaryFile(
        mode="w", suffix=".vbs", delete=False, encoding="utf-8"
    )
    # Escape het bat-pad voor VBScript ("-quoting)
    bat_for_vbs = bat.name.replace('"', '""')
    vbs.write(
        'Set s = CreateObject("WScript.Shell")\\r\\n'
        + 's.Run """' + bat_for_vbs + '""", 0, False\\r\\n'
    )
    vbs.close()

    # Vul nu het VBS-pad in de batch in (cleanup van de vbs)
    with open(bat.name, "r", encoding="utf-8") as bf:
        bat_content = bf.read()
    bat_content = bat_content.replace("__VBS_PATH__", vbs.name)
    with open(bat.name, "w", encoding="utf-8") as bf:
        bf.write(bat_content)

    # wscript.exe is een GUI-process (geen console) en runt het
    # vbs onzichtbaar. Daarna stopt 'ie - de batch loopt door.
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # SW_HIDE

    subprocess.Popen(
        ["wscript.exe", vbs.name],
        creationflags=(0x08000000 | 0x00000008 | 0x00000200),
        close_fds=True,
        startupinfo=startupinfo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


def _is_dangerous_path(p):
    """
    Returns een (str) waarschuwing als het pad gevaarlijk is om
    te verwijderen, of None als 't OK is.

    Gevaarlijke paden zijn paden die NOOIT verwijderd zouden mogen
    worden, omdat ze ook andere programma's/Windows-bestanden
    bevatten of een hele drive zijn.
    """
    try:
        p = Path(p).resolve()
    except Exception:
        return tr("danger_unknown")
    s = str(p)
    s_low = s.lower().rstrip("\\\\/").rstrip("\\\\")

    # Een drive-root: "C:" of "C:\\\\"
    if len(s_low) <= 3:
        return tr("danger_drive", path=s)

    # Bekende Windows-system / Program Files locaties
    forbidden = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                "SystemRoot", "windir"):
        v = os.environ.get(env, "")
        if v:
            forbidden.append(v.lower().rstrip("\\\\/"))

    for f in forbidden:
        if s_low == f:
            return tr("danger_system", path=s)

    # Het pad MOET de app-naam bevatten in de laatste component;
    # anders weten we niet zeker dat dit een dedicated install-map is.
    if p.name.lower() != APP_NAME.lower():
        return tr("danger_name", name=p.name, app=APP_NAME)

    return None


class _BrandedConfirmDialog(QDialog):
    """
    Gebrande uninstall-bevestiging met Dravenlock-banner links
    (logo) en tekst rechts. Vervangt de kale QMessageBox.question
    zodat de gebruiker altijd het Dravenlock-merk ziet bij
    verwijderen.
    """

    # Kleuren (zelfde palette als installer)
    BG_APP = "#111114"
    BG_CARD = "#1a1a20"
    BORDER = "#2a2a32"
    TEXT = "#e8eaef"
    TEXT_DIM = "#a0a4ad"
    TEXT_ON_ACCENT = "#111114"
    ACCENT = "#c0c8d4"
    ACCENT_HOVER = "#d4dae3"
    ACCENT_PRESSED = "#a8b0bc"

    def __init__(self, install_path, manifest):
        super().__init__()
        self.confirmed = False

        self.setWindowTitle(APP_NAME + tr("confirm_title"))
        self.setMinimumSize(640, 320)
        self.setStyleSheet(
            "QDialog { background: " + self.BG_APP + "; } "
            "QWidget { color: " + self.TEXT + "; "
            "background: transparent; } "
            "QLabel { color: " + self.TEXT + "; "
            "background: transparent; } "
            "QPushButton { background: " + self.ACCENT + "; "
            "color: " + self.TEXT_ON_ACCENT + "; border: none; "
            "border-radius: 6px; padding: 8px 22px; "
            "font-weight: bold; min-width: 90px; "
            "font-size: 11pt; } "
            "QPushButton:hover { background: " + self.ACCENT_HOVER + "; "
            "color: " + self.TEXT_ON_ACCENT + "; } "
            "QPushButton:pressed { background: " + self.ACCENT_PRESSED
            + "; color: " + self.TEXT_ON_ACCENT + "; } "
            "QPushButton:focus { background: " + self.ACCENT + "; "
            "color: " + self.TEXT_ON_ACCENT + "; outline: none; } "
            "QPushButton:default { background: " + self.ACCENT + "; "
            "color: " + self.TEXT_ON_ACCENT + "; }"
        )

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # Banner links (180px, volle hoogte, zwart)
        banner = QWidget()
        banner.setFixedWidth(180)
        banner.setStyleSheet(
            "background: #000000; "
            "border-right: 1px solid " + self.BORDER + ";"
        )
        bv = QVBoxLayout(banner)
        bv.setContentsMargins(16, 24, 16, 24)
        bv.addStretch()
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setStyleSheet("background: transparent;")

        # Probeer de ingebakken brand-logo te laden
        if BRAND_LOGO_B64:
            try:
                pix = QPixmap()
                pix.loadFromData(_b64.b64decode(BRAND_LOGO_B64))
                if not pix.isNull():
                    scaled = pix.scaled(
                        140, 140,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    logo_lbl.setPixmap(scaled)
                else:
                    logo_lbl.setText(BRAND_NAME)
                    logo_lbl.setStyleSheet(
                        "background: transparent; color: "
                        + self.ACCENT + "; "
                        "font-size: 12pt; font-weight: bold;"
                    )
            except Exception:
                logo_lbl.setText(BRAND_NAME)
                logo_lbl.setStyleSheet(
                    "background: transparent; color: "
                    + self.ACCENT + "; "
                    "font-size: 12pt; font-weight: bold;"
                )
        else:
            logo_lbl.setText(BRAND_NAME)
            logo_lbl.setStyleSheet(
                "background: transparent; color: " + self.ACCENT + "; "
                "font-size: 12pt; font-weight: bold;"
            )
        logo_lbl.setWordWrap(True)
        bv.addWidget(logo_lbl)
        bv.addStretch()
        h.addWidget(banner)

        # Rechts: header + body + knoppen
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(28, 22, 28, 22)
        rv.setSpacing(14)

        # Header: app-naam + Dravenlock Software
        header = QHBoxLayout()
        header.setSpacing(12)
        app_lbl = QLabel(APP_NAME)
        app_lbl.setStyleSheet(
            "background: transparent; color: " + self.TEXT + "; "
            "font-size: 18pt; font-weight: bold;"
        )
        header.addWidget(app_lbl)
        brand_lbl = QLabel(BRAND_NAME)
        brand_lbl.setStyleSheet(
            "background: transparent; color: " + self.TEXT_DIM + "; "
            "font-size: 10pt;"
        )
        brand_lbl.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        header.addWidget(brand_lbl, stretch=1)
        rv.addLayout(header)

        # Lijntje
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: " + self.BORDER + ";")
        rv.addWidget(sep)

        # Body
        body = QLabel(tr("confirm_body", app=APP_NAME,
                         path=str(install_path), n=len(manifest)))
        body.setWordWrap(True)
        body.setStyleSheet(
            "background: transparent; color: " + self.TEXT + "; "
            "font-size: 11pt;"
        )
        rv.addWidget(body)
        rv.addStretch()

        # Knoppen rechts onder
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        no_btn = QPushButton(tr("btn_no"))
        no_btn.clicked.connect(self.reject)
        btn_row.addWidget(no_btn)

        yes_btn = QPushButton(tr("btn_yes"))
        yes_btn.clicked.connect(self._on_yes)
        btn_row.addWidget(yes_btn)

        # Default: Nee, om per ongeluk verwijderen te voorkomen
        no_btn.setDefault(True)
        no_btn.setFocus()

        rv.addLayout(btn_row)
        h.addWidget(right, stretch=1)

    def _on_yes(self):
        self.confirmed = True
        self.accept()


def main():
    app = QApplication(sys.argv)

    # Qt's eigen vertalingen voor de standaard QMessageBox-knoppen
    # (Yes/No, OK/Cancel) - vertaalt zich naar gebruiker's systeemtaal
    try:
        translator = QTranslator()
        locale = QLocale.system()
        translations_path = QLibraryInfo.path(
            QLibraryInfo.TranslationsPath
        )
        if translator.load(locale, "qt", "_", translations_path):
            app.installTranslator(translator)
        translator2 = QTranslator()
        if translator2.load(locale, "qtbase", "_", translations_path):
            app.installTranslator(translator2)
    except Exception:
        pass

    app.setStyleSheet(
        "QMessageBox { background: #1a1a20; } "
        "QMessageBox QLabel { color: #e8eaef; "
        "font-size: 11pt; min-width: 320px; } "
        "QPushButton { background: #c0c8d4; color: #111114; "
        "border: none; border-radius: 6px; padding: 7px 18px; "
        "font-weight: bold; min-width: 80px; } "
        "QPushButton:hover { background: #d4dae3; color: #111114; } "
        "QPushButton:pressed { background: #a8b0bc; color: #111114; } "
        "QPushButton:focus { background: #c0c8d4; color: #111114; "
        "outline: none; } "
        "QPushButton:default { background: #c0c8d4; color: #111114; }"
    )

    install_path = _install_dir()

    # VEILIGHEIDSCHECK: weiger uninstall in gevaarlijke paden,
    # zoals C:\\ of C:\\Program Files. Dit zou anders systeem-
    # bestanden of andere programma's kunnen verwijderen.
    danger = _is_dangerous_path(install_path)
    if danger is not None:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(APP_NAME + tr("blocked_title"))
        msg.setText(tr("blocked_body", path=str(install_path),
                       reason=danger))
        ok_btn = msg.addButton(tr("btn_ok"), QMessageBox.AcceptRole)
        msg.setDefaultButton(ok_btn)
        msg.exec()
        return

    manifest = _read_manifest(install_path)

    if manifest is None:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(APP_NAME + tr("no_manifest_title"))
        msg.setText(tr("no_manifest_body", path=str(install_path)))
        ok_btn = msg.addButton(tr("btn_ok"), QMessageBox.AcceptRole)
        msg.setDefaultButton(ok_btn)
        msg.exec()
        return

    # Bouw een eigen QMessageBox zodat de Yes/No knoppen
    # gegarandeerd in de juiste taal staan (Qt's stock-vertalingen
    # werken niet betrouwbaar na Nuitka --onefile).
    # Gebrande Dravenlock-confirm dialog ipv kale QMessageBox.
    # Toont banner-logo + app-naam + body + Ja/Nee knoppen.
    dlg = _BrandedConfirmDialog(install_path, manifest)
    dlg.exec()

    if not dlg.confirmed:
        return

    _do_uninstall(install_path, manifest)
    os._exit(0)


if __name__ == "__main__":
    main()
'''


def render_uninstaller(app_name: str,
                       brand_logo_b64: str = "",
                       brand_logo_ext: str = "") -> str:
    """Vul de template in met app-naam en optioneel brand-logo."""
    return (UNINSTALLER_TEMPLATE
            .replace("__APP_NAME__", app_name)
            .replace("__BRAND_LOGO_B64__", brand_logo_b64)
            .replace("__BRAND_LOGO_EXT__", brand_logo_ext))
