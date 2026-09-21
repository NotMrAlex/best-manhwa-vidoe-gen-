"""Caption filter construction (legacy drawtext path, cross-platform font fix)."""

import os

from .fonts import escape_font_path


def build_caption(item, lang, pid, is_shorts, cfg, font_path, build_dir="build"):
    """Returns the drawtext filter snippet, or None when no caption applies.

    Long-form only in this phase (matches legacy). Karaoke .ass path for both
    aspects arrives in Phase 3.
    """
    raw_text = item.get(f"narration_{lang}", "")
    if is_shorts or not raw_text or str(raw_text).strip().lower() in ["none", "null", ""]:
        return None

    safe_text = str(raw_text).strip().replace("'", "’").replace(":", "\\:").replace(",", "\\,").replace("%", "\\%")

    cap_cfg = cfg.get("captions", {})
    max_fs = int(cap_cfg.get("max_font_size", 55))
    min_fs = int(cap_cfg.get("min_font_size", 25))

    char_count = max(len(safe_text), 1)
    font_size = min(max_fs, max(min_fs, int(3200 / char_count)))

    txt_path = os.path.abspath(
        os.path.join(build_dir, f"cap_{lang}_{pid}.txt")).replace('\\', '/')
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(safe_text)

    ff_txt_path = txt_path.replace(":", "\\:")
    f_path = escape_font_path(font_path)

    return (f"drawtext=fontfile='{f_path}':textfile='{ff_txt_path}':"
            f"fontcolor=0xFFE600:fontsize={font_size}:bordercolor=black:"
            f"borderw=4:x=(w-text_w)/2:y=h-text_h-80")


def apply_caption(v_filter, text_filter):
    """Splice the caption filter into the [outv] chain (legacy string surgery)."""
    return v_filter.replace("[outv]", "[prenotext]") + f";[prenotext]{text_filter}[outv]"
