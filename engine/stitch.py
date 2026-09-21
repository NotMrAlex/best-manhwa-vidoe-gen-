"""Final stitching via FFmpeg concat demuxer (legacy logic, verbatim)."""

import logging
import os
import subprocess
from pathlib import Path

from .assets import AUDIO_EXTS

log = logging.getLogger("engine.stitch")


def combine_clips_fast(clips, output_file, build_dir="build",
                       ffmpeg_threads="4", bgm_vol_db=-18.0):
    valid_clips = [c for c in clips
                   if os.path.exists(c) and os.path.getsize(c) > 1000]
    if not valid_clips:
        log.warning("No valid clips to stitch for %s", output_file)
        return

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(build_dir).mkdir(parents=True, exist_ok=True)
    list_file = os.path.join(build_dir,
                             f"filelist_{Path(output_file).stem}.txt")

    with open(list_file, "w", encoding="utf-8") as f:
        for c in valid_clips:
            f.write(f"file '{os.path.abspath(c).replace(os.sep, '/')}'\n")

    bgm_files = [f for f in Path("assets/bgm").glob("*")
                 if f.suffix.lower() in AUDIO_EXTS]

    if bgm_files:
        cmd = [
            'ffmpeg', '-y', '-hwaccel', 'auto', '-hide_banner',
            '-loglevel', 'error', '-threads', ffmpeg_threads,
            '-f', 'concat', '-safe', '0', '-i', list_file,
            '-stream_loop', '-1', '-i', str(bgm_files[0].absolute()),
            '-filter_complex',
            f'[1:a]volume={bgm_vol_db}dB[m];[0:a][m]amix=inputs=2:duration=first[aout]',
            '-map', '0:v', '-map', '[aout]',
            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', output_file
        ]
    else:
        cmd = [
            'ffmpeg', '-y', '-hwaccel', 'auto', '-hide_banner',
            '-loglevel', 'error',
            '-f', 'concat', '-safe', '0', '-i', list_file,
            '-map', '0:v', '-map', '0:a',
            '-c', 'copy', output_file
        ]

    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        log.error("Concat Error: %s", e)
