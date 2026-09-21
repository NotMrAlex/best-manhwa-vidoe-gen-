"""Benchmark harness, synthetic fixtures, and quality gates.

Usage:
    python -m engine.benchmark fixture [--n 12] [--seed 7]
    python -m engine.benchmark compare DIR_A DIR_B [--min-ssim 0.98]
"""

import argparse
import json
import logging
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("engine.benchmark")

FIXTURE_PAGE_BASE = 9000
BENCH_DIR = Path("build/bench")
SSIM_THRESHOLD = 0.98


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def ffprobe_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)])
    return float(out.decode().strip())


def generate_fixture(n=12, seed=7, langs=("english",),
                     story_path=str(BENCH_DIR / "story_fixture.json")):
    """Generate synthetic panels/audio/bg/sfx + a story file.

    Panels use page numbers >= 9000 so they never collide with real assets.
    Shared assets (background, sfx, transitions) are only created if missing
    so real user assets are never clobbered.
    """
    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    Path("output_panels").mkdir(parents=True, exist_ok=True)
    for lang in langs:
        Path(f"audio/{lang}").mkdir(parents=True, exist_ok=True)
    for d in ("assets/background", "assets/sfx", "assets/transitions"):
        Path(d).mkdir(parents=True, exist_ok=True)
    Path(story_path).parent.mkdir(parents=True, exist_ok=True)

    for i in range(n):
        page = FIXTURE_PAGE_BASE + i
        img = Image.new("RGB", (1080, 1920), (rnd.randrange(40, 120),
                                              rnd.randrange(20, 80),
                                              rnd.randrange(60, 140)))
        d = ImageDraw.Draw(img)
        for _ in range(40):
            x0, y0 = rnd.randrange(0, 900), rnd.randrange(0, 1800)
            x1 = x0 + rnd.randrange(40, 300)
            y1 = y0 + rnd.randrange(40, 300)
            d.rectangle([x0, y0, x1, y1],
                        fill=(rnd.randrange(256), rnd.randrange(256),
                              rnd.randrange(256)), outline=(0, 0, 0))
        d.text((40, 900), f"PANEL {page}", fill=(255, 255, 0))
        img.save(f"output_panels/page{page}_panel1.jpg", quality=92)
        for lang in langs:
            wav = f"audio/{lang}/{page}_1.wav"
            dur = 2.0 + (i % 3) * 0.5
            freq = 280 + i * 25
            _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                  "-f", "lavfi", "-i",
                  f"sine=frequency={freq}:duration={dur}",
                  "-ar", "44100", wav])

    bg = Path("assets/background/background.mp4")
    if not bg.exists():
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
              "-f", "lavfi", "-i",
              "testsrc2=size=1920x1080:rate=30:duration=15",
              "-pix_fmt", "yuv420p", str(bg)])
    sfx = Path("assets/sfx/boom.wav")
    if not sfx.exists():
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
              "-f", "lavfi", "-i", "sine=frequency=70:duration=0.5",
              "-ar", "44100", str(sfx)])
    tr = Path("assets/transitions/swoosh.wav")
    if not tr.exists():
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
              "-f", "lavfi", "-i", "sine=frequency=1200:duration=0.4",
              "-ar", "44100", str(tr)])

    anims = ["zoom_in", "zoom_out", "scroll"]
    story = []
    for i in range(n):
        page = FIXTURE_PAGE_BASE + i
        story.append({
            "render": (i % 7 != 6),
            "page": page,
            "panel": 1,
            "shorts": (1 + i // 4) if i < 8 else 0,
            "narration_english": f"Panel {i} drops into the neon city as our "
                                 f"hero laughs at danger once more.",
            "animation": anims[i % 3],
            "sfx": "boom" if i % 3 == 0 else "none",
            "transition": "swoosh" if i % 4 == 0 else "none",
            "plot_summary": "synthetic benchmark fixture",
        })
    with open(story_path, "w", encoding="utf-8") as f:
        json.dump({"story": story}, f, indent=2)
    log.info("Fixture written: %s (%d panels)", story_path, n)
    return story_path


def ssim_score(path_a, path_b):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path_a),
                        "-i", str(path_b), "-lavfi", "ssim", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"All:([0-9.]+)", p.stderr)
    return float(m.group(1)) if m else None


def compare_dirs(dir_a, dir_b):
    """Compare same-named .mp4 files (recursive) between two dirs."""
    dir_a, dir_b = Path(dir_a), Path(dir_b)
    results = {}
    skipped = []
    for fa in sorted(dir_a.rglob("*.mp4")):
        rel = fa.relative_to(dir_a)
        if fa.stat().st_size == 0:
            skipped.append(str(rel))
            continue
        fb = dir_b / rel
        if not fb.exists():
            results[str(rel)] = {"ssim": None, "error": "missing in B"}
            continue
        results[str(rel)] = {"ssim": ssim_score(fa, fb)}
    return results, skipped


def compare_report(dir_a, dir_b, min_ssim=SSIM_THRESHOLD):
    res, skipped = compare_dirs(dir_a, dir_b)
    scores = [v["ssim"] for v in res.values() if v.get("ssim") is not None]
    missing = [k for k, v in res.items() if v.get("ssim") is None]
    report = {
        "compared": len(scores),
        "missing": missing,
        "no_baseline": skipped,
        "min": min(scores) if scores else None,
        "mean": (sum(scores) / len(scores)) if scores else None,
        "files": res,
        "pass": bool(scores) and not missing and min(scores) >= min_ssim,
    }
    return report


def gate_decode_clean(files):
    bad = {}
    for f in files:
        p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f),
                            "-f", "null", "-"], capture_output=True, text=True)
        if p.stderr.strip():
            bad[str(f)] = p.stderr.strip()[:300]
    return {"pass": not bad, "errors": bad}


def gate_durations(clip_dir, tol=0.05):
    """Every clip {lang}_{tag}_{page}_{panel}.mp4 must match its audio length."""
    from . import assets
    mismatches = {}
    checked = 0
    for clip in sorted(Path(clip_dir).glob("*.mp4")):
        parts = clip.stem.split("_")
        if len(parts) < 4:
            continue
        lang = parts[0]
        pid = "_".join(parts[2:])
        audio = assets.find_asset(f"audio/{lang}", pid, assets.AUDIO_EXTS)
        if not audio:
            continue
        try:
            delta = abs(ffprobe_duration(clip) - ffprobe_duration(audio))
        except Exception as e:
            mismatches[clip.name] = f"probe failed: {e}"
            continue
        checked += 1
        if delta > tol:
            mismatches[clip.name] = f"delta {delta:.3f}s"
    return {"pass": not mismatches and checked > 0, "checked": checked,
            "mismatches": mismatches}


def gate_caption_pixels(clip, t=1.0, min_pixels=150):
    """Extract a frame and verify yellow caption pixels are actually burned in."""
    from PIL import Image
    frame = Path(clip).with_suffix(".gate.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t),
                    "-i", str(clip), "-frames:v", "1", str(frame)],
                   capture_output=True, check=True)
    count = 0
    with Image.open(frame) as im:
        im = im.convert("RGB")
        for r, g, b in im.getdata():
            if r > 200 and g > 200 and b < 100:
                count += 1
    frame.unlink(missing_ok=True)
    return {"pass": count >= min_pixels, "yellow_pixels": count}


def run_bench(args, cfg, logger):
    """Render a deterministic story slice and run all quality gates."""
    from .cli import run_pipeline

    n = int(args.bench)
    if args.synthetic:
        args.story = generate_fixture(max(n, 12))
    with open(args.story, encoding="utf-8") as f:
        story = json.load(f)["story"]

    renderable = [i for i in story if i.get("render")]
    step = max(1, len(renderable) // max(n, 1))
    picked = renderable[::step][:n]
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    slice_path = BENCH_DIR / "story_bench_slice.json"
    with open(slice_path, "w", encoding="utf-8") as f:
        json.dump({"story": picked}, f, indent=2)

    args.story = str(slice_path)
    args.build_dir = str(BENCH_DIR / "clips")
    args.output_dir = str(BENCH_DIR / "output")
    shutil.rmtree(args.build_dir, ignore_errors=True)
    shutil.rmtree(args.output_dir, ignore_errors=True)

    t0 = time.time()
    summary = run_pipeline(args, cfg, logger)
    wall_s = time.time() - t0

    clips = sorted(Path(args.build_dir).glob("*.mp4"))
    outputs_dir = Path(args.output_dir)
    stitched = sorted(outputs_dir.rglob("*.mp4")) if outputs_dir.exists() else []

    gates = {}
    gates["decode_clean"] = gate_decode_clean(clips + stitched)
    gates["durations"] = gate_durations(args.build_dir)
    long_clips = [c for c in clips if "_169_" in c.name]
    if long_clips:
        gates["captions_burned"] = gate_caption_pixels(long_clips[0])
    if args.baseline:
        base = Path(args.baseline)
        ssim = {}
        if (base / "clips").exists():
            ssim["clips"] = compare_report(base / "clips", args.build_dir)
        if (base / "output").exists():
            ssim["output"] = compare_report(base / "output", args.output_dir)
        gates["ssim_vs_baseline"] = ssim

    errors = [r for r in summary.get("results", []) if r["status"] == "error"]

    def _gate_ok(g):
        if not isinstance(g, dict):
            return False
        if "pass" in g:
            return bool(g["pass"])
        return all(_gate_ok(v) for v in g.values())

    gate_pass = all(_gate_ok(g) for g in gates.values())
    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_sha": _git_sha(),
        "story": args.story,
        "panels_benched": len(picked),
        "wall_s": round(wall_s, 2),
        "clips_ok": sum(1 for r in summary.get("results", [])
                        if r["status"] == "success"),
        "clips_skipped": sum(1 for r in summary.get("results", [])
                             if r["status"] == "skipped"),
        "clips_error": len(errors),
        "errors": errors[:20],
        "gates": gates,
        "pass": gate_pass and not errors and summary.get("ok", False),
    }
    report_path = BENCH_DIR / "bench_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info("Bench report: %s | PASS=%s | wall=%.1fs",
                report_path, report["pass"], wall_s)
    return report


def _git_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="engine.benchmark")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fx = sub.add_parser("fixture")
    fx.add_argument("--n", type=int, default=12)
    fx.add_argument("--seed", type=int, default=7)
    cp = sub.add_parser("compare")
    cp.add_argument("dir_a")
    cp.add_argument("dir_b")
    cp.add_argument("--min-ssim", type=float, default=SSIM_THRESHOLD)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.cmd == "fixture":
        print(generate_fixture(args.n, args.seed))
    elif args.cmd == "compare":
        report = compare_report(args.dir_a, args.dir_b, args.min_ssim)
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
