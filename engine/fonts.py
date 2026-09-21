"""Cross-platform font resolution + FFmpeg filtergraph path escaping.

Resolution order:
  1. Explicit path (config captions.font != "auto")
  2. assets/fonts/ (Anton-Regular.ttf preferred, then any .ttf/.otf)
  3. OS standard font directories (Linux, macOS, Windows)
  4. FontNotFoundError listing every searched path
"""

import logging
import os
import urllib.request
from pathlib import Path

log = logging.getLogger("engine.fonts")

BUNDLED_FONT = "Anton-Regular.ttf"
BUNDLED_FONT_URL = ("https://raw.githubusercontent.com/google/fonts/"
                    "main/ofl/anton/Anton-Regular.ttf")
FONT_DIR = Path("assets/fonts")

OS_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/impact.ttf",
]


class FontNotFoundError(RuntimeError):
    pass


def ensure_bundled_font(font_dir=FONT_DIR):
    """Download the bundled Anton font if missing. Never raises (offline-safe)."""
    target = Path(font_dir) / BUNDLED_FONT
    if target.exists() and target.stat().st_size > 10000:
        return target
    try:
        Path(font_dir).mkdir(parents=True, exist_ok=True)
        log.info("Downloading bundled font %s ...", BUNDLED_FONT)
        req = urllib.request.Request(BUNDLED_FONT_URL,
                                     headers={"User-Agent": "dank-engine"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 10000:
            raise ValueError(f"font download too small ({len(data)} bytes)")
        with open(target, "wb") as f:
            f.write(data)
        return target
    except Exception as e:
        log.warning("Could not download bundled font (%s). "
                    "Falling back to OS fonts.", e)
        target.unlink(missing_ok=True)
        return None


def resolve_font(preferred=None):
    searched = []
    if preferred and preferred != "auto":
        p = Path(preferred)
        searched.append(str(p))
        if p.exists():
            return p.resolve()

    if FONT_DIR.exists():
        anton = FONT_DIR / BUNDLED_FONT
        searched.append(str(anton))
        if anton.exists():
            return anton.resolve()
        for f in sorted(FONT_DIR.glob("*.ttf")) + sorted(FONT_DIR.glob("*.otf")):
            searched.append(str(f))
            return f.resolve()

    for c in OS_FONT_CANDIDATES:
        searched.append(c)
        if os.path.exists(c):
            return Path(c).resolve()

    raise FontNotFoundError(
        "No usable font found. Searched:\n  " + "\n  ".join(searched))


def escape_font_path(path):
    """Escape a font path for FFmpeg's filtergraph parser (fontfile='...').

    Normalizes backslashes to forward slashes and escapes colons so Windows
    paths like C:\\Windows\\Fonts\\arialbd.ttf become C\\:/Windows/Fonts/...
    """
    s = str(path).replace("\\", "/")
    s = s.replace(":", "\\:")
    return s
