"""
core/styling.py - Donker Dravenlock-thema, zilver op antraciet.

Contrast-checks (achtergrond -> tekst, alle WCAG AAA):
  bg_app (#111114) -> text (#e8eaef)        = 16.2:1  AAA
  bg_card (#1a1a20) -> text (#e8eaef)       = 13.4:1  AAA
  bg_input (#0a0a0c) -> text (#e8eaef)      = 18.8:1  AAA
  accent (#c0c8d4) -> bg_app (#111114)      = 11.8:1  AAA
  text_dim (#a0a4ad) -> bg_app (#111114)    =  8.1:1  AAA

Subtiliteit komt uit kleinere font / placement, NIET uit dimme
kleuren (text_dim blijft >= 7:1 op alle bg's).
"""
from dataclasses import dataclass
from PySide6.QtGui import QFont


@dataclass(frozen=True)
class _Color:
    bg_app = "#111114"           # antraciet hoofd
    bg_card = "#1a1a20"          # iets lichter voor banner/cards
    bg_input = "#0a0a0c"         # donkerder voor inputs
    bg_console = "#050507"       # bijna pikzwart voor console-log
    bg_hover = "#22222a"

    text = "#e8eaef"             # zacht wit
    text_dim = "#a0a4ad"         # gedimd, nog AAA
    text_on_accent = "#111114"   # antraciet op zilver

    accent = "#c0c8d4"           # zilver/staal (Dravenlock)
    accent_hover = "#d4dae3"
    accent_pressed = "#a8b0bc"
    accent_dim = "#383a42"

    success = "#5ad988"
    error = "#ff7a6f"
    warning = "#ffb84d"

    border = "#2a2a32"
    border_focus = "#c0c8d4"


COLOR = _Color()


def base_font(size: int = 11) -> QFont:
    return QFont("Segoe UI", size)


def mono_font(size: int = 10) -> QFont:
    f = QFont("Consolas", size)
    f.setStyleHint(QFont.Monospace)
    return f


def title_font(size: int = 18) -> QFont:
    f = QFont("Segoe UI", size)
    f.setBold(True)
    return f


def app_stylesheet() -> str:
    return (
        f"QMainWindow {{ background: {COLOR.bg_app}; }} "
        f"QWidget {{ color: {COLOR.text}; }} "
        f"QToolTip {{ background: {COLOR.bg_card}; "
        f"color: {COLOR.text}; border: 1px solid {COLOR.border}; "
        f"padding: 4px 8px; }} "
        f"QMessageBox {{ background: {COLOR.bg_card}; }} "
        f"QMessageBox QLabel {{ color: {COLOR.text}; }} "
        f"QSplitter::handle {{ background: {COLOR.border}; }}"
    )


def primary_button_style() -> str:
    return (
        f"QPushButton {{ "
        f"  background: {COLOR.accent}; "
        f"  color: {COLOR.text_on_accent}; "
        f"  border: none; "
        f"  border-radius: 8px; "
        f"  padding: 9px 22px; "
        f"  font-weight: bold; "
        f"  font-size: 11pt; "
        f"}} "
        f"QPushButton:hover {{ "
        f"  background: {COLOR.accent_hover}; "
        f"  color: {COLOR.text_on_accent}; "
        f"}} "
        f"QPushButton:pressed {{ "
        f"  background: {COLOR.accent_pressed}; "
        f"  color: {COLOR.text_on_accent}; "
        f"}} "
        f"QPushButton:focus {{ "
        f"  background: {COLOR.accent}; "
        f"  color: {COLOR.text_on_accent}; "
        f"  outline: none; "
        f"}} "
        f"QPushButton:default {{ "
        f"  background: {COLOR.accent}; "
        f"  color: {COLOR.text_on_accent}; "
        f"}} "
        f"QPushButton:disabled {{ "
        f"  background: {COLOR.border}; "
        f"  color: {COLOR.text_dim}; "
        f"}}"
    )


def secondary_button_style() -> str:
    return (
        f"QPushButton {{ "
        f"  background: {COLOR.bg_card}; "
        f"  color: {COLOR.accent}; "
        f"  border: 2px solid {COLOR.accent}; "
        f"  border-radius: 8px; "
        f"  padding: 7px 18px; "
        f"  font-weight: bold; "
        f"  font-size: 10pt; "
        f"}} "
        f"QPushButton:hover {{ "
        f"  background: {COLOR.accent_dim}; "
        f"  color: {COLOR.text}; "
        f"}} "
        f"QPushButton:pressed {{ "
        f"  background: {COLOR.bg_hover}; "
        f"  color: {COLOR.text}; "
        f"}} "
        f"QPushButton:focus {{ "
        f"  background: {COLOR.bg_card}; "
        f"  color: {COLOR.accent}; "
        f"  outline: none; "
        f"}}"
    )


def input_style() -> str:
    return (
        f"QLineEdit {{ "
        f"  background: {COLOR.bg_input}; "
        f"  color: {COLOR.text}; "
        f"  border: 2px solid {COLOR.border}; "
        f"  border-radius: 8px; "
        f"  padding: 7px 12px; "
        f"  font-size: 11pt; "
        f"  selection-background-color: {COLOR.accent}; "
        f"  selection-color: {COLOR.text_on_accent}; "
        f"}} "
        f"QLineEdit:focus {{ border-color: {COLOR.border_focus}; }} "
        f"QLineEdit:read-only {{ background: {COLOR.bg_card}; }}"
    )


def console_style() -> str:
    return (
        f"QPlainTextEdit {{ "
        f"  background: {COLOR.bg_console}; "
        f"  color: {COLOR.text}; "
        f"  border: 2px solid {COLOR.border}; "
        f"  border-radius: 8px; "
        f"  padding: 12px; "
        f"  font-family: 'Consolas', 'Courier New', monospace; "
        f"  font-size: 10pt; "
        f"  selection-background-color: {COLOR.accent}; "
        f"  selection-color: {COLOR.text_on_accent}; "
        f"}}"
    )


def list_style() -> str:
    return (
        f"QListWidget {{ "
        f"  background: {COLOR.bg_input}; "
        f"  color: {COLOR.text}; "
        f"  border: 2px solid {COLOR.border}; "
        f"  border-radius: 8px; "
        f"  padding: 4px; "
        f"  font-size: 10pt; "
        f"}} "
        f"QListWidget::item {{ padding: 4px 6px; }} "
        f"QListWidget::item:selected {{ "
        f"  background: {COLOR.accent_dim}; "
        f"  color: {COLOR.text}; "
        f"}} "
        f"QListWidget::item:hover {{ background: {COLOR.bg_hover}; }}"
    )


def progressbar_style() -> str:
    return (
        f"QProgressBar {{ "
        f"  background: {COLOR.bg_input}; "
        f"  border: 2px solid {COLOR.border}; "
        f"  border-radius: 6px; "
        f"  height: 24px; "
        f"  text-align: center; "
        f"  color: {COLOR.text}; "
        f"  font-weight: bold; "
        f"}} "
        f"QProgressBar::chunk {{ "
        f"  background: #3f4654; border: 1px solid {COLOR.accent}; "
        f"  border-radius: 4px; "
        f"}}"
    )
