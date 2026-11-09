# TTS Pipeline

Turns the narration text in `story.json` into spoken audio files for your
recap videos and Shorts. It supports 75 languages and picks the best voice
engine for each one automatically.

- **English, Spanish, French, Hindi, Italian, Portuguese, Japanese, Chinese**
  use **Kokoro** — a free, local neural voice engine (no internet needed after
  the first run, uses your NVIDIA GPU if you have one).
- **Every other language** (Arabic, German, Russian, ...) uses **Edge-TTS** —
  free online Microsoft voices.

Every file is saved as loudness-matched, mono 48 kHz WAV, ready to drop into
a video editor.

---

## 1. What you need to install first

Only two things:

1. **Python 3.10 - 3.12** — from https://www.python.org/downloads/
   During installation, tick **"Add Python to PATH"**.
2. **FFmpeg** (for final audio processing) — from https://www.gyan.dev/ffmpeg/builds/
   Download the "release essentials" zip, unzip it anywhere, and add its `bin`
   folder to PATH. (If you already have ffmpeg, you can skip this.)

That's it. You do **not** need to know any terminal commands.

---

## 2. Download the project

If you got this as a zip file, unzip it to a folder on your computer
(for example `C:\tts`).

---

## 3. Install the app

1. Double-click **`install.bat`**.
2. Wait. It will:
   - Check that Python is installed.
   - Create a private environment folder called `tts_env`.
   - Detect your graphics card and install the right PyTorch build.
   - Install every Python dependency.
3. When it says **"Done!"**, close the window.

> The first run downloads the Kokoro model (~330 MB) from Hugging Face. This
> only happens once. After that, audio can be generated fully offline for the
> local languages.

---

## 4. Generate audio

1. Make sure `story.json` is in the same folder as `run.bat`.
2. Double-click **`run.bat`**.
3. Audio files appear in the **`audio`** folder.

Run it again any time — already-generated files are skipped automatically, so
only new or changed narration is produced.

---

## 5. Configure narration languages

Edit `story.json`. Each scene can contain text for as many languages as you
want, using the pattern `narration_<language>`:

```json
{
  "story": [
    {
      "render": true,
      "page": 1,
      "panel": 1,
      "narration_english": "He finally reached the summit.",
      "narration_spanish": "Por fin llegó a la cima.",
      "narration_arabic": "وصل أخيراً إلى القمة."
    }
  ]
}
```

To skip a scene, set `"render": false`.

The supported language names are listed in `config_tts.json` under `LANGUAGES`
(75 languages). The local (Kokoro) languages are listed under `LOCAL.languages`;
everything else uses Edge-TTS automatically.

---

## 6. Choose voices

Open `config_tts.json` (a plain text file) and edit:

- **Local voices** — under `LOCAL.languages`, change `"voice"`. English voices
  include `af_heart`, `af_bella`, `af_nicole`, `am_michael` and more. Spanish
  voices include `ef_dora` and `em_alex`, and so on.
- **Edge voices** — under `LANGUAGES`, change the value, e.g.
  `"english": "en-US-ChristopherNeural"` to another voice such as
  `"en-US-GuyNeural"`.
- **Speaking rate** — `AUDIO_RATE` (`"+0%"` is normal; `"+10%"` is faster).
- **Loudness** — `MASTERING.loudness_lufs` (`-14` matches YouTube's standard).

If you delete `config_tts.json`, the app recreates it with sensible defaults
on the next run.

---

## 7. Where audio is saved

```
audio/english/1_1.wav          - narration for page 1, panel 1
audio/english/intro/1_1.wav    - intro clips (if any)
audio/spanish/1_1.wav
audio/arabic/1_1.wav
```

Filenames use `page_panel` so you can match them to `page1_panel1` images in
your editor.

---

## 8. Troubleshooting

**"Python was not found"** — install Python (section 1) and re-run `install.bat`.

**"ffmpeg/ffprobe missing"** — install FFmpeg (section 1), reopen the terminal,
and run again.

**A language fails to generate** — check that the language name in
`story.json` exactly matches a key in `config_tts.json` `LANGUAGES`.

**Kokoro isn't used (everything goes to Edge)** — this can happen if the model
could not download on first run. Check your internet, then delete the `temp`
folder and run `run.bat` again.

**Want to regenerate one clip** — delete that file inside `audio/`, then run
`run.bat` again.

**More detail / logs** — open a terminal in the project folder and run:
```
tts_env\Scripts\python tts_engine.py
```