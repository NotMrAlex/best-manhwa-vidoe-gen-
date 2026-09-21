"""Per-clip rendering loop (per-clip mode is first-class; segments in Phase 1)."""

import functools
import logging
import os
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import assets
from . import audio as audio_mod
from . import captions as captions_mod
from . import motion, stitch
from .manifest import make_key

log = logging.getLogger("engine.render")

ASPECT_TAG = {"9:16": "916", "16:9": "169"}


def _encoder_available(name):
    try:
        out = subprocess.check_output(["ffmpeg", "-hide_banner", "-encoders"],
                                      stderr=subprocess.DEVNULL).decode()
        return name in out
    except Exception:
        return False


def detect_hardware():
    """NVENC only when nvidia-smi works AND the ffmpeg build ships nvenc."""
    try:
        subprocess.check_output('nvidia-smi', shell=True, stderr=subprocess.DEVNULL)
        if _encoder_available("h264_nvenc"):
            return "h264_nvenc", ["-preset", "p4", "-cq", "22"]
        log.warning("nvidia-smi found but ffmpeg lacks h264_nvenc; using libx264")
    except Exception:
        pass
    if platform.system() == "Darwin":
        return "h264_videotoolbox", ["-b:v", "8M"]
    return "libx264", ["-preset", "superfast", "-crf", "20"]


def _manifest_params(ctx):
    return {
        "fps": ctx["fps"],
        "encoder": ctx["encoder"],
        "enc_params": ctx["enc_params"],
        "vols": ctx["vols"],
        "captions": ctx["cfg"].get("captions", {}),
        "font": ctx["font_path"],
    }


def process_clip(task, ctx):
    item, lang, bg_file, aspect = task["item"], task["lang"], task["bg"], task["aspect"]
    pid = f"{item['page']}_{item['panel']}"
    is_shorts = (aspect == "9:16")
    build_dir = ctx["build_dir"]

    expected_img_name = f"page{item['page']}_panel{item['panel']}"
    panel_img = assets.find_asset("output_panels", expected_img_name, assets.IMAGE_EXTS)
    voice_audio = assets.find_asset(f"audio/{lang}", pid, assets.AUDIO_EXTS)

    if not panel_img or not voice_audio:
        return {"status": "error", "msg": f"Missing Assets for {pid} ({aspect})"}

    aspect_tag = ASPECT_TAG[aspect]
    out_file = os.path.join(build_dir, f"{lang}_{aspect_tag}_{pid}.mp4")

    key = make_key(item, lang, aspect, panel_img, voice_audio,
                   _manifest_params(ctx))
    if ctx["resume"] and ctx["manifest"].is_done(key, out_file):
        return {"status": "skipped", "msg": f"{pid} ({aspect})"}

    try:
        dur = assets.probe_duration(voice_audio)
    except Exception as e:
        return {"status": "error", "msg": f"Duration probe failed for {pid} ({aspect}): {e}"}

    fps = ctx["fps"]
    frames = int(dur * fps) + 15

    v_filter = motion.build_video_filter(item, panel_img, aspect, dur, frames, fps)

    if ctx["cfg"].get("captions", {}).get("enabled", True) and ctx["font_path"]:
        text_filter = captions_mod.build_caption(
            item, lang, pid, is_shorts, ctx["cfg"], ctx["font_path"], build_dir)
        if text_filter:
            v_filter = captions_mod.apply_caption(v_filter, text_filter)

    extra_inputs, amix_str = audio_mod.build_mix(item, ctx["vols"])

    is_bg_video = bg_file.lower().endswith(('.mp4', '.mov', '.webm', '.mkv', '.avi'))
    bg_inputs = (["-stream_loop", "-1", "-i", bg_file] if is_bg_video
                 else ["-loop", "1", "-framerate", str(fps), "-i", bg_file])

    # NOTE: no "-hwaccel auto" — it's a no-op for image inputs and crashes
    # headless Linux (CUDA/libva probe aborts) when decoding the bg video.
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-threads", ctx["ffmpeg_threads"],
        *bg_inputs, "-loop", "1", "-framerate", str(fps), "-i", panel_img,
        "-i", voice_audio
    ]
    for f in extra_inputs:
        cmd.extend(["-i", f])

    full_filter = f"{v_filter};{amix_str}"
    cmd.extend([
        "-filter_complex", full_filter,
        "-map", "[outv]", "-map", "[aout]",
        "-c:v", ctx["encoder"], *ctx["enc_params"],
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", str(dur), "-pix_fmt", "yuv420p", out_file
    ])

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        ctx["manifest"].mark_done(key, out_file)
        return {"status": "success", "msg": f"{pid} ({aspect})"}
    except subprocess.CalledProcessError as e:
        ctx["manifest"].mark_error(key, out_file, e.stderr)
        return {"status": "error", "msg": f"FFmpeg failed on {pid} ({aspect}): {e.stderr}"}


def render_story(story, langs, bg_file, ctx):
    """Render all languages, then stitch. Mirrors legacy main() flow exactly."""
    from tqdm import tqdm

    build_dir = ctx["build_dir"]
    Path(build_dir).mkdir(parents=True, exist_ok=True)
    all_results = []

    for lang in langs:
        if not Path(f"audio/{lang}").exists():
            continue

        log.info("\n🎬 PROCESSING LANGUAGE: %s", lang.upper())

        jobs = []
        long_clips = []
        shorts_groups = {}

        for item in story:
            if not item.get("render"):
                continue
            pid = f"{item['page']}_{item['panel']}"

            jobs.append({"item": item, "lang": lang, "bg": bg_file, "aspect": "16:9"})
            long_clips.append(os.path.join(build_dir, f"{lang}_169_{pid}.mp4"))

            short_id = item.get("shorts")
            if isinstance(short_id, int) and short_id > 0:
                jobs.append({"item": item, "lang": lang, "bg": bg_file, "aspect": "9:16"})
                shorts_groups.setdefault(short_id, []).append(
                    os.path.join(build_dir, f"{lang}_916_{pid}.mp4"))

        voice_paths = []
        for t in jobs:
            pid = f"{t['item']['page']}_{t['item']['panel']}"
            p = assets.find_asset(f"audio/{lang}", pid, assets.AUDIO_EXTS)
            if p:
                voice_paths.append(p)
        assets.prescan_durations(voice_paths)

        with ThreadPoolExecutor(max_workers=ctx["workers"]) as executor:
            results = list(tqdm(
                executor.map(functools.partial(process_clip, ctx=ctx), jobs),
                total=len(jobs), desc="Rendering", unit="clip", colour="green"))
            for res in results:
                if res["status"] == "error":
                    log.error("%s", res['msg'])
        all_results.extend(results)
        ctx["manifest"].save()

        skipped = sum(1 for r in results if r["status"] == "skipped")
        if skipped:
            log.info("Resume: skipped %d already-rendered clips", skipped)

        log.info("⏳ Stitching final long video...")
        long_output = os.path.join(ctx["output_dir"], lang, "long_video.mp4")
        stitch.combine_clips_fast(long_clips, long_output, build_dir,
                                  ctx["ffmpeg_threads"], ctx["vols"]["bgm"])
        log.info("🎉 EXPORTED: %s", long_output)

        for sid, clips in shorts_groups.items():
            log.info("⏳ Stitching short #%d...", sid)
            short_output = os.path.join(ctx["output_dir"], lang, "shorts",
                                        f"short_{sid}.mp4")
            stitch.combine_clips_fast(clips, short_output, build_dir,
                                      ctx["ffmpeg_threads"], ctx["vols"]["bgm"])
            log.info("🎉 EXPORTED: %s", short_output)

    log.info("\n✅ ALL PROCESSES FINISHED.")
    return all_results
