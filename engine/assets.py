"""Asset lookup, image dimensions (Pillow-cached), duration probing, preflight."""

import json
import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

log = logging.getLogger("engine.assets")

AUDIO_EXTS = ('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
BG_EXTS = ['.mp4', '.mov', '.webm', '.jpg', '.png', '.jpeg']

_dims_cache = {}
_duration_cache = {}


def find_asset(folder_name, expected_name, valid_exts):
    folder = Path(folder_name)
    if not folder.exists():
        return None
    for file in folder.iterdir():
        if file.stem.lower() == expected_name.lower():
            if file.suffix.lower() in valid_exts:
                return str(file.absolute())
    return None


def find_intro(lang):
    """Return (audio_path, page, panel) for the intro TTS living in
    audio/{lang}/intro/, or None. The stem follows the {page}_{panel}
    convention (e.g. 1_1.wav); exactly one intro per language is expected."""
    folder = Path(f"audio/{lang}/intro")
    if not folder.exists():
        return None
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in AUDIO_EXTS:
            continue
        parts = f.stem.split("_")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            return str(f.absolute()), int(parts[0]), int(parts[1])
        log.warning("Intro file ignored (bad name, want {page}_{panel}): %s",
                    f.name)
    return None


def get_image_dims(img_path):
    """Pillow-based dims with caching (replaces per-clip ffprobe subprocess)."""
    if img_path in _dims_cache:
        return _dims_cache[img_path]
    dims = (1080, 1920)
    try:
        from PIL import Image
        with Image.open(img_path) as im:
            dims = im.size
    except Exception as e:
        log.warning("Could not read dims for %s (%s); using 1080x1920",
                    img_path, e)
    _dims_cache[img_path] = dims
    return dims


def probe_duration(audio_path):
    if audio_path in _duration_cache:
        return _duration_cache[audio_path]
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "csv=p=0", audio_path]
    dur = float(subprocess.check_output(cmd).decode().strip())
    _duration_cache[audio_path] = dur
    return dur


def prescan_durations(paths, workers=8):
    """Warm the duration cache in parallel before the render loop."""
    todo = [p for p in dict.fromkeys(paths) if p and p not in _duration_cache]
    if not todo:
        return

    def _probe(p):
        try:
            return p, probe_duration(p)
        except Exception as e:
            log.warning("Duration probe failed for %s: %s", p, e)
            return p, None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for p, d in ex.map(_probe, todo):
            if d is None:
                _duration_cache.pop(p, None)
    log.info("Pre-scanned durations for %d audio files", len(todo))


def preflight(story, langs, bg_file, font_path, build_dir="build"):
    """Validate all inputs before rendering. Mirrors render-time asset logic."""
    report = {"missing_panels": [], "missing_audio": [], "warnings": [],
              "background": bg_file, "font": str(font_path) if font_path else None,
              "hard_failures": 0}

    if not bg_file:
        report["warnings"].append("no background asset found")
        report["hard_failures"] += 1

    for item in story:
        if not item.get("render"):
            continue
        pid = f"{item['page']}_{item['panel']}"
        img_name = f"page{item['page']}_panel{item['panel']}"
        if not find_asset("output_panels", img_name, IMAGE_EXTS):
            report["missing_panels"].append(img_name)
        for lang in langs:
            if not find_asset(f"audio/{lang}", pid, AUDIO_EXTS):
                report["missing_audio"].append(f"{lang}/{pid}")
        for key, folder in (("sfx", "assets/sfx"),
                            ("transition", "assets/transitions")):
            name = item.get(key, "none")
            if name and name != "none" and not find_asset(folder, name, AUDIO_EXTS):
                report["warnings"].append(f"{key} asset missing: {name} ({pid})")

    report["hard_failures"] += len(report["missing_panels"])
    report["hard_failures"] += len(report["missing_audio"])

    Path(build_dir).mkdir(parents=True, exist_ok=True)
    report_path = Path(build_dir) / "preflight_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    if report["hard_failures"]:
        log.error("Preflight FAILED: %d missing panels, %d missing audio "
                  "(see %s)", len(report["missing_panels"]),
                  len(report["missing_audio"]), report_path)
    else:
        log.info("Preflight OK (%d warnings) — report: %s",
                 len(report["warnings"]), report_path)
    return report
