# TSH's own look: a palette and style sheet on top of Qt's Fusion style, in
# dark or light (or following the system), with a configurable accent color.
# Settings live under "appearance" and are edited on the Appearance page of
# the settings window.
import os
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from qtpy.QtCore import *

from .SettingsManager import SettingsManager

THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_SYSTEM = "system"

DEFAULT_THEME = THEME_DARK
# Taken from the TSH logo's magenta
DEFAULT_ACCENT = "#d02670"
DEFAULT_UI_SCALE = 100
UI_SCALES = [80, 90, 100, 110, 125, 150, 175, 200]

_BASE_COLORS = {
    THEME_DARK: {
        "window": "#14151b",
        "surface": "#1c1e26",
        "raised": "#262935",
        "raisedHover": "#2f3341",
        "border": "#353a4a",
        "text": "#e9eaf0",
        "muted": "#9298ab",
        "disabled": "#5d6273",
    },
    THEME_LIGHT: {
        "window": "#f2f3f7",
        "surface": "#ffffff",
        "raised": "#e7e9f0",
        "raisedHover": "#dcdfe8",
        "border": "#c9cdd9",
        "text": "#1b1d27",
        "muted": "#5c6275",
        "disabled": "#a3a8b8",
    },
}


def Blend(a, b, amount):
    # a mixed with amount of b
    a, b = QColor(a), QColor(b)
    return QColor(
        round(a.red() + (b.red() - a.red()) * amount),
        round(a.green() + (b.green() - a.green()) * amount),
        round(a.blue() + (b.blue() - a.blue()) * amount))


_ICONS = {
    "chevron-down": '<path d="M6 9l6 6 6-6" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "chevron-up": '<path d="M6 15l6-6 6 6" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
    "dot": '<circle cx="12" cy="12" r="5" fill="{color}"/>',
}


def ThemeIcon(name, color):
    # Style sheets can only draw arrows and check marks from image files, so
    # write one in the theme's colors and return its path for url()
    folder = os.path.join(QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.TempLocation), "tsh-theme")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}-{QColor(color).name()[1:]}.svg")
    if not os.path.isfile(path):
        with open(path, "w") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">' +
                    _ICONS[name].format(color=QColor(color).name()) + '</svg>')
    return path.replace("\\", "/")


def ApplyUIScale():
    # Qt only reads the scale factor when the application is created, so this
    # runs before that and a change takes effect on the next start. A scale
    # set in the environment wins.
    if "QT_SCALE_FACTOR" in os.environ:
        return
    try:
        scale = int(SettingsManager.Get("appearance.ui_scale", DEFAULT_UI_SCALE))
    except (TypeError, ValueError):
        return
    if scale != 100 and scale in UI_SCALES:
        os.environ["QT_SCALE_FACTOR"] = str(scale / 100)


class TSHTheme:
    _systemSignalConnected = False

    @staticmethod
    def Mode():
        # The theme the user picked: dark, light or system
        mode = SettingsManager.Get("appearance.theme", None)
        if mode in (THEME_DARK, THEME_LIGHT, THEME_SYSTEM):
            return mode
        # Before the Appearance settings, light mode was a menu toggle
        return THEME_LIGHT if SettingsManager.Get("light_mode", False) else DEFAULT_THEME

    @staticmethod
    def IsDark():
        mode = TSHTheme.Mode()
        if mode == THEME_SYSTEM:
            hints = QApplication.styleHints()
            if hasattr(hints, "colorScheme"):
                return hints.colorScheme() != Qt.ColorScheme.Light
            return True
        return mode == THEME_DARK

    @staticmethod
    def Colors():
        """The current theme's colors, for widgets that paint or style
        themselves. Each is a QColor."""
        base = _BASE_COLORS[THEME_DARK if TSHTheme.IsDark() else THEME_LIGHT]
        colors = {k: QColor(v) for k, v in base.items()}

        accent = QColor(SettingsManager.Get("appearance.accent_color", DEFAULT_ACCENT))
        if not accent.isValid():
            accent = QColor(DEFAULT_ACCENT)
        colors["accent"] = accent
        colors["accentHover"] = accent.lighter(115)
        # White or black, whichever reads better on the accent
        colors["onAccent"] = QColor("#ffffff") if accent.lightnessF() < 0.62 else QColor("#111111")
        colors["accentSoft"] = Blend(colors["surface"], accent, 0.22)
        # Accent color readable as text on the window
        colors["accentText"] = Blend(accent, colors["text"], 0.25) if TSHTheme.IsDark() else accent
        return colors

    @staticmethod
    def Apply():
        app = QApplication.instance()
        app.setStyle("Fusion")
        colors = TSHTheme.Colors()
        app.setPalette(TSHTheme.Palette(colors))
        app.setStyleSheet(TSHTheme.StyleSheet(colors))

        if not TSHTheme._systemSignalConnected:
            hints = QApplication.styleHints()
            if hasattr(hints, "colorSchemeChanged"):
                hints.colorSchemeChanged.connect(
                    lambda scheme: TSHTheme.Apply() if TSHTheme.Mode() == THEME_SYSTEM else None)
                TSHTheme._systemSignalConnected = True

    @staticmethod
    def Palette(c):
        palette = QPalette()
        roles = QPalette.ColorRole
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            palette.setColor(group, roles.Window, c["window"])
            palette.setColor(group, roles.WindowText, c["text"])
            palette.setColor(group, roles.Base, c["surface"])
            palette.setColor(group, roles.AlternateBase, Blend(c["surface"], c["raised"], 0.5))
            palette.setColor(group, roles.Text, c["text"])
            palette.setColor(group, roles.Button, c["raised"])
            palette.setColor(group, roles.ButtonText, c["text"])
            palette.setColor(group, roles.BrightText, c["onAccent"])
            palette.setColor(group, roles.Highlight, c["accent"])
            palette.setColor(group, roles.HighlightedText, c["onAccent"])
            palette.setColor(group, roles.ToolTipBase, c["raised"])
            palette.setColor(group, roles.ToolTipText, c["text"])
            palette.setColor(group, roles.PlaceholderText, c["muted"])
            palette.setColor(group, roles.Link, c["accentText"])
            palette.setColor(group, roles.LinkVisited, c["accentText"])
            palette.setColor(group, roles.Light, c["raisedHover"])
            palette.setColor(group, roles.Midlight, c["raised"])
            palette.setColor(group, roles.Mid, c["border"])
            palette.setColor(group, roles.Dark, Blend(c["border"], c["window"], 0.5))
            palette.setColor(group, roles.Shadow, QColor(0, 0, 0, 120))
        disabled = QPalette.ColorGroup.Disabled
        for role, color in [
            (roles.Window, c["window"]),
            (roles.Base, c["window"]),
            (roles.Button, c["raised"]),
            (roles.WindowText, c["disabled"]),
            (roles.Text, c["disabled"]),
            (roles.ButtonText, c["disabled"]),
            (roles.PlaceholderText, c["disabled"]),
            (roles.Highlight, c["border"]),
            (roles.HighlightedText, c["muted"]),
        ]:
            palette.setColor(disabled, role, color)
        return palette

    @staticmethod
    def StyleSheet(c):
        icons = {
            "down": ThemeIcon("chevron-down", c["muted"]),
            "up": ThemeIcon("chevron-up", c["muted"]),
            "downDisabled": ThemeIcon("chevron-down", c["disabled"]),
            "upDisabled": ThemeIcon("chevron-up", c["disabled"]),
            "check": ThemeIcon("check", c["onAccent"]),
            "dot": ThemeIcon("dot", c["onAccent"]),
        }
        c = {k: v.name() for k, v in c.items()}
        return f"""
        QComboBox::down-arrow {{ image: url({icons['down']}); width: 12px; height: 12px; }}
        QComboBox::down-arrow:disabled {{ image: url({icons['downDisabled']}); }}
        QAbstractSpinBox::up-arrow {{ image: url({icons['up']}); width: 10px; height: 10px; }}
        QAbstractSpinBox::down-arrow {{ image: url({icons['down']}); width: 10px; height: 10px; }}
        QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url({icons['upDisabled']}); }}
        QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{ image: url({icons['downDisabled']}); }}

        QCheckBox::indicator, QRadioButton::indicator,
        QAbstractItemView::indicator, QGroupBox::indicator {{
            width: 14px; height: 14px;
            background: {c['surface']}; border: 1.5px solid {c['muted']};
        }}
        QCheckBox::indicator, QAbstractItemView::indicator, QGroupBox::indicator {{ border-radius: 4px; }}
        QRadioButton::indicator {{ border-radius: 8px; }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {c['accent']}; }}
        QCheckBox::indicator:checked, QAbstractItemView::indicator:checked, QGroupBox::indicator:checked {{
            background: {c['accent']}; border-color: {c['accent']}; image: url({icons['check']});
        }}
        QCheckBox::indicator:indeterminate {{ background: {c['accentSoft']}; border-color: {c['accent']}; }}
        QRadioButton::indicator:checked {{
            background: {c['accent']}; border-color: {c['accent']}; image: url({icons['dot']});
        }}
        QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
            background: {c['window']}; border-color: {c['raised']};
        }}

        QToolTip {{
            background: {c['raised']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 8px;
        }}

        QPushButton, QToolButton {{
            background: {c['raised']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 6px;
            padding: 4px 10px;
        }}
        QToolButton {{ padding: 4px; }}
        QPushButton:hover, QToolButton:hover {{
            background: {c['raisedHover']}; border-color: {c['accent']};
        }}
        QPushButton:pressed, QToolButton:pressed,
        QPushButton:checked, QToolButton:checked {{
            background: {c['accentSoft']}; border-color: {c['accent']};
        }}
        QPushButton:default {{
            background: {c['accent']}; color: {c['onAccent']}; border-color: {c['accent']};
        }}
        QPushButton:default:hover {{ background: {c['accentHover']}; }}
        QPushButton:disabled, QToolButton:disabled {{
            background: {c['window']}; color: {c['disabled']}; border-color: {c['raised']};
        }}
        QPushButton::menu-indicator {{ subcontrol-position: right center; right: 6px; }}

        QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox, QKeySequenceEdit QLineEdit {{
            background: {c['surface']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 6px;
            padding: 3px 6px;
            selection-background-color: {c['accent']}; selection-color: {c['onAccent']};
        }}
        QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QAbstractSpinBox:hover, QComboBox:hover {{
            border-color: {c['muted']};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{
            border-color: {c['accent']};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
        QAbstractSpinBox:disabled, QComboBox:disabled {{
            background: {c['window']}; color: {c['disabled']}; border-color: {c['raised']};
        }}
        QComboBox QLineEdit {{ border: none; padding: 0px; background: transparent; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox QAbstractItemView {{
            background: {c['surface']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 6px; padding: 2px;
            selection-background-color: {c['accentSoft']}; selection-color: {c['text']};
            outline: none;
        }}
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            border: none; width: 18px; background: transparent;
        }}
        QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
            background: {c['raisedHover']};
        }}

        QAbstractItemView {{
            background: {c['surface']}; color: {c['text']};
            alternate-background-color: {c['raised']};
            selection-background-color: {c['accentSoft']}; selection-color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 6px;
            outline: none;
        }}
        QListView::item {{ padding: 3px 6px; }}
        QAbstractItemView::item:hover {{ background: {c['raised']}; }}
        QAbstractItemView::item:selected {{ background: {c['accentSoft']}; color: {c['text']}; }}
        QHeaderView::section {{
            background: {c['raised']}; color: {c['muted']};
            border: none; border-right: 1px solid {c['border']}; border-bottom: 1px solid {c['border']};
            padding: 4px 6px; font-weight: bold;
        }}
        QTableCornerButton::section {{ background: {c['raised']}; border: none; }}

        QTabWidget::pane {{
            border: 1px solid {c['border']}; border-radius: 6px; top: -1px;
            background: {c['window']};
        }}
        QTabBar::tab {{
            background: transparent; color: {c['muted']};
            padding: 6px 12px; border: none; border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:hover {{ color: {c['text']}; background: {c['raised']}; }}
        QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; }}
        QTabBar::close-button {{ subcontrol-position: right; }}

        QDockWidget {{ color: {c['muted']}; }}
        QDockWidget::title {{
            background: {c['window']}; padding: 4px 6px; text-align: left;
            border-bottom: 1px solid {c['border']};
        }}
        QMainWindow::separator {{ background: {c['border']}; width: 1px; height: 1px; }}
        QSplitter::handle {{ background: {c['border']}; }}
        QSplitter::handle:hover {{ background: {c['accent']}; }}

        QGroupBox {{
            border: 1px solid {c['border']}; border-radius: 8px;
            margin-top: 10px; padding-top: 6px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            left: 10px; padding: 0px 4px; color: {c['muted']};
        }}

        QMenu {{
            background: {c['surface']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 8px; padding: 4px;
        }}
        QMenu::item {{ padding: 5px 24px 5px 24px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {c['accentSoft']}; }}
        QMenu::item:disabled {{ color: {c['disabled']}; }}
        QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
        QMenu::icon {{ padding-left: 6px; }}
        QMenuBar {{ background: {c['window']}; }}
        QMenuBar::item:selected {{ background: {c['raised']}; border-radius: 4px; }}

        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
        QScrollBar::handle {{ background: {c['border']}; border-radius: 3px; }}
        QScrollBar::handle:vertical {{ min-height: 24px; }}
        QScrollBar::handle:horizontal {{ min-width: 24px; }}
        QScrollBar::handle:hover {{ background: {c['muted']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

        QProgressBar {{
            background: {c['surface']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: 6px; text-align: center;
        }}
        QProgressBar::chunk {{ background: {c['accent']}; border-radius: 5px; }}

        QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
        QSlider::handle:horizontal {{
            background: {c['accent']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
        }}

        QCheckBox, QRadioButton {{ spacing: 6px; }}
        QStatusBar {{ background: {c['window']}; color: {c['muted']}; }}
        """
