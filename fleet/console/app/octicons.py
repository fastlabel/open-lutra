"""Octicons (GitHub's icon set) rendered as inline SVG from the npm package's data file."""

import json
import urllib.request
from functools import cache

from markupsafe import Markup

_DATA_URL = "https://cdn.jsdelivr.net/npm/@primer/octicons@19.15.1/build/data.json"


@cache
def _data() -> dict:
    try:
        with urllib.request.urlopen(_DATA_URL, timeout=10) as response:
            return json.load(response)
    except OSError:
        return {}


def octicon(name: str, size: int = 16, cls: str = "") -> Markup:
    icon = _data().get(name)
    if icon is None:
        return Markup("")
    height = "24" if size >= 24 and "24" in icon["heights"] else "16"
    shape = icon["heights"][height]
    width = size * shape["width"] // int(height)
    return Markup(
        f'<svg class="octicon {cls}" viewBox="0 0 {shape["width"]} {height}" width="{width}" height="{size}"'
        f' fill="currentColor" aria-hidden="true">{shape["path"]}</svg>'
    )
