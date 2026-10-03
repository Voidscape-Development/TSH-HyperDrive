# TSH's own look: a palette and style sheet on top of Qt's Fusion style.
# A theme is a set of colors plus corner roundness, spacing and font. There
# are two built-in themes (dark and light, with a configurable accent),
# "follow system", and any number of named custom themes, which can be
# imported and exported as .json files. Settings live under "appearance"
# and are edited on the Appearance page of the settings window.
import json
import os
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from qtpy.QtCore import *

from .SettingsManager import SettingsManager

THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_SYSTEM = "system"
# appearance.theme is "custom:<name>" for a custom theme
CUSTOM_PREFIX = "custom:"

DEFAULT_THEME = THEME_DARK
# Taken from the TSH logo's magenta
DEFAULT_ACCENT = "#d02670"
DEFAULT_UI_SCALE = 100
UI_SCALES = [80, 90, 100, 110, 125, 150, 175, 200]

# The colors a theme sets. Hover and disabled shades are worked out from them.
COLOR_KEYS = ["window", "surface", "raised", "border", "text", "muted", "accent"]

DEFAULT_RADIUS = 6
MAX_RADIUS = 16

SPACING_COMPACT = "compact"
SPACING_NORMAL = "normal"
SPACING_COMFORTABLE = "comfortable"
DEFAULT_SPACING = SPACING_NORMAL
# Padding (vertical, horizontal) in px for each kind of control
_SPACING = {
    SPACING_COMPACT: {"button": (2, 8), "input": (1, 5), "tab": (4, 10), "menu": (3, 20), "item": (1, 5)},
    SPACING_NORMAL: {"button": (4, 10), "input": (3, 6), "tab": (6, 12), "menu": (5, 24), "item": (3, 6)},
    SPACING_COMFORTABLE: {"button": (7, 14), "input": (6, 8), "tab": (8, 16), "menu": (7, 28), "item": (6, 8)},
}

THEME_FILE_VERSION = 1

_BUILTIN_COLORS = {
    THEME_DARK: {
        "window": "#14151b",
        "surface": "#1c1e26",
        "raised": "#262935",
        "border": "#353a4a",
        "text": "#e9eaf0",
        "muted": "#9298ab",
    },
    THEME_LIGHT: {
        "window": "#f2f3f7",
        "surface": "#ffffff",
        "raised": "#e7e9f0",
        "border": "#c9cdd9",
        "text": "#1b1d27",
        "muted": "#5c6275",
    },
}


def ColorLabels():
    return {
        "window": QApplication.translate("settings.appearance", "Background"),
        "surface": QApplication.translate("settings.appearance", "Panels and inputs"),
        "raised": QApplication.translate("settings.appearance", "Buttons"),
        "border": QApplication.translate("settings.appearance", "Borders"),
        "text": QApplication.translate("settings.appearance", "Text"),
        "muted": QApplication.translate("settings.appearance", "Secondary text"),
        "accent": QApplication.translate("settings.appearance", "Accent"),
    }


def SpacingLabels():
    return {
        SPACING_COMPACT: QApplication.translate("settings.appearance", "Compact"),
        SPACING_NORMAL: QApplication.translate("settings.appearance", "Normal"),
        SPACING_COMFORTABLE: QApplication.translate("settings.appearance", "Comfortable"),
    }


def Blend(a, b, amount):
    # a mixed with amount of b
    a, b = QColor(a), QColor(b)
    return QColor(
        round(a.red() + (b.red() - a.red()) * amount),
        round(a.green() + (b.green() - a.green()) * amount),
        round(a.blue() + (b.blue() - a.blue()) * amount))


def BuiltinTheme(mode, accent=DEFAULT_ACCENT):
    colors = dict(_BUILTIN_COLORS[mode])
    colors["accent"] = QColor(accent).name() if QColor(accent).isValid() else DEFAULT_ACCENT
    return {
        "name": QApplication.translate("settings.appearance", "Dark") if mode == THEME_DARK
        else QApplication.translate("settings.appearance", "Light"),
        "colors": colors,
        "radius": DEFAULT_RADIUS,
        "spacing": DEFAULT_SPACING,
        "font": "",
    }


def NormalizeTheme(data, name=None):
    """Checks a theme (from settings or a file) and fills in what's missing.
    Raises ValueError if it isn't a theme."""
    if not isinstance(data, dict) or not isinstance(data.get("colors", {}), dict):
        raise ValueError("Not a TSH theme")
    colors = data.get("colors", {})
    if not any(k in colors for k in COLOR_KEYS):
        raise ValueError("The theme has no colors")

    # Missing colors come from the built-in theme closest to it
    window = QColor(str(colors.get("window", "")))
    base = BuiltinTheme(THEME_LIGHT if window.isValid() and window.lightnessF() >= 0.5 else THEME_DARK)
    theme = {"name": str(name or data.get("name") or "").strip(), "colors": {}}
    for key in COLOR_KEYS:
        color = QColor(str(colors.get(key, "")))
        theme["colors"][key] = color.name() if color.isValid() else base["colors"][key]

    try:
        radius = int(data.get("radius", DEFAULT_RADIUS))
    except (TypeError, ValueError):
        radius = DEFAULT_RADIUS
    theme["radius"] = max(0, min(MAX_RADIUS, radius))
    spacing = data.get("spacing", DEFAULT_SPACING)
    theme["spacing"] = spacing if spacing in _SPACING else DEFAULT_SPACING
    font = data.get("font", "")
    theme["font"] = font.strip() if isinstance(font, str) else ""
    return theme


def ExportTheme(theme, path):
    data = {"tsh_theme": THEME_FILE_VERSION, **NormalizeTheme(theme)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def ImportTheme(path):
    """Reads a theme file. Raises ValueError if it isn't a TSH theme."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(str(e))
    if not isinstance(data, dict) or "tsh_theme" not in data:
        raise ValueError("Not a TSH theme")
    name = data.get("name") or os.path.splitext(os.path.basename(path))[0]
    return NormalizeTheme(data, name)


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


class ThemedIconEngine(QIconEngine):
    """Draws TSH's one-color icons in the theme's text color.

    The icons in assets/icons are white glyphs with a black outline (made
    for a dark background) or plain black glyphs. They're drawn as a single
    color, worked out when painted, so they follow theme changes. Icons with
    any other color are drawn as they are."""

    def __init__(self, path, badge=None):
        super().__init__()
        self.path = path
        self.badge = badge
        self.source = QIcon(path)
        self.kind = None
        self.cache = {}

    def clone(self):
        return ThemedIconEngine(self.path, self.badge)

    def _Kind(self):
        # "outlined" (white glyph, black outline), "solid" (one dark color)
        # or "color" (leave alone), from a small render of the icon
        if self.kind is None:
            image = self.source.pixmap(32, 32).toImage()
            light = dark = 0
            self.kind = "solid"
            for y in range(image.height()):
                for x in range(image.width()):
                    pixel = image.pixelColor(x, y)
                    if pixel.alpha() < 128:
                        continue
                    if pixel.hsvSaturationF() > 0.15:
                        self.kind = "color"
                        return self.kind
                    if pixel.lightnessF() > 0.6:
                        light += 1
                    else:
                        dark += 1
            if light > 0:
                self.kind = "outlined"
            elif dark == 0:
                self.kind = "color"
        return self.kind

    def _Color(self, mode, state):
        colors = TSHTheme.Colors()
        if mode == QIcon.Mode.Disabled:
            return colors["disabled"]
        if state == QIcon.State.On:
            return colors["accentText"]
        return colors["text"]

    def scaledPixmap(self, size, mode, state, scale):
        return self._Pixmap(size, mode, state, scale)

    def pixmap(self, size, mode, state):
        return self._Pixmap(size, mode, state, 1.0)

    def _Pixmap(self, size, mode, state, scale):
        if self._Kind() == "color":
            pixmap = self.source.pixmap(size, scale, mode, state)
        else:
            color = self._Color(mode, state)
            key = (size.width(), size.height(), scale, color.rgba())
            pixmap = self.cache.get(key)
            if pixmap is None:
                pixmap = self._Tinted(size, scale, color)
                if len(self.cache) >= 8:
                    self.cache.clear()
                self.cache[key] = pixmap
        if self.badge:
            pixmap = QPixmap(pixmap)
            painter = QPainter(pixmap)
            side = pixmap.width() * 0.4
            painter.drawPixmap(QRectF(pixmap.width() - side, 0, side, side).toRect(),
                               QIcon(self.badge).pixmap(int(side), int(side)))
            painter.end()
        return pixmap

    def _Tinted(self, size, scale, color):
        image = self.source.pixmap(size, scale).toImage().convertToFormat(
            QImage.Format.Format_ARGB32)
        outlined = self.kind == "outlined"
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                alpha = pixel.alphaF()
                if alpha == 0:
                    continue
                if outlined:
                    # Keep the white glyph, drop the black outline
                    alpha *= pixel.lightnessF()
                image.setPixelColor(x, y, QColor(
                    color.red(), color.green(), color.blue(), round(alpha * 255)))
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(scale)
        return pixmap

    def paint(self, painter, rect, mode, state):
        scale = painter.device().devicePixelRatioF() if painter.device() else 1.0
        painter.drawPixmap(rect, self._Pixmap(rect.size(), mode, state, scale))

    def actualSize(self, size, mode, state):
        return self.source.actualSize(size, mode, state)


def ThemedIcon(path, badge=None):
    """An icon from assets/icons that follows the theme's colors. badge is
    another icon drawn on its top right corner."""
    return QIcon(ThemedIconEngine(path, badge))


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
    _defaultFont = None

    @staticmethod
    def Mode():
        """The theme the user picked: dark, light, system or custom:<name>."""
        mode = SettingsManager.Get("appearance.theme", None)
        if mode in (THEME_DARK, THEME_LIGHT, THEME_SYSTEM):
            return mode
        if isinstance(mode, str) and mode.startswith(CUSTOM_PREFIX) \
                and mode[len(CUSTOM_PREFIX):] in TSHTheme.CustomThemes():
            return mode
        # Before the Appearance settings, light mode was a menu toggle
        return THEME_LIGHT if SettingsManager.Get("light_mode", False) else DEFAULT_THEME

    @staticmethod
    def CustomThemeName():
        mode = TSHTheme.Mode()
        return mode[len(CUSTOM_PREFIX):] if mode.startswith(CUSTOM_PREFIX) else None

    @staticmethod
    def CustomThemes():
        themes = {}
        stored = SettingsManager.Get("appearance.custom_themes", {})
        for name, data in (stored if isinstance(stored, dict) else {}).items():
            try:
                themes[name] = NormalizeTheme(data, name)
            except ValueError:
                pass
        return themes

    @staticmethod
    def SaveCustomTheme(theme, oldName=None):
        themes = dict(SettingsManager.Get("appearance.custom_themes", {}) or {})
        if oldName and oldName != theme["name"]:
            themes.pop(oldName, None)
        themes[theme["name"]] = NormalizeTheme(theme)
        SettingsManager.Set("appearance.custom_themes", themes)

    @staticmethod
    def DeleteCustomTheme(name):
        themes = dict(SettingsManager.Get("appearance.custom_themes", {}) or {})
        themes.pop(name, None)
        SettingsManager.Set("appearance.custom_themes", themes)

    @staticmethod
    def UniqueName(name):
        name = (name or "").strip() or QApplication.translate("settings.appearance", "Custom theme")
        existing = TSHTheme.CustomThemes()
        if name not in existing:
            return name
        i = 2
        while f"{name} ({i})" in existing:
            i += 1
        return f"{name} ({i})"

    @staticmethod
    def SystemIsDark():
        hints = QApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() != Qt.ColorScheme.Light
        return True

    @staticmethod
    def Current():
        """The theme in use, as a theme dict."""
        mode = TSHTheme.Mode()
        custom = TSHTheme.CustomThemeName()
        if custom:
            return TSHTheme.CustomThemes()[custom]
        if mode == THEME_SYSTEM:
            mode = THEME_DARK if TSHTheme.SystemIsDark() else THEME_LIGHT
        return BuiltinTheme(mode, SettingsManager.Get("appearance.accent_color", DEFAULT_ACCENT))

    @staticmethod
    def IsDark():
        return QColor(TSHTheme.Current()["colors"]["window"]).lightnessF() < 0.5

    @staticmethod
    def Colors(theme=None):
        """The theme's colors, for widgets that paint or style themselves.
        Each is a QColor."""
        theme = theme or TSHTheme.Current()
        colors = {k: QColor(v) for k, v in theme["colors"].items()}
        dark = colors["window"].lightnessF() < 0.5
        colors["raisedHover"] = Blend(colors["raised"], colors["text"], 0.08)
        colors["disabled"] = Blend(colors["muted"], colors["window"], 0.45)
        accent = colors["accent"]
        colors["accentHover"] = accent.lighter(115)
        # White or black, whichever reads better on the accent
        colors["onAccent"] = QColor("#ffffff") if accent.lightnessF() < 0.62 else QColor("#111111")
        colors["accentSoft"] = Blend(colors["surface"], accent, 0.22)
        # Accent color readable as text on the window
        colors["accentText"] = Blend(accent, colors["text"], 0.25) if dark else accent
        return colors

    @staticmethod
    def Radius():
        return TSHTheme.Current()["radius"]

    @staticmethod
    def Apply():
        app = QApplication.instance()
        app.setStyle("Fusion")
        theme = TSHTheme.Current()
        colors = TSHTheme.Colors(theme)
        app.setPalette(TSHTheme.Palette(colors))

        if TSHTheme._defaultFont is None:
            TSHTheme._defaultFont = QFont(app.font())
        font = QFont(TSHTheme._defaultFont)
        if theme["font"]:
            font.setFamily(theme["font"])
        app.setFont(font)

        app.setStyleSheet(TSHTheme.StyleSheet(colors, theme))

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
    def StyleSheet(c, theme=None):
        theme = theme or TSHTheme.Current()
        r = theme["radius"]
        pad = {k: f"{v}px {h}px" for k, (v, h) in _SPACING[theme["spacing"]].items()}
        buttonV = _SPACING[theme["spacing"]]["button"][0]
        # A family name can't hold a quote, but don't let one break the sheet
        font = theme["font"].replace('"', '')
        fontRule = f'QWidget {{ font-family: "{font}"; }}' if font else ""
        icons = {
            "down": ThemeIcon("chevron-down", c["muted"]),
            "up": ThemeIcon("chevron-up", c["muted"]),
            "downDisabled": ThemeIcon("chevron-down", c["disabled"]),
            "upDisabled": ThemeIcon("chevron-up", c["disabled"]),
            "check": ThemeIcon("check", c["onAccent"]),
            "dot": ThemeIcon("dot", c["onAccent"]),
        }
        c = {k: v.name() for k, v in c.items()}
        return fontRule + f"""
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
        QCheckBox::indicator, QAbstractItemView::indicator, QGroupBox::indicator {{ border-radius: {min(r, 4)}px; }}
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
            border: 1px solid {c['border']}; border-radius: {r}px; padding: 4px 8px;
        }}

        QPushButton, QToolButton {{
            background: {c['raised']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: {r}px;
            padding: {pad['button']};
        }}
        QToolButton {{ padding: {buttonV}px; }}
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
            border: 1px solid {c['border']}; border-radius: {r}px;
            padding: {pad['input']};
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
            border: 1px solid {c['border']}; border-radius: {r}px; padding: 2px;
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
            border: 1px solid {c['border']}; border-radius: {r}px;
            outline: none;
        }}
        QListView::item {{ padding: {pad['item']}; }}
        QAbstractItemView::item:hover {{ background: {c['raised']}; }}
        QAbstractItemView::item:selected {{ background: {c['accentSoft']}; color: {c['text']}; }}
        QHeaderView::section {{
            background: {c['raised']}; color: {c['muted']};
            border: none; border-right: 1px solid {c['border']}; border-bottom: 1px solid {c['border']};
            padding: 4px 6px; font-weight: bold;
        }}
        QTableCornerButton::section {{ background: {c['raised']}; border: none; }}

        QTabWidget::pane {{
            border: 1px solid {c['border']}; border-radius: {r}px; top: -1px;
            background: {c['window']};
        }}
        QTabBar::tab {{
            background: transparent; color: {c['muted']};
            padding: {pad['tab']}; border: none; border-bottom: 2px solid transparent;
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
            border: 1px solid {c['border']}; border-radius: {r + 2}px;
            margin-top: 10px; padding-top: 6px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            left: 10px; padding: 0px 4px; color: {c['muted']};
        }}

        QMenu {{
            background: {c['surface']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: {r + 2}px; padding: 4px;
        }}
        QMenu::item {{ padding: {pad['menu']}; border-radius: {max(r - 2, 0)}px; }}
        QMenu::item:selected {{ background: {c['accentSoft']}; }}
        QMenu::item:disabled {{ color: {c['disabled']}; }}
        QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
        QMenu::icon {{ padding-left: 6px; }}
        QMenuBar {{ background: {c['window']}; }}
        QMenuBar::item:selected {{ background: {c['raised']}; border-radius: {max(r - 2, 0)}px; }}

        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
        QScrollBar::handle {{ background: {c['border']}; border-radius: {min(r, 3)}px; }}
        QScrollBar::handle:vertical {{ min-height: 24px; }}
        QScrollBar::handle:horizontal {{ min-width: 24px; }}
        QScrollBar::handle:hover {{ background: {c['muted']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

        QProgressBar {{
            background: {c['surface']}; color: {c['text']};
            border: 1px solid {c['border']}; border-radius: {r}px; text-align: center;
        }}
        QProgressBar::chunk {{ background: {c['accent']}; border-radius: {max(r - 1, 0)}px; }}

        QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
        QSlider::handle:horizontal {{
            background: {c['accent']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
        }}

        QCheckBox, QRadioButton {{ spacing: 6px; }}
        QStatusBar {{ background: {c['window']}; color: {c['muted']}; }}
        """
