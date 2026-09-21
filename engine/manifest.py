"""Render manifest: hash-keyed resume/skip cache persisted to build/manifest.json."""

import hashlib
import json
import os
import threading
import time
from pathlib import Path

RENDER_PARAMS_VERSION = "p0"


def make_key(item, lang, aspect, panel_img, voice_audio, params):
    def sig(p):
        try:
            return [p, os.path.getsize(p), int(os.path.getmtime(p))]
        except OSError:
            return [p, None, None]

    payload = {
        "v": RENDER_PARAMS_VERSION,
        "item": item,
        "lang": lang,
        "aspect": aspect,
        "panel": sig(panel_img),
        "audio": sig(voice_audio),
        "params": params,
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


class Manifest:
    def __init__(self, path="build/manifest.json"):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def is_done(self, key, output):
        e = self._data.get(key, {})
        return e.get("status") == "ok" and os.path.exists(output)

    def mark_done(self, key, output):
        with self._lock:
            self._data[key] = {"status": "ok", "output": output,
                               "ts": int(time.time())}

    def mark_error(self, key, output, err):
        with self._lock:
            self._data[key] = {"status": "error", "output": output,
                               "error": str(err)[-500:], "ts": int(time.time())}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
        tmp.replace(self.path)
