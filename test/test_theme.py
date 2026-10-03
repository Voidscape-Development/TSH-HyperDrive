# Checks TSHTheme's theme model: checking themes, importing and exporting
# them, and working out which theme is in use from the settings.
# Run from the repository root: python test/test_theme.py
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.abspath("."))
# Import only the modules needed, not the whole application
package = types.ModuleType("src")
package.__path__ = [os.path.abspath("src")]
sys.modules["src"] = package

from src.SettingsManager import SettingsManager
SettingsManager.SaveSettings = lambda: None

from src.TSHTheme import (
    TSHTheme, NormalizeTheme, ImportTheme, ExportTheme, BuiltinTheme,
    COLOR_KEYS, DEFAULT_ACCENT, DEFAULT_RADIUS, DEFAULT_SPACING, MAX_RADIUS,
    THEME_DARK, THEME_LIGHT,
)


def Settings(appearance=None, **other):
    SettingsManager.settings = {"appearance": appearance or {}, **other}


def ExpectInvalid(data):
    try:
        NormalizeTheme(data)
    except ValueError:
        return
    raise AssertionError(f"Expected {data} to be rejected")


def TestNormalizeFillsMissing():
    theme = NormalizeTheme({"colors": {"accent": "#00ff88"}}, "Mine")
    dark = BuiltinTheme(THEME_DARK)
    assert theme["name"] == "Mine"
    assert theme["colors"]["accent"] == "#00ff88"
    assert theme["colors"]["window"] == dark["colors"]["window"]
    assert theme["radius"] == DEFAULT_RADIUS
    assert theme["spacing"] == DEFAULT_SPACING
    assert theme["font"] == ""
    assert set(theme["colors"]) == set(COLOR_KEYS)

    # A light background fills in from the light theme
    theme = NormalizeTheme({"colors": {"window": "#fafafa"}})
    assert theme["colors"]["text"] == BuiltinTheme(THEME_LIGHT)["colors"]["text"]


def TestNormalizeCleansValues():
    theme = NormalizeTheme({
        "name": "  Spaced  ",
        "colors": {"window": "not a color", "accent": "#ABCDEF"},
        "radius": 99,
        "spacing": "huge",
        "font": 12,
    })
    assert theme["name"] == "Spaced"
    assert theme["colors"]["window"] == BuiltinTheme(THEME_DARK)["colors"]["window"]
    assert theme["colors"]["accent"] == "#abcdef"
    assert theme["radius"] == MAX_RADIUS
    assert theme["spacing"] == DEFAULT_SPACING
    assert theme["font"] == ""
    assert NormalizeTheme({"colors": {"text": "#fff"}, "radius": -3})["radius"] == 0
    assert NormalizeTheme({"colors": {"text": "#fff"}, "radius": "x"})["radius"] == DEFAULT_RADIUS


def TestNormalizeRejects():
    for data in [None, [], "theme", {}, {"colors": {}}, {"colors": "red"}, {"colors": {"other": "#fff"}}]:
        ExpectInvalid(data)


def TestExportImport():
    with tempfile.TemporaryDirectory() as folder:
        theme = NormalizeTheme({"colors": {"accent": "#f4b400"}, "radius": 12,
                                "spacing": "compact", "font": "DejaVu Serif"}, "Midnight")
        path = os.path.join(folder, "midnight.json")
        ExportTheme(theme, path)
        data = json.load(open(path))
        assert data["tsh_theme"] == 1
        assert ImportTheme(path) == theme

        # The file name is used when the theme has none
        del data["name"]
        unnamed = os.path.join(folder, "Sunset.json")
        json.dump(data, open(unnamed, "w"))
        assert ImportTheme(unnamed)["name"] == "Sunset"

        for content in ['{"colors": {"text": "#fff"}}', "not json", "[1, 2]", '{"tsh_theme": 1}']:
            bad = os.path.join(folder, "bad.json")
            open(bad, "w").write(content)
            try:
                ImportTheme(bad)
            except ValueError:
                continue
            raise AssertionError(f"Expected {content} to be rejected")

        try:
            ImportTheme(os.path.join(folder, "missing.json"))
        except ValueError:
            pass
        else:
            raise AssertionError("Expected a missing file to be rejected")


def TestMode():
    Settings()
    assert TSHTheme.Mode() == THEME_DARK
    assert TSHTheme.IsDark()

    # Light mode from before the Appearance settings
    Settings(light_mode=True)
    assert TSHTheme.Mode() == THEME_LIGHT
    assert not TSHTheme.IsDark()
    Settings({"theme": THEME_DARK}, light_mode=True)
    assert TSHTheme.Mode() == THEME_DARK

    Settings({"theme": "custom:Mine", "custom_themes": {"Mine": {"colors": {"window": "#ffffff"}}}})
    assert TSHTheme.Mode() == "custom:Mine"
    assert TSHTheme.CustomThemeName() == "Mine"
    assert TSHTheme.Current()["name"] == "Mine"
    assert not TSHTheme.IsDark()

    # A custom theme that's gone falls back to the default
    Settings({"theme": "custom:Gone"})
    assert TSHTheme.Mode() == THEME_DARK
    assert TSHTheme.CustomThemeName() is None

    Settings({"theme": "nonsense"})
    assert TSHTheme.Mode() == THEME_DARK


def TestAccent():
    Settings({"theme": THEME_LIGHT, "accent_color": "#2f80ed"})
    assert TSHTheme.Current()["colors"]["accent"] == "#2f80ed"
    Settings({"accent_color": "nope"})
    assert TSHTheme.Current()["colors"]["accent"] == DEFAULT_ACCENT
    # Text on a light accent is dark, on a dark accent white
    Settings({"accent_color": "#ffe066"})
    assert TSHTheme.Colors()["onAccent"].name() == "#111111"
    Settings({"accent_color": "#1a237e"})
    assert TSHTheme.Colors()["onAccent"].name() == "#ffffff"


def TestCustomThemes():
    Settings({"custom_themes": {"Good": {"colors": {"text": "#fff"}}, "Broken": "x"}})
    assert list(TSHTheme.CustomThemes()) == ["Good"]

    TSHTheme.SaveCustomTheme(NormalizeTheme({"colors": {"text": "#000"}}, "New"))
    assert sorted(TSHTheme.CustomThemes()) == ["Good", "New"]
    assert TSHTheme.UniqueName("New") == "New (2)"
    assert TSHTheme.UniqueName("Other") == "Other"

    # Renaming replaces the old entry
    TSHTheme.SaveCustomTheme(NormalizeTheme({"colors": {"text": "#000"}}, "Renamed"), "New")
    assert sorted(TSHTheme.CustomThemes()) == ["Good", "Renamed"]

    TSHTheme.DeleteCustomTheme("Good")
    assert sorted(TSHTheme.CustomThemes()) == ["Renamed"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("Test")]
    for test in tests:
        test()
        print(f"{test.__name__}: OK")
