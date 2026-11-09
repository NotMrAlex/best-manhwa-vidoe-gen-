# Dank Engine Studio

Turns your manhwa / manga panels and narration text into finished recap
videos and vertical Shorts automatically. You give it panels and words;
it gives you ready-to-post videos.

---

## 1. What you need to install first

Only two things:

1. **Python 3.10 - 3.12** — from https://www.python.org/downloads/
   During installation, tick **"Add Python to PATH"**.
2. **FFmpeg** (creates the video) — from https://www.gyan.dev/ffmpeg/builds/
   Download the "release essentials" zip, unzip it anywhere, and add its
   `bin` folder to PATH. (If you already have ffmpeg, skip this.)

That's it. You do **not** need to know any terminal commands.

---

## 2. Download the project

If you got this as a zip file, unzip it to a folder on your computer
(for example `C:\DankEngine`).

---

## 3. Install the app

1. Double-click **`install.bat`**.
2. Wait. It will:
   - Check that Python is installed.
   - Check for FFmpeg and tell you where to get it if it is missing.
   - Create a private environment folder called `engine_env`.
   - Install every dependency.
3. When it says **"Done!"**, close the window.

---

## 4. Make a video

1. Put your files in the right folders (see section 5).
2. Double-click **`engine.bat`**.
3. Finished videos appear in the **`output`** folder.

Run it again any time — already-finished clips are skipped automatically,
so only new or changed panels are rendered again.

---

## 5. What each folder is for

```
story.json               The script. Each panel's narration text lives here.
                         (It is already filled in — you only edit it if you
                         want to change the words.)
output_panels/           Your panel images, named like page1_panel1.jpg,
                         page1_panel2.jpg, page2_panel1.jpg ...
audio/                   Narration audio, one folder per language:
                           audio/english/1_1.wav
                           audio/spanish/1_1.wav
assets/
  background/            Looping background video (background.mp4)
  bgm/  sfx/  transitions/  Background music, sound effects, transitions
  fonts/                 Caption font (added automatically if missing)
output/                  Finished videos appear here
build/                   Temporary files (safe to ignore)
```

Every folder is created for you on the first run.

---

## 6. Understand story.json

Each scene looks like this:

```json
{
  "render": true,
  "page": 1,
  "panel": 1,
  "narration_english": "He finally reached the summit.",
  "narration_spanish": "Por fin llegó a la cima.",
  "animation": "zoom_in",
  "sfx": "boom",
  "transition": "none"
}
```

- Set `"render": false` to skip a panel.
- `narration_<language>` — the words spoken for each language. A language is
  rendered only if there is matching audio in the `audio` folder.
- `animation` — how the panel moves (`zoom_in`, `zoom_out`, and so on).
- `sfx` and `transition` — optional sound effects and transition sounds.

---

## 7. Troubleshooting

**"Python was not found"** — install Python (section 1) and re-run `install.bat`.

**"ffmpeg missing"** — install FFmpeg (section 1), reopen the terminal or
restart your computer, then run again.

**A panel is skipped or missing in the video** — check that the image file in
`output_panels` is named exactly `page<page>_panel<panel>` and that narration
audio exists in `audio/<language>/<page>_<panel>.wav`.

**Videos render but have no captions** — leave `assets/fonts` alone; the font
is downloaded automatically on first run. Check your internet connection and
delete any empty font file in that folder, then run again.

**Want to redo just one clip** — delete that clip's files inside `build/`,
then run `engine.bat` again.

**More detail / logs** — open `build/engine.log` for a full record of the last
run.