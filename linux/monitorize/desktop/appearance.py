"""Application palette for native dialogs and inherited Qt Quick control roles."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette


def _mix(color, target, amount):
    return QColor.fromRgbF(*[color.getRgbF()[i] * (1 - amount) + target * amount for i in range(3)])


def _luminance(color):
    def linear(v):
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return sum(linear(v) * weight for v, weight in zip(color.getRgbF()[:3], (.2126, .7152, .0722)))


def accent_colors(color, dark):
    """Build readable related shades while retaining the selected accent hue."""
    base = QColor(color)
    foreground = "#ffffff" if _luminance(base) < .179 else "#232629"
    heading = _mix(base, 1 if dark else 0, .48 if dark else .28)
    background = QColor("#272b2e" if dark else "#ffffff")
    for _ in range(20):
        light, dim = sorted((_luminance(heading), _luminance(background)), reverse=True)
        if (light + .05) / (dim + .05) >= 4.5:
            break
        heading = _mix(heading, 1 if dark else 0, .08)
    return {
        "buttonBackground": base.name(),
        "buttonBackgroundHover": _mix(base, 1, .15).name(),
        "buttonBackgroundPressed": _mix(base, 0, .18).name(),
        "buttonText": foreground,
        "accent": heading.name(),
        "headingText": heading.name(),
        "iconTint": _mix(base, 1, .55).name() if dark else "#43494f",
        "borderHover": base.name(),
        "accentAlpha20": QColor.fromRgbF(*base.getRgbF()[:3], .125).name(QColor.NameFormat.HexArgb),
        "accentAlpha40": QColor.fromRgbF(*base.getRgbF()[:3], .25).name(QColor.NameFormat.HexArgb),
    }


def apply_palette(app, mode="system", use_system_accent=None):
    from monitorize.config.settings import load_general_settings
    from monitorize.desktop.system_accent import system_accent
    source = system_accent(app)
    if use_system_accent is None:
        use_system_accent = load_general_settings().get("use_system_accent", False)
    dark = mode == "dark" or (mode == "system" and
                             app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    palette = QPalette()
    colors = {
        "Window": "#202324" if dark else "#eff0f1",
        "Base": "#272b2e" if dark else "#ffffff",
        "AlternateBase": "#303538" if dark else "#e3e5e7",
        "Button": "#303538" if dark else "#e3e5e7",
        "ToolTipBase": "#272b2e" if dark else "#ffffff",
        "Highlight": "#1676d2",
        "HighlightedText": "#ffffff",
        "Link": "#69b5ff" if dark else "#1764a5",
        "LinkVisited": "#a58cda" if dark else "#6746a0",
    }
    if use_system_accent:
        accent = accent_colors(source.color, dark)
        colors.update(Highlight=accent["buttonBackground"], HighlightedText=accent["buttonText"],
                      Link=accent["accent"], LinkVisited=accent["headingText"])
        if hasattr(QPalette.ColorRole, "Accent"):
            colors["Accent"] = accent["buttonBackground"]
    for role in ("WindowText", "Text", "ButtonText", "ToolTipText", "PlaceholderText"):
        colors[role] = ("#a4a9ae" if dark else "#626970") if role == "PlaceholderText" else ("#eff0f1" if dark else "#232629")
    for role, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ("WindowText", "Text", "ButtonText"):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role),
                         QColor("#a4a9ae" if dark else "#626970"))
    app.setPalette(palette)
