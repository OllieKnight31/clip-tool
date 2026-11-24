---
name: clip-tool-skill
description: Cuts long videos into short vertical clips ready for Instagram, TikTok or Shorts, or adds a headline, captions and music to a clip that is already edited. Transcribes on this Mac, picks the strongest moments, writes a headline per clip, cuts on word boundaries, reframes to 1080 x 1920, adds phrase captions and optional music, and saves the clips to a folder. Use when the user says "clip up this video", "cut my long-form into short-form", "make reels from this footage", "turn this podcast or call into clips", "add a headline to my video", "put captions on this video", "/clip-tool", "/clips".
---

# Clip Tool

Turns long videos (talks, calls, podcasts, vlogs) into short vertical clips: headline at the top, three to four word captions, optional music underneath. Everything runs on the user's Mac. No API key is needed: you (Claude) read the transcript and choose the clips.

**Tool folder:** `~/clip-tool` unless the user installed it elsewhere. If `~/clip-tool/process_local.py` does not exist, ask where the tool is, or tell them to run `install.sh` from the download. In every command below, `TOOL` means that folder and `PY` means `TOOL/.venv/bin/python`.

## Step 0: check the tool is ready (every session, takes two seconds)

```bash
~/clip-tool/.venv/bin/python ~/clip-tool/doctor.py
```

- If `.venv/bin/python` does not exist, setup has not been run: run `bash ~/clip-tool/setup.sh` (needs internet, a few minutes, about 1 GB of disk) and then the check again.
- Any `[FAIL]` line prints its own fix. Apply it, or tell the user exactly what to install (`brew install ffmpeg`, `brew install node`). Do not continue until the check ends with "All required checks passed."
- `[INFO]` lines are optional features. Do not block on them.

## Which mode

- **Mode A, clip a long video:** the user gives one or more long videos and wants short clips out of them.
- **Mode B, overlay only:** the user already has a finished short video and only wants the headline, captions and music added.

Ask for the video path if it was not given. Paths with spaces must be quoted. Videos must be files on this Mac (see "Google Drive" at the end for the optional Drive route).

## Mode A: clip a long video

### 1. Transcribe

```bash
~/clip-tool/.venv/bin/python ~/clip-tool/transcribe/whisper.py "/path/to/video.mp4" --text
```

This prints the transcript as timestamped lines and a `[transcript] <path>` line pointing at a JSON file with a timestamp for every word. The first ever run downloads the speech model (about 460 MB) and can take a few minutes; later runs of the same video are cached. A long video can take several minutes to transcribe, so run it in the background for anything over about ten minutes of footage.

If it reports 0 words, the video has no clear speech: tell the user and stop.

### 2. Pick the clips yourself

Read the transcript. If `~/clip-tool/selector/brand_voice.md` exists, read it first and follow it; otherwise read `brand_voice.example.md` in the same folder for the default criteria. If the user has not written their own brand voice file, offer once to write one with them (who they are, who watches, phrases they own, headline style).

Choose up to the number of clips the user asked for (default: the best 3, fewer if the material is thin). Never pad with weak clips.

Rules for every clip:

- 20 to 90 seconds after cutting. It must make sense with no other context.
- Starts on a strong opening line, never mid-sentence. Ends on a landed thought.
- Use `keep_segments` to skip filler, restarts, tangents and long pauses. Only join segments when the result reads as one continuous thought.
- **Every `start` and `end` must be a real word timestamp from the transcript JSON**: `start` is the `start` of the first word you keep, `end` is the `end` of the last word you keep. Open the JSON file and look the words up. Never estimate or round a timestamp from the printed lines.
- Headline: lowercase, 3 to 7 words, no emoji, no quote marks, no exclamation marks. A specific reframe or stake, not a stock phrase such as "the secret to" or "what nobody tells you".
- `topic_slug`: 2 to 5 lowercase words joined with hyphens, letters and digits only. Each clip of one video needs a different slug.

Skip, and say why: logistics chatter, screen-share troubleshooting, heavy crosstalk, anything that only makes sense with the rest of the video.

Show the user the list (headline, start to end, duration, one line on why) and let them change it before rendering, unless they asked you to go straight through.

### 3. Write the decisions file

Save it as `~/clip-tool/.cache/decisions_<short-name>.json`:

```json
{
  "videos": [
    {
      "source_path": "/full/path/to/video.mp4",
      "clips": [
        {
          "headline": "your bottleneck is not marketing",
          "topic_slug": "bottleneck-not-marketing",
          "keep_segments": [
            {"start": 276.23, "end": 302.21},
            {"start": 310.63, "end": 349.91}
          ]
        }
      ]
    }
  ]
}
```

Optional fields:

| Field | Where | Meaning |
|---|---|---|
| `music_path` | clip | File name in `~/clip-tool/music/` or a full path. `null` means no music for this clip. Left out, the default from `config.env` is used (none until the user sets one). |
| `music_volume` | clip | 0 to 1. Default 0.07, a quiet bed under speech. |
| `music_start_from_s` | clip | Second of the track to start from. |
| `bg_blur_fill` | clip or video | `true` fills the black bars of a landscape clip with a blurred copy of the picture. |
| `crop_bottom_px` | video | Pixels to trim off the bottom of the source, to remove subtitles already burned in. |
| `name_fixes` | video | `[{"heard": "Acmee", "correct": "Acme"}]` fixes a name the transcript always gets wrong. |
| `phrase_fixes` | video | `[{"at": 41.2, "heard": "the clothes", "correct": "the close"}]` fixes a misheard phrase near that second. |
| `word_fixes` | video | `[{"at": 12.3, "w": "Acme"}]` replaces the single word that starts at that second. |
| `strip_music` | clip or video | `true` removes music already in the source. Needs the optional demucs install; do not use unless the user asks. |

Read the captions back from the transcript before rendering: if a name or key word is misspelt, add a fix so it is not burned into the video wrong.

### 4. Cut and render

```bash
~/clip-tool/.venv/bin/python ~/clip-tool/process_local.py ~/clip-tool/.cache/decisions_<short-name>.json
```

Rendering is slower than real time (allow a few minutes per clip), so run it in the background for more than one or two clips. The very first render also downloads a headless browser (about 200 MB).

The run prints `[OK] <path>` per finished clip and ends with a line like `[done] 3 clip(s) rendered, 0 unchanged, 0 failed. Folder: ...`. Exit code 0 means every clip rendered.

- A clip that is unchanged since the last run is skipped. Change the decisions file and run again to re-render only what changed, or add `--force` to redo everything.
- A `[FAIL]` line names the clip and the reason. Fix the decisions file and run again; finished clips are not redone.

### 5. Check before you report

For each finished clip run:

```bash
ffprobe -v error -show_entries stream=codec_type,width,height,duration -of csv=p=0 "<clip path>"
```

Confirm a video stream of 1080 by 1920, an audio stream, and a duration that matches what you planned. Then tell the user where the clips are, with headline and duration per clip. Clips are named `<source-name>_<NN>_<topic-slug>.mp4` in the output folder (`~/clip-tool/output` unless changed in `config.env`).

## Mode B: overlay only

```bash
~/clip-tool/.venv/bin/python ~/clip-tool/overlay_only.py "/path/to/edited.mp4" "headline text here" \
    [--music my-track.mp3] [--music-volume 0.07] \
    [--no-captions] [--headline-duration 5] [--headline-style pill] [--mask-top] \
    [--output "/path/to/result.mp4"]
```

- The headline is drawn exactly as typed.
- Captions are transcribed from the video's own audio. `--no-captions` skips them (and skips transcription).
- `--headline-duration 5` shows the headline for the first 5 seconds only. `--headline-style pill` draws dark text in a white rounded box. `--mask-top` covers a headline already in the video with a black band.
- Without `--output` the result is `<output folder>/<input name>_overlay.mp4`. The input file is never changed.

Check the result with the same `ffprobe` command as above.

## How the clips look

- Canvas 1080 x 1920, 30 frames a second, H.264 video and AAC audio.
- Portrait source fills the frame (cropped to fit, never stretched), headline at the top over a soft dark gradient.
- Landscape or square source sits in the middle with black bars (or a blurred fill), headline in the bar above the picture, captions below it.
- Captions: up to four words at a time, white, bold, breaking at the end of sentences.
- Font: Inter, installed with the renderer. No internet is needed to render after setup.

## Music

No music ships with the tool. To use music the user puts an audio file in `~/clip-tool/music/` and either sets `CLIP_TOOL_DEFAULT_MUSIC=<file name>` in `~/clip-tool/config.env` or names it per clip. Remind them once to use only music they are licensed to publish; for a trending song the safe route is to render without music and add the song inside the Instagram or TikTok app when posting. Details are in `~/clip-tool/music/README.md`.

## Settings

All settings live in `~/clip-tool/config.env` (created by setup, never overwritten): output folder, speech model (`small.en` by default; use `small` or `medium` for languages other than English), default music and volume, render concurrency. Read `config.example.env` for the full list. Never print the contents of `config.env` if it contains a key.

## Optional extras (only if the user asks)

- **Unattended picking with an API key:** `PY ~/clip-tool/pick_clips.py "/path/to/video.mp4" 3` transcribes, asks the Anthropic API to pick clips and writes a decisions file. Needs `ANTHROPIC_API_KEY` in `config.env` and `PY -m pip install anthropic`. Inside Claude Code this is not needed.
- **Google Drive:** `batch_orchestrate.py` takes a decisions file where each video has `"drive_id"` instead of `"source_path"`, downloads the sources, renders, and uploads the clips to a `Done` folder inside the folder set as `CLIP_TOOL_OUTPUT_FOLDER`. It needs the user's own Google OAuth client; the README has the steps. If that is not set up, ask the user to download the video to the Mac and use Mode A.

## Troubleshooting

| What you see | What to do |
|---|---|
| `ffmpeg was not found` | `brew install ffmpeg`, then run again. |
| `The renderer is not installed` | `bash ~/clip-tool/setup.sh`. |
| `faster-whisper is not installed` | The command was run with the wrong Python. Use `~/clip-tool/.venv/bin/python`. |
| `Could not load the speech model` | First run needs internet and about 500 MB free. Try again when online. |
| `has no audio track` | The file has no sound. Mode A cannot work on it; Mode B works with `--no-captions`. |
| `segment N starts at ... but the video is only ...` | A timestamp in the decisions file is past the end of the video. Re-read the transcript JSON. |
| Render stops with a timeout or the Mac becomes very slow | Set `CLIP_TOOL_REMOTION_CONCURRENCY=1` in `config.env` and run again. Free up disk space: rendering needs a few GB of scratch space. |
| Captions show a wrong word | Add a `name_fixes`, `phrase_fixes` or `word_fixes` entry and run again. |
| Captions overlap subtitles already in the video | Set `crop_bottom_px` on the video (try 12 percent of the source height). |
| Disk is filling up | Delete `~/clip-tool/.cache/edits` and `~/clip-tool/.cache/videos`. Finished clips in the output folder are not affected. |
