"""CLI entry point. Zero-arg `python engine.py` == legacy behavior."""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from . import __version__
from . import assets, fonts
from .config import load_config
from .logging_setup import setup_logging
from .manifest import Manifest
from .render import detect_hardware, render_story
from .segments import clamp_size

log = logging.getLogger("engine.cli")

FOLDERS = [
    "output_panels", "audio", "build", "output",
    "assets/background", "assets/sfx", "assets/bgm", "assets/transitions"
]


def build_parser():
    p = argparse.ArgumentParser(
        prog="engine.py",
        description="Dank Engine Studio - manhwa/manga recap renderer")
    p.add_argument("--lang", default="all",
                   help="Language to render (e.g. english, spanish) or 'all'")
    p.add_argument("--profile", choices=["draft", "final"], default=None,
                   help="Quality profile: draft = fast preview encodes")
    p.add_argument("--jobs", type=int, default=None,
                   help="Parallel clip workers (overrides config workers)")
    p.add_argument("--fps", type=int, default=None,
                   help="Output frame rate (overrides config fps)")
    p.add_argument("--config", default="config.json", help="Config file path")
    p.add_argument("--story", default="story.json", help="Story JSON path")
    p.add_argument("--build-dir", default="build", help="Intermediate clip dir")
    p.add_argument("--output-dir", default="output", help="Final output dir")
    p.add_argument("--bench", type=int, default=None, metavar="N",
                   help="Benchmark mode: render N-panel slice with gates")
    p.add_argument("--synthetic", action="store_true",
                   help="Generate synthetic fixture assets for benchmarking")
    p.add_argument("--baseline", default=None,
                   help="Baseline dir for SSIM comparison during --bench")
    p.add_argument("--render-mode", choices=["clips", "segments"], default=None,
                   help="Long-form mode: per-clip (default) or 8-12 panel segments")
    p.add_argument("--segment-size", type=int, default=None,
                   help="Panels per segment, clamped 8-12 (segments mode only)")
    p.add_argument("--no-resume", action="store_true",
                   help="Ignore the render manifest (re-render everything)")
    p.add_argument("--skip-preflight", action="store_true",
                   help="Skip pre-render asset validation")
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {__version__}")
    return p


def run_pipeline(args, cfg, logger):
    """Full render pipeline. Returns a summary dict (used by bench harness)."""
    es = cfg["engine_settings"]
    fps = int(args.fps or es.get("fps", 60))
    workers = int(args.jobs or es.get("workers", 6))
    ffmpeg_threads = str(es.get("ffmpeg_threads", "4"))
    vols = cfg["audio_volumes_dB"]
    resume = bool(es.get("resume", True)) and not args.no_resume
    render_mode = args.render_mode or es.get("render_mode", "clips")
    segment_size = clamp_size(args.segment_size or es.get("segment_size", 10))
    profile = args.profile or es.get("profile", "final")

    if workers > 1:
        cpu = os.cpu_count() or 4
        cap = max(1, (cpu * 2) // workers)
        if int(ffmpeg_threads) > cap:
            logger.info("Auto-cap: ffmpeg_threads %s -> %d "
                        "(%d workers on %d cores)", ffmpeg_threads, cap,
                        workers, cpu)
            ffmpeg_threads = str(cap)

    story_path = args.story
    if not os.path.exists(story_path):
        logger.error("❌ ERROR: %s not found!", story_path)
        return {"ok": False, "reason": "story_not_found", "results": []}

    with open(story_path, "r", encoding="utf-8") as f:
        story = json.load(f)["story"]

    bg_file = assets.find_asset("assets/background", "background", assets.BG_EXTS)
    if not bg_file:
        bg_files = list(Path("assets/background").glob("*"))
        if not bg_files:
            logger.error("❌ ERROR: No background file found in assets/background/")
            return {"ok": False, "reason": "no_background", "results": []}
        bg_file = str(bg_files[0].absolute())

    langs = {k.replace("narration_", "") for item in story if item.get("render")
             for k in item.keys() if k.startswith("narration_")}
    if args.lang != "all":
        langs &= {args.lang}
    active_langs = sorted(l for l in langs if Path(f"audio/{l}").exists())

    font_path = None
    if cfg.get("captions", {}).get("enabled", True):
        try:
            font_path = str(fonts.resolve_font(cfg["captions"].get("font", "auto")))
            logger.info("Caption font: %s", font_path)
        except fonts.FontNotFoundError as e:
            logger.error("%s", e)
            return {"ok": False, "reason": "font_not_found", "results": []}

    encoder, enc_params = detect_hardware()
    if profile == "draft":
        fps = min(30, fps)
        enc_params = {
            "libx264": ["-preset", "ultrafast", "-crf", "28"],
            "h264_nvenc": ["-preset", "p1", "-cq", "30"],
            "h264_videotoolbox": ["-b:v", "4M"],
        }.get(encoder, enc_params)
    logger.info("\n🚀 ENGINE STARTED | ENCODER: %s | %d THREADS | %d FPS | "
                "MODE: %s | %s",
                encoder, workers, fps,
                f"{render_mode}/{segment_size}" if render_mode == "segments"
                else render_mode, profile.upper())

    ctx = {
        "cfg": cfg, "fps": fps, "workers": workers,
        "ffmpeg_threads": ffmpeg_threads, "vols": vols,
        "encoder": encoder, "enc_params": enc_params,
        "font_path": font_path, "build_dir": args.build_dir,
        "output_dir": args.output_dir, "resume": resume,
        "render_mode": render_mode,
        "segment_size": segment_size,
        "manifest": Manifest(os.path.join(args.build_dir, "manifest.json")),
    }

    if bool(es.get("preflight", True)) and not args.skip_preflight:
        report = assets.preflight(story, active_langs, bg_file, font_path,
                                  args.build_dir)
        if report["hard_failures"]:
            return {"ok": False, "reason": "preflight_failed",
                    "preflight": report, "results": []}

    t0 = time.time()
    results = render_story(story, active_langs, bg_file, ctx)
    wall_s = time.time() - t0

    errors = [r for r in results if r["status"] == "error"]
    err_path = Path(args.build_dir) / "error_report.json"
    with open(err_path, "w", encoding="utf-8") as f:
        json.dump(errors, f, indent=2)
    if errors:
        logger.error("%d clip errors — see %s", len(errors), err_path)

    return {"ok": not errors, "results": results, "wall_s": wall_s,
            "encoder": encoder, "fps": fps, "workers": workers}


def main(argv=None):
    try:
        from tqdm import tqdm  # noqa: F401
    except ImportError:
        print("[!] Missing 'tqdm' library. Please run: pip install tqdm")
        sys.exit(1)

    args = build_parser().parse_args(argv)
    for f in FOLDERS:
        Path(f).mkdir(parents=True, exist_ok=True)

    logger = setup_logging(args.build_dir)
    cfg = load_config(args.config)
    fonts.ensure_bundled_font()

    if args.bench:
        from . import benchmark
        report = benchmark.run_bench(args, cfg, logger)
        sys.exit(0 if report.get("pass") else 1)

    summary = run_pipeline(args, cfg, logger)
    if not summary.get("ok") and summary.get("reason") == "preflight_failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
