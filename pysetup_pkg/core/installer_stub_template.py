"""
core/installer_stub_template.py - De Python-code die wordt
gecompileerd tot de uiteindelijke installer-exe.

Deze stub bevat:
  - De payload (base64-gecodeerde zip) met de app + extras
  - PySide6 wizard-UI in Dravenlock-stijl
  - Uitpak-logica
  - Uninstaller-generator
  - Windows registratie (start-menu, desktop, Programma's en
    onderdelen)

Placeholders die ingevuld worden via .replace():
  __APP_DISPLAY_NAME__  -> bv. "MijnTool"
  __APP_EXE_NAME__      -> bv. "mijntool.exe"
  __PAYLOAD_B64__       -> de base64-string van de payload-zip
  __UNINSTALLER_PY__    -> de inhoud van de uninstaller (als string)
"""

INSTALLER_STUB_TEMPLATE = '''#!/usr/bin/env python3
"""Self-extracting installer voor __APP_DISPLAY_NAME__."""
import base64
import os
import sys
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtCore import (
    Qt, QThread, Signal, QObject, QLocale, QTranslator, QLibraryInfo
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QWizard, QWizardPage, QLabel, QLineEdit,
    QPushButton, QHBoxLayout, QVBoxLayout, QFileDialog,
    QCheckBox, QProgressBar, QMessageBox, QPlainTextEdit,
    QWidget,
)
from PySide6.QtGui import QPixmap


APP_DISPLAY_NAME = "__APP_DISPLAY_NAME__"
APP_EXE_NAME = "__APP_EXE_NAME__"

# Payload (base64-gecodeerde zip met app/<exe>, app/uninstall.exe,
# extras/, meta/icon.ico)
PAYLOAD_B64 = """\\
__PAYLOAD_B64__"""


# === Dravenlock donker thema ===
# === Dravenlock donker thema (zilver op antraciet) ===
ACCENT = "#c0c8d4"
ACCENT_HOVER = "#d4dae3"
ACCENT_PRESSED = "#a8b0bc"
ACCENT_DIM = "#383a42"
BG_APP = "#111114"
BG_CARD = "#1a1a20"
BG_INPUT = "#0a0a0c"
BG_CONSOLE = "#050507"
TEXT = "#e8eaef"
TEXT_DIM = "#a0a4ad"
TEXT_ON_ACCENT = "#111114"
BORDER = "#2a2a32"

# Merknaam - consistent over Browser, SysCare, en alle Dravenlock-apps.
# Wordt rechts naast de app-naam getoond in elke installer.
BRAND_NAME = "Dravenlock Software"


# === Taal-detectie & vertalingen ===
# Detecteer systeemtaal via QLocale. Nederlands krijgt NL-teksten,
# alle andere talen krijgen Engels (default/fallback).

def _detect_lang():
    """Returns 'nl' of 'en' op basis van systeemtaal."""
    try:
        lang = QLocale.system().name()  # bv. 'nl_NL', 'en_US'
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


# Alle UI-strings. Voor elke key: nl + en vertaling.
I18N = {
    # Wizard window-titel
    "installer_title":        {"nl": " - Installatie",
                                "en": " - Setup"},
    # Welkom-pagina
    "welcome":                {"nl": "Welkom",
                                "en": "Welcome"},
    "welcome_body":           {"nl": "Deze wizard zal {app} op je "
                                      "computer installeren.\\n\\n"
                                      "Klik op 'Volgende' om door te "
                                      "gaan met de installatie, of op "
                                      "'Annuleren' om af te breken.",
                                "en": "This wizard will install {app} "
                                      "on your computer.\\n\\nClick "
                                      "'Next' to continue, or "
                                      "'Cancel' to abort."},
    # Pad-pagina
    "path_title":             {"nl": "Installatiemap kiezen",
                                "en": "Choose install location"},
    "path_subtitle":          {"nl": "Kies de bovenliggende map. "
                                      "Er wordt automatisch een "
                                      "submap '{app}' aangemaakt.",
                                "en": "Choose the parent folder. A "
                                      "subfolder '{app}' will be "
                                      "created automatically."},
    "parent_folder":          {"nl": "Bovenliggende map:",
                                "en": "Parent folder:"},
    "browse":                 {"nl": "Bladeren...",
                                "en": "Browse..."},
    "install_to":             {"nl": "Installatie naar:  ",
                                "en": "Install to:  "},
    "desktop_shortcut":       {"nl": "Snelkoppeling op bureaublad",
                                "en": "Create desktop shortcut"},
    "dialog_parent":          {"nl": "Bovenliggende map",
                                "en": "Parent folder"},
    # Install-pagina
    "install_title":          {"nl": "Installeren",
                                "en": "Installing"},
    "install_subtitle":       {"nl": "Bezig met installeren...",
                                "en": "Installing..."},
    "start_install":          {"nl": "Installatie starten...",
                                "en": "Starting installation..."},
    "done_install":           {"nl": "Klaar.",
                                "en": "Done."},
    "error_prefix":           {"nl": "FOUT: ",
                                "en": "ERROR: "},
    # Done-pagina
    "done":                   {"nl": "Klaar",
                                "en": "Done"},
    "done_body":              {"nl": "{app} is succesvol "
                                      "geinstalleerd.\\n\\nDe app is "
                                      "te vinden in het start-menu "
                                      "en (indien gekozen) op het "
                                      "bureaublad.",
                                "en": "{app} has been successfully "
                                      "installed.\\n\\nThe app can "
                                      "be found in the start menu "
                                      "and (if chosen) on the "
                                      "desktop."},
    # Logs in install-progress
    "extract_to":             {"nl": "Uitpakken naar ",
                                "en": "Extracting to "},
    "writing_manifest":       {"nl": "Manifest schrijven...",
                                "en": "Writing manifest..."},
    "files_in_manifest":      {"nl": " bestanden in manifest",
                                "en": " files in manifest"},
    "shortcuts_register":     {"nl": "Snelkoppelingen + registratie...",
                                "en": "Shortcuts + registration..."},
    # Wizard knoppen (Qt's eigen vertalingen werken niet altijd na
    # Nuitka --onefile - we zetten ze handmatig via setButtonText)
    "btn_next":               {"nl": "Volgende >",
                                "en": "Next >"},
    "btn_back":               {"nl": "< Vorige",
                                "en": "< Back"},
    "btn_cancel":             {"nl": "Annuleren",
                                "en": "Cancel"},
    "btn_finish":             {"nl": "Voltooien",
                                "en": "Finish"},
    "btn_yes":                {"nl": "Ja",
                                "en": "Yes"},
    "btn_no":                 {"nl": "Nee",
                                "en": "No"},
    "btn_ok":                 {"nl": "OK",
                                "en": "OK"},
    "error_title":            {"nl": "Fout",
                                "en": "Error"},
    "install_failed":         {"nl": "Installatie mislukt:\\n\\n",
                                "en": "Installation failed:\\n\\n"},
}


def tr(key, **kwargs):
    """
    Vertaal een key. Geeft Engels terug als de key niet in NL staat.
    Met kwargs: format-strings, bv. tr('welcome_body', app='SysCare').
    """
    val = I18N.get(key, {}).get(_lang())
    if val is None:
        val = I18N.get(key, {}).get("en", key)
    if kwargs:
        try:
            val = val.format(**kwargs)
        except Exception:
            pass
    return val


# === Worker voor uitpakken op een thread ===

class ExtractWorker(QObject):
    progress = Signal(int)
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, install_dir, make_desktop_shortcut):
        super().__init__()
        self.install_dir = install_dir
        self.make_desktop_shortcut = make_desktop_shortcut

    def run(self):
        try:
            install_path = Path(self.install_dir)
            install_path.mkdir(parents=True, exist_ok=True)

            self.log.emit("Payload decoderen...")
            self.progress.emit(2)
            payload = base64.b64decode(PAYLOAD_B64)

            with tempfile.NamedTemporaryFile(
                    suffix=".zip", delete=False) as tmp:
                tmp.write(payload)
                tmp_zip = tmp.name

            self.log.emit(tr("extract_to") + str(install_path) + "...")
            extracted_files = []
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                names = zf.namelist()
                total = max(len(names), 1)
                for i, name in enumerate(names):
                    if name.endswith("/"):
                        continue
                    if name.startswith("app/"):
                        rel = name[4:]
                        target = install_path / rel
                    elif name.startswith("extras/"):
                        rel = name[7:]
                        target = install_path / rel
                    elif name.startswith("meta/"):
                        rel = Path(name).name
                        target = install_path / rel
                    else:
                        rel = name
                        target = install_path / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src:
                        with open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    extracted_files.append(rel)
                    if i % 5 == 0:
                        self.progress.emit(
                            min(int(i / total * 90) + 2, 92)
                        )

            try:
                os.unlink(tmp_zip)
            except Exception:
                pass

            # KRITIEK: schrijf install_manifest.txt met de lijst
            # van alle uitgepakte bestanden. De uninstaller gebruikt
            # die om ALLEEN onze eigen bestanden te verwijderen -
            # zo kan een install in C:/Program Files niet leiden
            # tot een rampzalige uninstall.
            self.log.emit(tr("writing_manifest"))
            manifest_path = install_path / "install_manifest.txt"
            manifest_path.write_text(
                "\\n".join(extracted_files), encoding="utf-8"
            )
            self.log.emit("  " + str(len(extracted_files))
                          + tr("files_in_manifest"))

            self.log.emit(tr("shortcuts_register"))
            self.progress.emit(95)
            _register_with_windows(
                install_path, self.make_desktop_shortcut,
                log_func=self.log.emit
            )

            self.progress.emit(100)
            self.log.emit(tr("done_install"))
            self.finished.emit(True, str(install_path))

        except Exception as e:
            self.finished.emit(False, str(e))


def _create_shortcut(lnk_path, target_exe, icon_path, working_dir):
    """
    Maak een Windows .lnk via Win32 IShellLink COM-interface,
    rechtstreeks aangeroepen met ctypes.

    Geen child-process, geen console-flits, synchroon, geen
    quoting/escaping problemen.
    """
    try:
        import ctypes
        from ctypes import (
            c_void_p, c_wchar_p, c_int, c_byte, c_ulong,
            POINTER, byref, Structure, WINFUNCTYPE
        )

        ole32 = ctypes.windll.ole32

        # CoInitializeEx met COINIT_APARTMENTTHREADED (=2)
        ole32.CoInitializeEx.argtypes = [c_void_p, c_ulong]
        ole32.CoInitializeEx.restype = c_int
        ole32.CoInitializeEx(None, 2)

        try:
            class GUID(Structure):
                _fields_ = [
                    ("Data1", c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", c_byte * 8),
                ]

            def _guid(d1, d2, d3, d4_bytes):
                g = GUID()
                g.Data1 = d1
                g.Data2 = d2
                g.Data3 = d3
                for i, b in enumerate(d4_bytes):
                    g.Data4[i] = b
                return g

            # CLSID_ShellLink = {00021401-0000-0000-C000-000000000046}
            clsid = _guid(
                0x00021401, 0x0000, 0x0000,
                [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46]
            )
            # IID_IShellLinkW = {000214F9-0000-0000-C000-000000000046}
            iid_sl = _guid(
                0x000214F9, 0x0000, 0x0000,
                [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46]
            )
            # IID_IPersistFile = {0000010B-0000-0000-C000-000000000046}
            iid_pf = _guid(
                0x0000010B, 0x0000, 0x0000,
                [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46]
            )

            CLSCTX_INPROC_SERVER = 0x1

            ole32.CoCreateInstance.argtypes = [
                POINTER(GUID), c_void_p, c_ulong,
                POINTER(GUID), POINTER(c_void_p)
            ]
            ole32.CoCreateInstance.restype = c_int

            ppv = c_void_p()
            hr = ole32.CoCreateInstance(
                byref(clsid), None, CLSCTX_INPROC_SERVER,
                byref(iid_sl), byref(ppv)
            )
            if hr != 0 or not ppv.value:
                print("CoCreateInstance fout: HRESULT=" + hex(hr))
                return False

            # Helper: vtable-functiepointer voor een COM-methode
            def vtbl_fn(this_ptr, index, *argtypes):
                vtable = ctypes.cast(
                    ctypes.cast(this_ptr, POINTER(c_void_p))[0],
                    POINTER(c_void_p)
                )
                fn_ptr = vtable[index]
                proto = WINFUNCTYPE(c_int, c_void_p, *argtypes)
                return proto(fn_ptr)

            try:
                # SetPath - vtable index 20
                set_path = vtbl_fn(ppv, 20, c_wchar_p)
                hr = set_path(ppv, str(target_exe))
                if hr != 0:
                    print("SetPath fout: HRESULT=" + hex(hr))
                    return False

                # SetWorkingDirectory - index 9
                set_wd = vtbl_fn(ppv, 9, c_wchar_p)
                set_wd(ppv, str(working_dir))

                # SetIconLocation - index 17 (path + index int)
                set_icon = vtbl_fn(ppv, 17, c_wchar_p, c_int)
                set_icon(ppv, str(icon_path), 0)

                # QueryInterface naar IPersistFile - index 0
                qi = vtbl_fn(ppv, 0, POINTER(GUID), POINTER(c_void_p))
                ppf = c_void_p()
                hr = qi(ppv, byref(iid_pf), byref(ppf))
                if hr != 0 or not ppf.value:
                    print("QI(IPersistFile) fout: HRESULT=" + hex(hr))
                    return False

                try:
                    # IPersistFile::Save - vtable index 6
                    save_fn = vtbl_fn(ppf, 6, c_wchar_p, c_int)
                    hr = save_fn(ppf, str(lnk_path), 1)
                    if hr != 0:
                        print("IPersistFile::Save fout: HRESULT="
                              + hex(hr))
                        return False
                finally:
                    # IPersistFile::Release - index 2
                    release_pf = vtbl_fn(ppf, 2)
                    release_pf(ppf)

            finally:
                # IShellLink::Release - index 2
                release_sl = vtbl_fn(ppv, 2)
                release_sl(ppv)

            return Path(lnk_path).exists()

        finally:
            ole32.CoUninitialize()

    except Exception as e:
        print("shortcut exception: " + str(e))
        import traceback
        traceback.print_exc()
        return False


def _find_start_menu():
    """
    Vind het echte Start Menu Programs pad. Net als bij Desktop
    gebruiken we de registry als authoritative source - APPDATA
    is niet altijd betrouwbaar (kan leeg zijn in bepaalde
    subprocess contexten, met als gevolg dat Path("") resulteert
    in de current working directory!).
    """
    # 1. Registry Shell Folders -> "Programs" key
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
                return p, "registry Shell Folders/Programs"
    except Exception as e:
        print("start menu registry lookup faalde:", e)

    # 2. APPDATA fallback - maar valideer dat 't ABSOLUUT pad is!
    appdata = os.environ.get("APPDATA", "")
    if appdata and Path(appdata).is_absolute():
        p = (Path(appdata) / "Microsoft" / "Windows"
             / "Start Menu" / "Programs")
        if p.is_dir():
            return p, "APPDATA fallback"

    # 3. USERPROFILE fallback
    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile and Path(userprofile).is_absolute():
        p = (Path(userprofile) / "AppData" / "Roaming" / "Microsoft"
             / "Windows" / "Start Menu" / "Programs")
        if p.is_dir():
            return p, "USERPROFILE fallback"

    return None, None


def _find_desktop():
    """
    Vind het echte Desktop-pad. Op moderne Windows met OneDrive
    is dit NIET USERPROFILE/Desktop maar bv. een OneDrive-pad.

    Authoritative source: HKCU registry "Shell Folders" -> Desktop.
    Daarna fallbacks via USERPROFILE.
    """
    # 1. Registry (de echte locatie zoals Windows zelf 'm kent)
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
                return p, "registry Shell Folders"
    except Exception as e:
        print("desktop registry lookup faalde:", e)

    # 2. USERPROFILE fallbacks
    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile:
        for name, sub in [
            ("USERPROFILE/Desktop", Path(userprofile) / "Desktop"),
            ("USERPROFILE/OneDrive/Desktop",
             Path(userprofile) / "OneDrive" / "Desktop"),
            ("USERPROFILE/OneDrive/Bureaublad",
             Path(userprofile) / "OneDrive" / "Bureaublad"),
            ("USERPROFILE/Bureaublad",
             Path(userprofile) / "Bureaublad"),
        ]:
            if sub.is_dir():
                return sub, name

    # 3. PUBLIC Desktop (laatste redmiddel - alle gebruikers)
    public = os.environ.get("PUBLIC", "")
    if public:
        p = Path(public) / "Desktop"
        if p.is_dir():
            return p, "PUBLIC/Desktop"

    return None, None


def _register_with_windows(install_path, make_desktop_shortcut,
                            log_func=None):
    """Start-menu + desktop shortcuts + uninstall-registry."""
    def _log(msg):
        if log_func:
            try:
                log_func(msg)
            except Exception:
                pass
        print(msg)

    exe_path = install_path / APP_EXE_NAME
    icon_path = install_path / "icon.ico"
    icon_for_reg = (str(icon_path) if icon_path.exists()
                    else str(exe_path))

    # Start-menu snelkoppeling - via registry-helper, NIET via
    # rauwe os.environ["APPDATA"] (die kan leeg zijn waardoor
    # Path("") = cwd → snelkoppeling kwam in de verkeerde map!).
    sm_parent, sm_source = _find_start_menu()
    if sm_parent is None:
        _log("Start-menu locatie NIET gevonden, snelkoppeling "
             "wordt overgeslagen.")
    else:
        _log("Start-menu gevonden via: " + sm_source +
             "  -> " + str(sm_parent))
        start_menu = sm_parent / APP_DISPLAY_NAME
        # Veiligheidscheck: het pad MOET absoluut zijn en MOET
        # binnen de Roaming-tree zitten (anders maken we mappen
        # op een rare plek aan).
        if not start_menu.is_absolute():
            _log("Start-menu pad is niet absoluut, overgeslagen: "
                 + str(start_menu))
        else:
            start_menu.mkdir(parents=True, exist_ok=True)
            sm_link = start_menu / (APP_DISPLAY_NAME + ".lnk")
            sm_ok = _create_shortcut(sm_link, exe_path, icon_for_reg,
                                      install_path)
            _log("Start-menu shortcut: " +
                 ("OK" if sm_ok else "MISLUKT") +
                 "  " + str(sm_link))

    # Desktop snelkoppeling (indien gewenst)
    if make_desktop_shortcut:
        desktop, source = _find_desktop()
        if desktop is not None:
            _log("Desktop gevonden via: " + source +
                 "  -> " + str(desktop))
            dt_link = desktop / (APP_DISPLAY_NAME + ".lnk")
            dt_ok = _create_shortcut(dt_link, exe_path, icon_for_reg,
                                       install_path)
            _log("Desktop shortcut: " +
                 ("OK" if dt_ok else "MISLUKT") + "  " + str(dt_link))
        else:
            _log("Desktop NIET gevonden (registry+USERPROFILE+PUBLIC "
                 "allemaal niets opgeleverd). Geen desktop-shortcut.")

    # Registry-entry voor 'Programma's en onderdelen'
    try:
        import winreg
        bs = chr(92)
        key_path = ("Software" + bs + "Microsoft" + bs + "Windows" + bs
                    + "CurrentVersion" + bs + "Uninstall" + bs
                    + APP_DISPLAY_NAME)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              key_path) as k:
            uninstall_exe = install_path / "uninstall.exe"
            winreg.SetValueEx(k, "DisplayName", 0,
                              winreg.REG_SZ, APP_DISPLAY_NAME)
            winreg.SetValueEx(k, "UninstallString", 0,
                              winreg.REG_SZ, str(uninstall_exe))
            winreg.SetValueEx(k, "DisplayIcon", 0,
                              winreg.REG_SZ, icon_for_reg)
            winreg.SetValueEx(k, "InstallLocation", 0,
                              winreg.REG_SZ, str(install_path))
            winreg.SetValueEx(k, "NoModify", 0,
                              winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "NoRepair", 0,
                              winreg.REG_DWORD, 1)
        _log("Registry-entry: OK")
    except Exception as e:
        _log("Registry-entry FOUT: " + str(e))


# === Wizard UI ===

class InstallerWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME + tr("installer_title"))
        # ModernStyle zou een eigen banner-strook hebben - dat
        # botst met onze eigen branded layout op Welkom/Klaar.
        # ClassicStyle = minimal chrome, laat onze layout puur tonen.
        self.setWizardStyle(QWizard.ClassicStyle)
        # Geen logo bovenin van Qt zelf
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.NoCancelButtonOnLastPage, True)
        # Groter zodat 200px banner + content comfortabel past
        self.resize(780, 540)
        self.setMinimumSize(720, 500)
        self.install_dir = ""
        self.make_desktop_shortcut = True

        self.addPage(WelcomePage())
        self.addPage(PathPage())
        self.install_page = InstallPage(self)
        self.addPage(self.install_page)
        self.addPage(DonePage())

        # KRITIEK: Qt's eigen vertalingen werken niet betrouwbaar
        # na Nuitka --onefile. We zetten knop-teksten handmatig zodat
        # ze ALTIJD in de juiste taal staan (NL of EN).
        self.setButtonText(QWizard.NextButton, tr("btn_next"))
        self.setButtonText(QWizard.BackButton, tr("btn_back"))
        self.setButtonText(QWizard.CancelButton, tr("btn_cancel"))
        self.setButtonText(QWizard.FinishButton, tr("btn_finish"))


def _find_brand_logo_in_payload():
    """
    Bij de wizard wordt aangeroepen VOOR de install. De payload is
    nog in de exe verpakt - we hebben 'm niet uitgepakt. We doen
    een mini-extract van alleen meta/brand_logo.* uit de payload-zip.

    Returns: bytes van de logo + extensie, of (None, None).
    """
    import io
    try:
        zip_bytes = base64.b64decode(PAYLOAD_B64)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                low = name.lower()
                if low.startswith("meta/brand_logo."):
                    ext = Path(name).suffix.lower()
                    return zf.read(name), ext
    except Exception as e:
        print("brand_logo extract faalde:", e)
    return None, None


# Cache - laden gebeurt 1x per wizard-run
_BRAND_LOGO_BYTES = None
_BRAND_LOGO_EXT = None


def _get_brand_logo():
    global _BRAND_LOGO_BYTES, _BRAND_LOGO_EXT
    if _BRAND_LOGO_BYTES is None and _BRAND_LOGO_EXT is None:
        _BRAND_LOGO_BYTES, _BRAND_LOGO_EXT = _find_brand_logo_in_payload()
    return _BRAND_LOGO_BYTES, _BRAND_LOGO_EXT


def _wrap_page_with_brand_banner(inner_widget):
    """
    Wikkel een pagina-inhoud in een lay-out met:
      - Links: 200px brede banner met Dravenlock-logo (donker paars)
      - Rechts: header (app-naam + Dravenlock Software) + content

    Wordt gebruikt door Welkom en Klaar pagina's.
    """
    container = QWidget()
    container.setStyleSheet("background: " + BG_APP + ";")
    h = QHBoxLayout(container)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # === Banner links (200px, volle hoogte) ===
    # Pikzwart zodat het Dravenlock-logo (zwart-zilver) er
    # perfect in past. Subtiele rand rechts scheidt 'm van de
    # antraciet hoofd-bg.
    banner = QWidget()
    banner.setFixedWidth(200)
    banner.setStyleSheet(
        "background: #000000; "
        "border-right: 1px solid " + BORDER + ";"
    )
    banner_v = QVBoxLayout(banner)
    banner_v.setContentsMargins(20, 30, 20, 30)
    banner_v.addStretch()

    logo_lbl = QLabel()
    logo_lbl.setAlignment(Qt.AlignCenter)
    logo_lbl.setStyleSheet("background: transparent;")

    logo_bytes, logo_ext = _get_brand_logo()
    if logo_bytes:
        pix = QPixmap()
        pix.loadFromData(logo_bytes)
        if not pix.isNull():
            # Schaal naar max 160px breed, behoud aspect ratio
            scaled = pix.scaled(
                160, 160,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            logo_lbl.setPixmap(scaled)
        else:
            logo_lbl.setText(BRAND_NAME)
            logo_lbl.setStyleSheet(
                "background: transparent; color: " + ACCENT + "; "
                "font-size: 14pt; font-weight: bold;"
            )
            logo_lbl.setWordWrap(True)
    else:
        # Geen logo meegegeven - toon merknaam als tekst
        logo_lbl.setText(BRAND_NAME)
        logo_lbl.setStyleSheet(
            "background: transparent; color: " + ACCENT + "; "
            "font-size: 14pt; font-weight: bold;"
        )
        logo_lbl.setWordWrap(True)
        logo_lbl.setAlignment(Qt.AlignCenter)

    banner_v.addWidget(logo_lbl)
    banner_v.addStretch()
    h.addWidget(banner)

    # === Rechts: header + inhoud ===
    right = QWidget()
    right.setStyleSheet("background: " + BG_APP + ";")
    right_v = QVBoxLayout(right)
    right_v.setContentsMargins(28, 24, 28, 24)
    right_v.setSpacing(14)

    # Header: app-naam GROOT + Dravenlock Software DIMMER ernaast
    header_row = QHBoxLayout()
    header_row.setSpacing(12)

    app_lbl = QLabel(APP_DISPLAY_NAME)
    app_lbl.setStyleSheet(
        "background: transparent; color: " + TEXT + "; "
        "font-size: 22pt; font-weight: bold;"
    )
    header_row.addWidget(app_lbl)

    brand_lbl = QLabel(BRAND_NAME)
    brand_lbl.setStyleSheet(
        "background: transparent; color: " + TEXT_DIM + "; "
        "font-size: 11pt;"
    )
    brand_lbl.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
    header_row.addWidget(brand_lbl, stretch=1)

    right_v.addLayout(header_row)

    # Scheidings-lijntje
    sep = QLabel()
    sep.setFixedHeight(1)
    sep.setStyleSheet("background: " + BORDER + ";")
    right_v.addWidget(sep)

    # Page-inhoud
    right_v.addWidget(inner_widget, stretch=1)

    h.addWidget(right, stretch=1)

    return container



class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        # Inhoud die rechts in de branded layout komt
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(10)

        welkom = QLabel(tr("welcome"))
        welkom.setStyleSheet(
            "background: transparent; color: " + ACCENT + "; "
            "font-size: 16pt; font-weight: bold;"
        )
        iv.addWidget(welkom)

        m = QLabel(tr("welcome_body", app=APP_DISPLAY_NAME))
        m.setWordWrap(True)
        m.setStyleSheet(
            "background: transparent; color: " + TEXT + "; "
            "font-size: 11pt;"
        )
        iv.addWidget(m)
        iv.addStretch()

        # Wikkel met banner
        branded = _wrap_page_with_brand_banner(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(branded)


class PathPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("path_title"))
        self.setSubTitle(tr("path_subtitle", app=APP_DISPLAY_NAME))

        default_root = os.environ.get(
            "LOCALAPPDATA", os.path.expanduser("~")
        )
        # Default: LOCALAPPDATA/Programs (de submap komt er
        # automatisch onder via _resolve_install_dir).
        default = Path(default_root) / "Programs"

        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("parent_folder")))

        h = QHBoxLayout()
        self.path_edit = QLineEdit(str(default))
        self.path_edit.setMinimumHeight(36)
        self.path_edit.textChanged.connect(self._update_preview)
        h.addWidget(self.path_edit)

        btn = QPushButton(tr("browse"))
        btn.clicked.connect(self._browse)
        h.addWidget(btn)
        v.addLayout(h)

        # Preview van het volledige install-pad incl submap
        self.lbl_preview = QLabel("")
        self.lbl_preview.setStyleSheet(
            "color: " + ACCENT + "; font-size: 10pt; padding: 6px 2px;"
        )
        self.lbl_preview.setWordWrap(True)
        v.addWidget(self.lbl_preview)
        self._update_preview()

        self.chk_desktop = QCheckBox(tr("desktop_shortcut"))
        self.chk_desktop.setChecked(True)
        v.addWidget(self.chk_desktop)
        v.addStretch()

    def _resolve_install_dir(self):
        """
        Het uiteindelijke install-pad is ALTIJD <gekozen_map>/<APP_NAME>.
        Tenzij de gebruiker zelf al een map met die naam koos -
        dan niet dubbel nesten.
        """
        chosen = Path(self.path_edit.text().strip())
        if chosen.name == APP_DISPLAY_NAME:
            return chosen
        return chosen / APP_DISPLAY_NAME

    def _update_preview(self):
        try:
            install = self._resolve_install_dir()
            self.lbl_preview.setText(
                tr("install_to") + str(install)
            )
        except Exception:
            self.lbl_preview.setText("")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("dialog_parent"), self.path_edit.text()
        )
        if d:
            # Als de gebruiker per ongeluk de submap zelf koos
            # (bv. al bestaande oude install-map), strippen we 'm
            chosen = Path(d)
            if chosen.name == APP_DISPLAY_NAME:
                chosen = chosen.parent
            self.path_edit.setText(str(chosen))

    def validatePage(self):
        path = self.path_edit.text().strip()
        if not path:
            return False
        install_dir = self._resolve_install_dir()
        self.wizard().install_dir = str(install_dir)
        self.wizard().make_desktop_shortcut = self.chk_desktop.isChecked()
        return True


class InstallPage(QWizardPage):
    def __init__(self, wiz):
        super().__init__()
        self._wiz = wiz
        self.setTitle(tr("install_title"))
        self.setSubTitle(tr("install_subtitle"))

        v = QVBoxLayout(self)
        self.lbl_status = QLabel(tr("install_subtitle"))
        v.addWidget(self.lbl_status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        v.addWidget(self.bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            "background:" + BG_CONSOLE + ";color:" + TEXT + ";"
            "font-family:Consolas;border-radius:6px;padding:8px;"
            "border:2px solid " + BORDER + ";"
        )
        v.addWidget(self.log, stretch=1)

        self._thread = None
        self._worker = None
        self._done = False

    def isComplete(self):
        return self._done

    def initializePage(self):
        self._done = False
        self.completeChanged.emit()

        self._thread = QThread()
        self._worker = ExtractWorker(
            self._wiz.install_dir,
            self._wiz.make_desktop_shortcut
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.bar.setValue)
        self._worker.log.connect(self._on_log)
        self._worker.finished.connect(self._on_done)
        self._thread.start()

    def _on_log(self, msg):
        self.log.appendPlainText(msg)
        self.lbl_status.setText(msg)

    def _on_done(self, ok, info):
        self._thread.quit()
        self._thread.wait()
        if ok:
            self.log.appendPlainText("")
            self.log.appendPlainText("Geinstalleerd in: " + info)
            self._done = True
            self.completeChanged.emit()
            self._wiz.next()
        else:
            err_msg = QMessageBox(self)
            err_msg.setIcon(QMessageBox.Critical)
            err_msg.setWindowTitle(tr("error_title"))
            err_msg.setText(tr("install_failed") + info)
            ok_btn = err_msg.addButton(tr("btn_ok"),
                                        QMessageBox.AcceptRole)
            err_msg.setDefaultButton(ok_btn)
            err_msg.exec()


class DonePage(QWizardPage):
    def __init__(self):
        super().__init__()

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(10)

        klaar = QLabel(tr("done"))
        klaar.setStyleSheet(
            "background: transparent; color: " + ACCENT + "; "
            "font-size: 16pt; font-weight: bold;"
        )
        iv.addWidget(klaar)

        m = QLabel(tr("done_body", app=APP_DISPLAY_NAME))
        m.setWordWrap(True)
        m.setStyleSheet(
            "background: transparent; color: " + TEXT + "; "
            "font-size: 11pt;"
        )
        iv.addWidget(m)
        iv.addStretch()

        branded = _wrap_page_with_brand_banner(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(branded)


def main():
    app = QApplication(sys.argv)

    # Qt's eigen vertalingen voor stock-knoppen
    # (Next/Cancel/Back/Finish). Bestanden zitten in PySide6
    # installatie - we laden de juiste taal voor de wizard.
    try:
        translator = QTranslator()
        locale = QLocale.system()
        translations_path = QLibraryInfo.path(
            QLibraryInfo.TranslationsPath
        )
        # Probeer qt_<lang>.qm voor stock-vertalingen
        if translator.load(locale, "qt", "_", translations_path):
            app.installTranslator(translator)
        # qtbase_<lang>.qm voor moderne Qt6 builds
        translator2 = QTranslator()
        if translator2.load(locale, "qtbase", "_", translations_path):
            app.installTranslator(translator2)
    except Exception as e:
        print("Translator load faalde:", e)

    app.setStyleSheet(
        "QWizard { background: " + BG_APP + "; } "
        "QWizard QWidget { background: " + BG_APP + "; "
        "color: " + TEXT + "; } "
        "QLabel { color: " + TEXT + "; font-size: 11pt; "
        "background: transparent; } "
        "QPushButton { background: " + ACCENT + "; "
        "color: " + TEXT_ON_ACCENT + "; border: none; "
        "border-radius: 6px; padding: 7px 18px; "
        "font-weight: bold; min-width: 80px; } "
        "QPushButton:hover { background: " + ACCENT_HOVER + "; "
        "color: " + TEXT_ON_ACCENT + "; } "
        "QPushButton:pressed { background: " + ACCENT_PRESSED + "; "
        "color: " + TEXT_ON_ACCENT + "; } "
        "QPushButton:focus { background: " + ACCENT + "; "
        "color: " + TEXT_ON_ACCENT + "; outline: none; } "
        "QPushButton:default { background: " + ACCENT + "; "
        "color: " + TEXT_ON_ACCENT + "; } "
        "QPushButton:disabled { background: " + BORDER + "; "
        "color: " + TEXT_DIM + "; } "
        "QLineEdit { background: " + BG_INPUT + "; "
        "color: " + TEXT + "; "
        "border: 2px solid " + BORDER + "; border-radius: 6px; "
        "padding: 6px 10px; font-size: 11pt; "
        "selection-background-color: " + ACCENT + "; "
        "selection-color: " + TEXT_ON_ACCENT + "; } "
        "QLineEdit:focus { border-color: " + ACCENT + "; } "
        "QCheckBox { color: " + TEXT + "; background: transparent; "
        "font-size: 11pt; } "
        "QCheckBox::indicator { width: 18px; height: 18px; "
        "border: 2px solid " + BORDER + "; border-radius: 4px; "
        "background: " + BG_INPUT + "; } "
        "QCheckBox::indicator:checked { background: " + ACCENT + "; "
        "border-color: " + ACCENT + "; } "
        "QProgressBar { background: " + BG_INPUT + "; "
        "border: 2px solid " + BORDER + "; border-radius: 6px; "
        "height: 22px; text-align: center; color: " + TEXT + "; "
        "font-weight: bold; } "
        "QProgressBar::chunk { background: #3f4654; border: 1px solid " + ACCENT + "; "
        "border-radius: 4px; } "
        "QMessageBox { background: " + BG_CARD + "; } "
        "QMessageBox QLabel { color: " + TEXT + "; }"
    )
    wiz = InstallerWizard()
    wiz.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
'''


def render_installer_stub(app_display_name: str,
                          app_exe_name: str,
                          payload_b64: str) -> str:
    """
    Vul de template-placeholders in. Voor PAYLOAD_B64 splitsen
    we in regels van 76 chars zodat het in een triple-quoted
    string-literal past.
    """
    lines = []
    for i in range(0, len(payload_b64), 76):
        lines.append(payload_b64[i:i + 76])
    payload_chunked = "\n".join(lines)

    return (INSTALLER_STUB_TEMPLATE
            .replace("__APP_DISPLAY_NAME__", app_display_name)
            .replace("__APP_EXE_NAME__", app_exe_name)
            .replace("__PAYLOAD_B64__", payload_chunked))
