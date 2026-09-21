"""Segment rendering: 8-12 panels per FFmpeg invocation (Phase 1).

One process per segment amortizes startup/decoder overhead vs per-clip mode
(render_mode="clips", still first-class). A/V sync is held by cumulative
frame-compensated per-panel frame counts: panel i emits
round(cum_dur[i+1]*fps) - round(cum_dur[i]*fps) frames, so absolute panel
boundaries stay within half a frame of the audio timeline (no drift).
Segments are long-form (16:9) only; shorts stay per-clip.
"""

import hashlib
import logging
import os
import subprocess

from . import assets
from . import captions as captions_mod
from .assets import AUDIO_EXTS, find_asset
from .manifest import make_key
from .motion import build_video_filter

log = logging.getLogger("engine.segments")

DEFAULT_SEGMENT_SIZE = 10
MIN_SEGMENT_SIZE = 8
MAX_SEGMENT_SIZE = 12


def clamp_size(size):
    return max(MIN_SEGMENT_SIZE, min(MAX_SEGMENT_SIZE, int(size)))


def plan_segments(story, size=DEFAULT_SEGMENT_SIZE):
    """Chunk consecutive render:true story items into segment groups."""
    size = clamp_size(size)
    renderable = [it for it in story if it.get("render")]
    return [renderable[i:i + size] for i in range(0, len(renderable), size)]


def segment_name(lang, seg_idx):
    return f"{lang}_169_seg{seg_idx:04d}.mp4"


def _frame_windows(durs, fps):
    """Per-panel exact frame counts + cumulative boundary times (seconds)."""
    bounds = [0]
    acc = 0.0
    for d in durs:
        acc += d
        bounds.append(int(round(acc * fps)))
    counts = [bounds[i + 1] - bounds[i] for i in range(len(durs))]
    times = [b / fps for b in bounds]
    return counts, times


def build_segment_graph(members, lang, ctx, fps):
    """Build the full filter_complex string for one segment.

    members: [{item, panel_img, voice, dur}] in render order.
    Input layout: 0=bg, 1..k=panels, k+1..2k=voices, then sfx/transition.
    Returns (filter_complex, extra_input_files, total_dur_seconds).
    """
    k = len(members)
    vols = ctx["vols"]
    durs = [m["dur"] for m in members]
    counts, times = _frame_windows(durs, fps)

    vparts = ["[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
              "crop=1920:1080,setsar=1,split=" + str(k) +
              "".join(f"[bg{i}]" for i in range(k))]
    for i, m in enumerate(members):
        vparts.append(build_video_filter(
            m["item"], m["panel_img"], "16:9", m["dur"], counts[i] + 15, fps,
            src=f"{1 + i}:v", out=f"v{i}", bg=f"bg{i}",
            bg_chain=False, exact=True, trim_seconds=counts[i] / fps))
    vparts.append("".join(f"[v{i}]" for i in range(k)) +
                  f"concat=n={k}:v=1:a=0[vcat]")

    cur = "vcat"
    if ctx["cfg"].get("captions", {}).get("enabled", True) and ctx["font_path"]:
        for i, m in enumerate(members):
            item = m["item"]
            pid = f"{item['page']}_{item['panel']}"
            snip = captions_mod.build_caption(
                item, lang, pid, False, ctx["cfg"], ctx["font_path"],
                ctx["build_dir"])
            if snip:
                t0, t1 = times[i], times[i + 1]
                snip += f":enable='between(t,{t0:.3f},{t1 - 0.001:.3f})'"
                vparts.append(f"[{cur}]{snip}[cap{i}]")
                cur = f"cap{i}"
    vparts.append(f"[{cur}]null[outv]")

    voice0 = 1 + k
    aparts = []
    vlabels = []
    for i, m in enumerate(members):
        aparts.append(
            f"[{voice0 + i}:a]aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"aresample=44100,atrim=0:{m['dur']:.6f},asetpts=PTS-STARTPTS,"
            f"volume={vols['voice']}dB[av{i}]")
        vlabels.append(f"[av{i}]")
    aparts.append("".join(vlabels) + f"concat=n={k}:v=0:a=1[avoice]")

    mix = ["[avoice]"]
    extra_inputs = []
    ext = voice0 + k
    for i, m in enumerate(members):
        off_ms = int(round(times[i] * 1000))
        for key, vkey, folder in (("sfx", "sfx", "assets/sfx"),
                                  ("transition", "transition",
                                   "assets/transitions")):
            name = m["item"].get(key, "none")
            if name and str(name).strip().lower() != "none":
                f = find_asset(folder, name, AUDIO_EXTS)
                if f:
                    extra_inputs.append(f)
                    aparts.append(
                        f"[{ext}:a]aformat=sample_fmts=fltp:"
                        f"channel_layouts=stereo,aresample=44100,"
                        f"volume={vols[vkey]}dB,"
                        f"adelay={off_ms}|{off_ms}[mx{ext}]")
                    mix.append(f"[mx{ext}]")
                    ext += 1
    if len(mix) > 1:
        aparts.append("".join(mix) +
                      f"amix=inputs={len(mix)}:duration=first[aout]")
    else:
        aparts.append("[avoice]anull[aout]")

    return ";".join(vparts + aparts), extra_inputs, times[-1]


def _segment_params(ctx):
    return {
        "mode": "segments",
        "fps": ctx["fps"],
        "encoder": ctx["encoder"],
        "enc_params": ctx["enc_params"],
        "vols": ctx["vols"],
        "captions": ctx["cfg"].get("captions", {}),
        "font": ctx["font_path"],
    }


def segment_key(members, lang, ctx):
    params = _segment_params(ctx)
    member_keys = [make_key(m["item"], lang, "16:9", m["panel_img"],
                            m["voice"], params) for m in members]
    return hashlib.sha1("|".join(member_keys).encode()).hexdigest()


def render_segment(task, ctx):
    items, lang, bg_file = task["items"], task["lang"], task["bg"]
    idx = task["seg_idx"]
    fps = ctx["fps"]

    members = []
    for item in items:
        pid = f"{item['page']}_{item['panel']}"
        img = assets.find_asset("output_panels",
                                f"page{item['page']}_panel{item['panel']}",
                                assets.IMAGE_EXTS)
        voice = assets.find_asset(f"audio/{lang}", pid, assets.AUDIO_EXTS)
        if not img or not voice:
            return {"status": "error",
                    "msg": f"Missing Assets in segment {idx} ({pid})"}
        try:
            dur = assets.probe_duration(voice)
        except Exception as e:
            return {"status": "error",
                    "msg": f"Duration probe failed in segment {idx} "
                           f"({pid}): {e}"}
        members.append({"item": item, "panel_img": img, "voice": voice,
                        "dur": dur})

    out_file = os.path.join(ctx["build_dir"], segment_name(lang, idx))
    os.makedirs(ctx["build_dir"], exist_ok=True)

    key = segment_key(members, lang, ctx)
    if ctx["resume"] and ctx["manifest"].is_done(key, out_file):
        return {"status": "skipped",
                "msg": f"seg{idx:04d} ({len(items)} panels)"}

    full_filter, extra_inputs, total_dur = build_segment_graph(
        members, lang, ctx, fps)

    is_bg_video = bg_file.lower().endswith(
        ('.mp4', '.mov', '.webm', '.mkv', '.avi'))
    bg_inputs = (["-stream_loop", "-1", "-i", bg_file] if is_bg_video
                 else ["-loop", "1", "-framerate", str(fps), "-i", bg_file])

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-threads", ctx["ffmpeg_threads"], *bg_inputs]
    for m in members:
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", m["panel_img"]]
    for m in members:
        cmd += ["-i", m["voice"]]
    for f in extra_inputs:
        cmd += ["-i", f]
    cmd += ["-filter_complex", full_filter,
            "-map", "[outv]", "-map", "[aout]",
            "-c:v", ctx["encoder"], *ctx["enc_params"],
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-t", f"{total_dur:.6f}", "-pix_fmt", "yuv420p", out_file]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        ctx["manifest"].mark_done(key, out_file)
        return {"status": "success",
                "msg": f"seg{idx:04d} ({len(items)} panels)"}
    except subprocess.CalledProcessError as e:
        ctx["manifest"].mark_error(key, out_file, e.stderr)
        return {"status": "error",
                "msg": f"FFmpeg failed on segment {idx}: {e.stderr}"}
