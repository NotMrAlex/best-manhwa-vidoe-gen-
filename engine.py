import os
import json
import subprocess
import platform
import sys
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

try:
    from tqdm import tqdm
except ImportError:
    print("[!] Missing 'tqdm' library. Please run: pip install tqdm")
    sys.exit(1)

# ==========================================
# 1. CONFIGURATION SYSTEM
# ==========================================
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "engine_settings": {
        "fps": 60,
        "workers": 6,             
        "ffmpeg_threads": "4"     
    },
    "audio_volumes_dB": {
        "voice": 3.0,             
        "sfx": -2.0,              
        "transition": 0.0,        
        "bgm": -18.0              
    }
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()
FPS = CONFIG["engine_settings"]["fps"]
WORKERS = CONFIG["engine_settings"]["workers"]
FFMPEG_THREADS = str(CONFIG["engine_settings"]["ffmpeg_threads"])
VOL = CONFIG["audio_volumes_dB"]

# ==========================================
# 2. AUTO-SETUP & UTILS
# ==========================================
FOLDERS = [
    "output_panels", "audio", "build", "output",
    "assets/background", "assets/sfx", "assets/bgm", "assets/transitions"
]
for f in FOLDERS: Path(f).mkdir(parents=True, exist_ok=True)

AUDIO_EXTS = ('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')

def detect_hardware():
    try:
        subprocess.check_output('nvidia-smi', shell=True, stderr=subprocess.DEVNULL)
        return "h264_nvenc", ["-preset", "p4", "-cq", "22"]
    except:
        if platform.system() == "Darwin":
            return "h264_videotoolbox", ["-b:v", "8M"]
        return "libx264", ["-preset", "superfast", "-crf", "20"]

ENCODER, ENC_PARAMS = detect_hardware()

def find_asset(folder_name, expected_name, valid_exts):
    folder = Path(folder_name)
    if not folder.exists(): return None
    for file in folder.iterdir():
        if file.stem.lower() == expected_name.lower():
            if file.suffix.lower() in valid_exts:
                return str(file.absolute())
    return None

def get_image_dims(img_path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", img_path]
    try:
        w, h = subprocess.check_output(cmd).decode().strip().split('x')
        return int(w), int(h)
    except:
        return 1080, 1920

# ==========================================
# 3. ZERO-SHAKE DYNAMIC RENDERER (MANHWA)
# ==========================================
def process_clip(task):
    item, lang, bg_file, aspect = task
    pid = f"{item['page']}_{item['panel']}"
    is_shorts = (aspect == "9:16")
    panel_num = int(item.get('panel', 1))

    expected_img_name = f"page{item['page']}_panel{item['panel']}"
    panel_img = find_asset("output_panels", expected_img_name, IMAGE_EXTS)
    voice_audio = find_asset(f"audio/{lang}", pid, AUDIO_EXTS)
    
    if not panel_img or not voice_audio:
        return {"status": "error", "msg": f"Missing Assets for {pid} ({aspect})"}

    aspect_tag = "916" if is_shorts else "169"
    out_file = f"build/{lang}_{aspect_tag}_{pid}.mp4"

    dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", voice_audio]
    dur = float(subprocess.check_output(dur_cmd).decode().strip())
    
    frames = int(dur * FPS) + 15 
    
    anim = item.get("animation", "zoom_in")
    ease = f"(1-cos(PI*on/{frames}))/2"  
    
    z_in = f"1.0+(0.15*{ease})"
    z_out = f"1.15-(0.15*{ease})"
    zoom_expr = z_in if anim == "zoom_in" else z_out

    base_crop = "crop=iw:ih*0.8:0:ih*0.1"

    if is_shorts:
        if anim == "scroll":
            ease_t = f"(1-cos(PI*t/{dur}))/2"
            v_filter = f"[1:v]{base_crop},scale=1080:-2:flags=bicubic,pad=1080:max(ih\\,1920):0:0:color=black[p_base];[p_base]crop=1080:1920:0:'max(0, ih-1920)*{ease_t}',setsar=1[outv]"
        else:
            scale_ratio = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            v_filter = f"[1:v]{base_crop},{scale_ratio},scale=2160:3840:flags=bicubic,zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':d={frames}:s=2160x3840:fps={FPS},scale=1080:1920:flags=bicubic,setsar=1[outv]"
    else:
        bg_filter = "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[bg];"
        orig_w, orig_h = get_image_dims(panel_img)
        crop_h = orig_h * 0.8
        target_w = int(1080 * (orig_w / crop_h))
        target_w += target_w % 2 
        
        slide_dur = 0.5
        cx = "(1920-w)/2"
        dist = "(1920/2+w/2)"
        ease_slide = f"sin(min(t/{slide_dur}\\,1)*(PI/2))"
        
        if panel_num % 2 == 0:
            slide_x = f"max({cx}\\, 1920 - {dist}*{ease_slide})"
        else:
            slide_x = f"min({cx}\\, -w + {dist}*{ease_slide})"
            
        if anim == "scroll":
            ease_t = f"(1-cos(PI*t/{dur}))/2"
            scroll_h = int(target_w * (orig_h / orig_w))
            scroll_h += scroll_h % 2
            v_filter = f"{bg_filter}[1:v]{base_crop},scale={target_w}:{scroll_h}:flags=bicubic,pad={target_w}:max(ih\\,1080):0:0:color=black,crop={target_w}:1080:0:'max(0, ih-1080)*{ease_t}'[p_anim];[bg][p_anim]overlay=x='{slide_x}':y='(1080-h)/2':shortest=1,setsar=1[outv]"
        else:
            uw, uh = target_w * 2, 1080 * 2
            v_filter = f"{bg_filter}[1:v]{base_crop},scale={uw}:{uh}:flags=bicubic,zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':d={frames}:s={uw}x{uh}:fps={FPS},scale={target_w}:1080:flags=bicubic[p_anim];[bg][p_anim]overlay=x='{slide_x}':y='(1080-h)/2':shortest=1,setsar=1[outv]"

    # ==========================================
    # 🆕 DYNAMIC ONE-LINE CAPTIONS (LONG-FORM ONLY)
    # ==========================================
    raw_text = item.get(f"narration_{lang}", "")
    
    if not is_shorts and raw_text and str(raw_text).strip().lower() not in ["none", "null", ""]:
        safe_text = str(raw_text).strip().replace("'", "\u2019").replace(":", "\\:").replace(",", "\\,").replace("%", "\\%")
        
        # Calculate dynamic font size to keep it on a single line!
        char_count = max(len(safe_text), 1)
        font_size = min(55, max(25, int(3200 / char_count)))
        
        # Write flat single line to text file
        txt_path = os.path.abspath(f"build/cap_{lang}_{pid}.txt").replace('\\', '/')
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(safe_text)
            
        ff_txt_path = txt_path.replace(":", "\\:")
        f_path = "impact.ttf" if os.path.exists("impact.ttf") else "C:/Windows/Fonts/arialbd.ttf"
        f_path = f_path.replace(":", "\\:")
        
        text_filter = f"drawtext=fontfile='{f_path}':textfile='{ff_txt_path}':fontcolor=0xFFE600:fontsize={font_size}:bordercolor=black:borderw=4:x=(w-text_w)/2:y=h-text_h-80"
        
        v_filter = v_filter.replace("[outv]", "[prenotext]") + f";[prenotext]{text_filter}[outv]"

    # --- FINAL MIXING ---
    is_bg_video = bg_file.lower().endswith(('.mp4', '.mov', '.webm', '.mkv', '.avi'))
    bg_inputs = ["-stream_loop", "-1", "-i", bg_file] if is_bg_video else ["-loop", "1", "-framerate", str(FPS), "-i", bg_file]

    cmd = [
        "ffmpeg", "-y", "-hwaccel", "auto", "-hide_banner", "-loglevel", "error", "-threads", FFMPEG_THREADS,
        *bg_inputs, "-loop", "1", "-framerate", str(FPS), "-i", panel_img, "-i", voice_audio
    ]

    amix_str = f"[2:a]volume={VOL['voice']}dB[v]" 
    a_sources = ["[v]"]
    idx = 3

    if item.get("sfx", "none") != "none":
        sfx_file = find_asset("assets/sfx", item['sfx'], AUDIO_EXTS)
        if sfx_file:
            cmd.extend(["-i", sfx_file])
            amix_str += f";[{idx}:a]volume={VOL['sfx']}dB[sfx]"
            a_sources.append("[sfx]")
            idx += 1

    if item.get("transition", "none") != "none":
        tr_file = find_asset("assets/transitions", item['transition'], AUDIO_EXTS)
        if tr_file:
            cmd.extend(["-i", tr_file])
            amix_str += f";[{idx}:a]volume={VOL['transition']}dB[tr]"
            a_sources.append("[tr]")
            idx += 1

    if len(a_sources) > 1:
        amix_str += f";{''.join(a_sources)}amix=inputs={len(a_sources)}:duration=first[aout]"
    else:
        amix_str = f"[2:a]volume={VOL['voice']}dB[aout]"

    full_filter = f"{v_filter};{amix_str}"

    cmd.extend([
        "-filter_complex", full_filter,
        "-map", "[outv]", "-map", "[aout]",
        "-c:v", ENCODER, *ENC_PARAMS, 
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", 
        "-t", str(dur), "-pix_fmt", "yuv420p", out_file
    ])

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"status": "success", "msg": f"{pid} ({aspect})"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "msg": f"FFmpeg failed on {pid} ({aspect}): {e.stderr}"}

# ==========================================
# 4. STITCHER ENGINE
# ==========================================
def combine_clips_fast(clips, output_file):
    valid_clips = [c for c in clips if os.path.exists(c) and os.path.getsize(c) > 1000]
    if not valid_clips: return

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    list_file = os.path.join("build", "filelist.txt")
    
    with open(list_file, "w", encoding="utf-8") as f:
        for c in valid_clips:
            f.write(f"file '{os.path.abspath(c).replace(os.sep, '/')}'\n")

    bgm_files = [f for f in Path("assets/bgm").glob("*") if f.suffix.lower() in AUDIO_EXTS]

    if bgm_files:
        cmd = [
            'ffmpeg', '-y', '-hwaccel', 'auto', '-hide_banner', '-loglevel', 'error', '-threads', FFMPEG_THREADS,
            '-f', 'concat', '-safe', '0', '-i', list_file,
            '-stream_loop', '-1', '-i', str(bgm_files[0].absolute()),
            '-filter_complex', f'[1:a]volume={VOL["bgm"]}dB[m];[0:a][m]amix=inputs=2:duration=first[aout]',
            '-map', '0:v', '-map', '[aout]',
            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', output_file
        ]
    else:
        cmd = [
            'ffmpeg', '-y', '-hwaccel', 'auto', '-hide_banner', '-loglevel', 'error', 
            '-f', 'concat', '-safe', '0', '-i', list_file, 
            '-map', '0:v', '-map', '0:a',
            '-c', 'copy', output_file
        ]

    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"[!] Concat Error: {e}")

# ==========================================
# 5. MASTER ORCHESTRATOR
# ==========================================
def main():
    print(f"\n🚀 ENGINE STARTED | ENCODER: {ENCODER} | {WORKERS} THREADS | {FPS} FPS")
    
    if not os.path.exists("story.json"):
        print("❌ ERROR: story.json not found!")
        return

    with open("story.json", "r", encoding="utf-8") as f:
        story = json.load(f)["story"]

    bg_file = find_asset("assets/background", "background", ['.mp4', '.mov', '.webm', '.jpg', '.png', '.jpeg'])
    if not bg_file:
        bg_files = list(Path("assets/background").glob("*"))
        if not bg_files:
            print("❌ ERROR: No background file found in assets/background/")
            return
        bg_file = str(bg_files[0].absolute())

    langs = {k.replace("narration_", "") for item in story if item.get("render") for k in item.keys() if k.startswith("narration_")}

    for lang in langs:
        if not Path(f"audio/{lang}").exists():
            continue
            
        print(f"\n🎬 PROCESSING LANGUAGE: {lang.upper()}")
        
        jobs = []
        long_clips = []
        shorts_groups = {}

        for item in story:
            if not item.get("render"): continue
            pid = f"{item['page']}_{item['panel']}"
            
            jobs.append((item, lang, bg_file, "16:9"))
            long_clips.append(os.path.join("build", f"{lang}_169_{pid}.mp4"))

            short_id = item.get("shorts")
            if isinstance(short_id, int) and short_id > 0:
                jobs.append((item, lang, bg_file, "9:16"))
                if short_id not in shorts_groups:
                    shorts_groups[short_id] = []
                shorts_groups[short_id].append(os.path.join("build", f"{lang}_916_{pid}.mp4"))

        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            results = list(tqdm(executor.map(process_clip, jobs), total=len(jobs), desc="Rendering", unit="clip", colour="green"))
            for res in results:
                if res["status"] == "error": print(f"\n{res['msg']}")

        print("⏳ Stitching final long video...")
        long_output = f"output/{lang}/long_video.mp4"
        combine_clips_fast(long_clips, long_output)
        print(f"🎉 EXPORTED: {long_output}")

        for sid, clips in shorts_groups.items():
            print(f"⏳ Stitching short #{sid}...")
            short_output = f"output/{lang}/shorts/short_{sid}.mp4"
            combine_clips_fast(clips, short_output)
            print(f"🎉 EXPORTED: {short_output}")

    print("\n✅ ALL PROCESSES FINISHED.")

if __name__ == "__main__":
    main()