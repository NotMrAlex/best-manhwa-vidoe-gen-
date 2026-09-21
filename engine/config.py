"""Configuration loading with backward-compatible schema versioning.

v1 configs (fps/workers/ffmpeg_threads + audio_volumes_dB) load unchanged;
missing v2 keys are filled with defaults; unknown keys are preserved.
"""

import copy
import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "engine_settings": {
        "fps": 30,
        "workers": 6,
        "ffmpeg_threads": "4",
        "profile": "final",
        "resume": True,
        "preflight": True,
        "render_mode": "clips",
        "segment_size": 10,
    },
    "audio_volumes_dB": {
        "voice": 3.0,
        "sfx": -2.0,
        "transition": 0.0,
        "bgm": -18.0,
    },
    "captions": {
        "enabled": True,
        "font": "auto",
        "max_font_size": 55,
        "min_font_size": 25,
    },
}


def _merge_defaults(defaults, current):
    merged = copy.deepcopy(defaults)

    def _apply(base, override):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                _apply(base[k], v)
            else:
                base[k] = v

    _apply(merged, current)
    return merged


def load_config(path=CONFIG_FILE):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return copy.deepcopy(DEFAULT_CONFIG)
    with open(path, "r", encoding="utf-8") as f:
        current = json.load(f)
    return _merge_defaults(DEFAULT_CONFIG, current)
