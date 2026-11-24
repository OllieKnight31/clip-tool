# Clip Tool for Claude Code

Give Claude Code a long video and get back short vertical clips, ready for Instagram, TikTok or Shorts.

## What it does

1. **Transcribes** the video on your Mac, with a timestamp for every word.
2. **Picks the best moments.** Claude reads the transcript, chooses the strongest self-contained moments and writes a short headline for each.
3. **Cuts on word boundaries**, skipping filler, restarts and dead air, with tiny audio fades so the joins do not click.
4. **Reframes to 1080 x 1920.** Portrait footage fills the frame. Landscape footage sits in the middle with the headline above and captions below.
5. **Adds captions** (three to four words at a time), the **headline**, and optional **music**.
6. **Saves the clips** to a folder, named after the source video and the topic.

It can also take a clip you have already edited and only add the headline, captions and music.

Your videos never leave your Mac. Transcription, cutting and rendering all run locally.

## What you need

| Item | Notes |
|---|---|
| A Mac | Built and tested on macOS with Apple Silicon. Not tested on Windows or Linux. |
| [Claude Code](https://claude.com/claude-code) | Installed and signed in. Claude picks the clips, so no separate API key is needed. |
| [Homebrew](https://brew.sh) | The easiest way to install the next three items. |
| ffmpeg | `brew install ffmpeg` |
| Node.js 18 or newer | `brew install node` |
| Python 3.9 or newer | Already on most Macs. Otherwise `brew install python`. |
| About 2 GB of free disk for the install | Renderer about 600 MB, headless browser about 200 MB, speech model about 460 MB, Python packages about 300 MB. Keep a few GB spare for rendering. |
| Internet for setup and the first run | After that everything works offline. |

Not included, and not needed to start: music (see "Music" below), an Anthropic API key, Google Drive access.

## Setup

1. Install the three tools if you do not have them:

   ```bash
   brew install ffmpeg node python
   ```

2. In Terminal, go to this folder and run the installer:

   ```bash
   cd /path/to/clip-tool-skill
   bash install.sh
   ```

   This copies the skill to `~/.claude/skills/clip-tool-skill`, copies the tool to `~/clip-tool`, then installs the transcription package and the renderer and runs a check. It takes a few minutes. It ends with a list of `[PASS]` lines and "All required checks passed."

   To put the tool somewhere else: `CLIP_TOOL_HOME=/some/folder bash install.sh`.

3. Restart Claude Code.

Running `install.sh` again later updates the program files. It never overwrites your settings (`config.env`), your brand voice notes, your music, your clips or the caches.

## First run

In Claude Code, say:

```
clip up /path/to/my-video.mp4
```

Claude will check the tool, transcribe the video, show you the clips it proposes (headline, timings, why), and render them once you are happy. The first transcription downloads the speech model (about 460 MB) and the first render downloads a headless browser (about 200 MB), so the first run is the slowest.

Finished clips are in `~/clip-tool/output`.

Other things to say:

- "Give me the five best clips from this video, under 45 seconds each"
- "Add a headline and captions to ~/Movies/my-edit.mp4, the headline is stop adding start subtracting"
- "The captions spell Acme wrong, fix it and render again"
- "Redo clip 2 but start one sentence later"

### Make it sound like you

Copy `~/clip-tool/selector/brand_voice.example.md` to `brand_voice.md` in the same folder and fill it in (who you are, who watches, phrases you are known for, how you like headlines). Claude reads it every time it picks clips. Or ask Claude: "help me write my brand voice file for the clip tool".

## Settings

Open `~/clip-tool/config.env` in any text editor. Every line is optional.

| Setting | What it changes |
|---|---|
| `CLIP_TOOL_OUT_DIR` | Where finished clips are saved. |
| `CLIP_TOOL_WHISPER_MODEL` | Speech model. `small.en` is the default (English). Use `small` or `medium` for other languages, `medium.en` for higher accuracy and slower runs. |
| `CLIP_TOOL_DEFAULT_MUSIC` | Music used on every clip. Empty means no music. |
| `CLIP_TOOL_MUSIC_VOLUME` | 0 to 1. Default 0.07, a quiet bed under speech. |
| `CLIP_TOOL_REMOTION_CONCURRENCY` | Lower to 1 if rendering makes the Mac struggle. |

## Music

No music is included. To add some, put an audio file in `~/clip-tool/music/` and set `CLIP_TOOL_DEFAULT_MUSIC=my-track.mp3` in `config.env`, or ask Claude to use it on a particular clip.

Use only music you have the right to publish: a royalty-free library, a track you have licensed, or your own. A chart song baked into the video file can get a post muted or removed. If you want a trending song, render without music and add the song inside the Instagram or TikTok app when you post.

## Optional extras

### Picking clips without Claude Code

`pick_clips.py` can pick clips through the Anthropic API for unattended runs. It needs an API key from [console.anthropic.com](https://console.anthropic.com) in `config.env` (`ANTHROPIC_API_KEY=...`) and one extra package:

```bash
~/clip-tool/.venv/bin/python -m pip install anthropic
~/clip-tool/.venv/bin/python ~/clip-tool/pick_clips.py /path/to/video.mp4 3
```

The model is set by `CLIP_TOOL_ANTHROPIC_MODEL` (default `claude-opus-5-5`). API use is billed to your Anthropic account. Never share `config.env` once a key is in it.

### Google Drive

The tool can download source videos from Google Drive and upload finished clips. This needs a one-off setup with your own Google account:

1. In [Google Cloud Console](https://console.cloud.google.com) create a project, enable the **Google Drive API**, and create an **OAuth client ID** of type **Desktop app**. Add yourself as a test user on the consent screen.
2. Download the client file and save it as `~/.config/clip-tool/google/google_credentials.json`.
3. Install the Drive packages: `~/clip-tool/.venv/bin/python -m pip install -r ~/clip-tool/requirements-drive.txt`
4. Put the id of the Drive folder for finished clips in `config.env` as `CLIP_TOOL_OUTPUT_FOLDER`. The id is the last part of the folder's web address.
5. The first Drive command opens your browser to sign in.

If that is more than you want to do, download the video to your Mac and use the normal route.

### Removing music already in a video

Setting `"strip_music": true` separates the voice from music that is already mixed into the source. It needs the demucs package, which downloads well over 1 GB: `~/clip-tool/.venv/bin/python -m pip install demucs`.

## Troubleshooting

Run the check first. It prints one line per requirement and the fix for anything missing:

```bash
~/clip-tool/.venv/bin/python ~/clip-tool/doctor.py
```

| Problem | Fix |
|---|---|
| `install.sh` stops with "ffmpeg is missing" or "Node.js is missing" | Run the `brew install` line it prints, then `bash install.sh` again. |
| Claude does not seem to know the skill | Restart Claude Code. Check that `~/.claude/skills/clip-tool-skill/SKILL.md` exists. |
| "No module named faster_whisper" or "faster-whisper is not installed" | The tool was run with the wrong Python. Use `~/clip-tool/.venv/bin/python`. If `.venv` does not exist, run `bash ~/clip-tool/setup.sh`. |
| "Could not load the speech model" | The first run needs internet and about 500 MB of free disk. Try again when online. |
| "The renderer is not installed" | `bash ~/clip-tool/setup.sh` |
| The first render fails while downloading the browser | Check the internet connection and run again. |
| Rendering is very slow, times out, or the Mac runs out of memory | Set `CLIP_TOOL_REMOTION_CONCURRENCY=1` in `config.env`. Close other heavy apps. Free up disk space. |
| "has no audio track" | The video has no sound, so there is nothing to transcribe. Overlay mode still works with captions switched off. |
| A caption has a wrong word or name | Tell Claude the correct spelling and ask it to render again. |
| Captions sit on top of subtitles already in the video | Ask Claude to crop the bottom of the source (`crop_bottom_px`). |
| The disk is filling up | Delete `~/clip-tool/.cache/edits` and `~/clip-tool/.cache/videos`. Your finished clips are not in there. |
| The words are wrong because the video is not in English | Set `CLIP_TOOL_WHISPER_MODEL=small` (or `medium`) in `config.env`. |

## What is in this folder

| Path | What it is |
|---|---|
| `install.sh` | Copies the skill and the tool into place and runs setup. |
| `skill/SKILL.md` | The instructions Claude Code follows. |
| `tool/` | The tool itself: transcription, cutting, rendering. |
| `tool/setup.sh` | Installs the Python packages and the renderer. Safe to run again. |
| `tool/doctor.py` | Checks that everything is in place. |
| `tool/config.example.env` | Every setting, with comments. |

## Uninstall

```bash
rm -rf ~/.claude/skills/clip-tool-skill ~/clip-tool
```

The speech model is kept in `~/.cache/huggingface`; delete that folder too if nothing else uses it.

## Licences of what gets installed

The installer downloads third-party software under its own licences: faster-whisper (MIT), FFmpeg (LGPL/GPL, installed by you through Homebrew), Remotion, and the Inter font (SIL Open Font Licence). Remotion is free for individuals and for companies of up to three people; larger companies need a paid Remotion licence. See [remotion.dev/license](https://remotion.dev/license).
