# ⚡ DANK ENGINE STUDIO
**The Automated Manhwa & Manga Video Production Pipeline**

## 🧠 System Architecture Overview
Dank Engine Studio is a highly modular, multi-threaded Python pipeline designed to scrape, process, narrate, and render dynamic YouTube/TikTok recap videos with zero-shake FFmpeg math and multi-lingual RVC audio.

The system relies on a **"Bridge Architecture"** via a central UI (`studio.py`). Scripts do not call each other directly; instead, the Studio routes folder outputs sequentially to prevent data corruption.

---

## 📂 Core Directory Structure
The system relies on strict folder pathing. The Bridge automatically moves data between these nodes.
```text
/DankEngine/
├── assets/
│   ├── background/      # Contains looping 16:9 .mp4 background
│   ├── bgm/             # Contains background music
│   ├── sfx/             # Contains sound effects
│   └── transitions/     # Contains transition sounds
├── models/              # Contains .pth and .index RVC voice models
├── arrows/              # Contains custom UI arrow PNGs (thumbnail_studio.py)
├── config_tts.json      # Maps languages to Edge-TTS voice models
├── story.json           # The Master AI Script (Drives the entire engine)
└── ...[python scripts]

⚙️ The Pipeline Modules
1. Acquisition Node (app.py)
Function: Asynchronous DOM-scanning web scraper.
Logic: Uses Selenium to bypass Cloudflare, injects custom JS to unroll lazy-loaded images, and uses aiohttp to blast-download directories.
2. Vision Prep Node (slicer.py & stitcher.py)
Function: Prepares images for Vision LLM context.
slicer.py: Uses OpenCV Canny Edge Detection and CLAHE contrast to intelligently slice panels. It filters out scroll-padding, blank voids, and noise by checking standard deviation and absolute edge-pixel counts. Sub-slices massive panels dynamically.
stitcher.py: Groups 4 sequential panels into a single image with red borders and exact text labels (e.g., Panel: page1_panel2.jpg). Reduces LLM token cost by 75%.
3. Pre-Production Node (preprod_studio.py & thumbnail_studio.py)
Function: LLM API GUI for generating YouTube metadata and Clickbait Thumbnails.
Safety Bypass: Uses a "Code-Word Dictionary" to bypass API NSFW filters during prompt generation:
[CODE_B] -> impossibly large breasts, voluptuous figure
[CODE_H] -> thick thighs, wide hips
[CODE_C] -> extreme deep cleavage
[CODE_A] -> exposed muscular abs
thumbnail_studio.py: A local Pillow-based UI that maps user clicks to X/Y coordinates to auto-draw heavy-stroke text and rotated arrows over base images without needing external APIs.
4. Audio Node (tts_engine.py)
Function: Multi-lingual TTS & Voice Conversion.
Logic:
Reads story.json.
Generates Edge-TTS base audio.
Trims robotic silence using PyDub (split_on_silence), retaining 150ms to prevent word clipping.
Applies rvc-python to convert the voice. Includes PyTorch weights_only=False and _pytree runtime patches to support newer PyTorch environments.
5. Render Nodes (engine.py & manga_engine.py)
Function: Hardware-accelerated (NVENC) FFmpeg multiplexing.
Zero-Shake Math: Uses scale=target*2 before zoompan, then scales back down, to eliminate sub-pixel jitter.
Manhwa vs Manga:
engine.py (Manhwa): Crops panels to 80% vertical height (touching top/bottom) and uses sin() functions to slide left/right on odd/even panels.
manga_engine.py (Manga): Scales panels to fit entirely inside the 16:9 canvas with bounding boxes.
Captions: Uses Python's textwrap to calculate dynamic font-sizing based on string length, writes to a temp .txt file, and injects into FFmpeg's drawtext filter. Bypasses command-line string escaping crashes.
6. The Bridge (studio.py)
Function: The Master GUI and Folder Router.
Logic: Executes subprocess chains. Synchronizes output_panels to panels. Sorts final rendered videos into Upload_Queue/{Account_Name}/{Language}/. Cleans and moves all generated temp files into timestamped Archive/ folders.
📜 Master JSON Schema (story.json)
This is the core execution file required by the Audio and Render nodes.
code
JSON
{
  "story": [
    {
      "render": true,
      "page": 1,
      "panel": 1,
      "shorts": 1,
      "narration_english": "The string text.",
      "narration_spanish": "El texto.",
      "animation": "zoom_in",
      "sfx": "boom",
      "transition": "none"
    }
  ]
}
render: false signals the engine to completely skip processing the panel (used for scroll-padding removal).
shorts: X groups panels together. The FFmpeg concat demuxer will extract all panels matching shorts: 1 and compile them into a 9:16

---

## 🚀 Render Engine: Modes, Profiles & Benchmarks

`engine.py` (the Manhwa render node) is driven by `config.json` → `engine_settings` and CLI flags. Zero-arg `python engine.py` always reproduces legacy behavior.

### Render modes
- **`clips`** (default): one FFmpeg process per panel clip. First-class, fully supported.
- **`segments`**: renders 8–12 panels per FFmpeg invocation (long-form 16:9 only; shorts stay per-clip). Amortizes process/decoder startup and holds A/V sync via cumulative frame-compensated frame counts (panel boundaries within half a frame of the audio timeline). Enable via CLI or config:
  ```bash
  python engine.py --render-mode segments --segment-size 10
  ```
  Segment renders are memory-heavy (~1 GB each at 1080p60), so a **memory guard** auto-caps concurrent segment workers to fit available RAM (shorts keep full concurrency).

### Quality profiles
- **`final`** (default): production encodes.
- **`draft`**: fast preview encodes (x264 ultrafast/crf28, NVENC p1/cq30, fps capped at 30):
  ```bash
  python engine.py --profile draft
  ```

### Key CLI flags
| Flag | Purpose |
|---|---|
| `--lang LANG` | Render one language instead of all |
| `--jobs N` | Parallel workers (overrides config) |
| `--fps N` | Output frame rate (overrides config) |
| `--render-mode clips\|segments` | Long-form render strategy |
| `--segment-size N` | Panels per segment (clamped 8–12) |
| `--profile draft\|final` | Encode quality profile |
| `--bench N --synthetic` | Benchmark an N-panel slice with quality gates |
| `--baseline DIR` | SSIM-compare bench output against a baseline |
| `--no-resume` | Ignore the render manifest (re-render all) |
| `--skip-preflight` | Skip pre-render asset validation |

### Resume & preflight
- A manifest in the build dir tracks rendered clips/segments by content hash (params + input files); re-runs skip completed work in under a second. Deleting a clip re-renders only that clip.
- Preflight validates panels, audio, background, and caption font before rendering; hard failures abort with a report in the build dir.
- `ffmpeg_threads` is auto-capped to `2 × cores ÷ workers` to avoid thread oversubscription.

### Benchmark harness
```bash
python engine.py --bench 12 --synthetic --baseline build/baseline
```
Generates synthetic fixture assets (pages ≥ 9000, never colliding with real assets), renders a deterministic story slice, and runs quality gates: decode-clean, per-clip duration vs audio, segment composition (`segments` mode), total long-video duration, caption pixel burn-in, and SSIM vs baseline (≥ 0.98). Report: `build/bench/bench_report.json`. Exit code 0 = pass.