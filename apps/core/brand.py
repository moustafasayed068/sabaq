"""Brand tokens (brand/tokens.json) as CSS custom properties, light and dark."""

import json
from pathlib import Path
from typing import Any

from django.conf import settings

TOKENS_JSON = Path(settings.BASE_DIR) / "brand" / "tokens.json"
TOKENS_CSS = Path(settings.BASE_DIR) / "static" / "css" / "tokens.css"

# Notice backgrounds used by reference/plan-lab.html but missing from tokens.json.
# Kept here until the owner adds them to the brand file.
EXTRA_COLORS: dict[str, dict[str, str]] = {
    "warn-soft": {"light": "#fbe9d0", "dark": "#3a2c12"},
    "stop-soft": {"light": "#fadcd3", "dark": "#3d1c14"},
}


def _colors(data: dict[str, Any], theme: str) -> list[str]:
    lines = [f"  --{t['name']}: {t['value'][theme]};" for t in data["color"]["tokens"]]
    lines += [f"  --{name}: {values[theme]};" for name, values in EXTRA_COLORS.items()]
    return lines


def build_tokens_css(data: dict[str, Any] | None = None) -> str:
    data = data or json.loads(TOKENS_JSON.read_text(encoding="utf-8"))
    families = data["type"]["families"]
    static_lines = [f"  --font-{name}: {value};" for name, value in families.items()]
    static_lines += [f"  --{t['name']}: {t['value']};" for t in data["spacing"]["tokens"]]
    static_lines += [f"  --{t['name']}: {t['value']};" for t in data["radius"]["tokens"]]
    dark = "\n".join("  " + line for line in [*_colors(data, "dark"), "  color-scheme: dark;"])
    return "\n".join([
        "/* Generated from brand/tokens.json by `manage.py build_tokens`. Do not edit. */",
        ":root {",
        *_colors(data, "light"),
        *static_lines,
        "  color-scheme: light;",
        "}",
        "@media (prefers-color-scheme: dark) {",
        '  :root:not([data-theme="light"]) {',
        dark,
        "  }",
        "}",
        ':root[data-theme="dark"] {',
        *_colors(data, "dark"),
        "  color-scheme: dark;",
        "}",
        "",
    ])  # fmt: skip
