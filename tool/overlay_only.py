"""Overlay mode: add a headline, phrase captions and music to an ALREADY-EDITED video.

No cutting, no stitching, no clip selection. The input video is used as it is
and the overlay layer is composed on top.

Usage:
  .venv/bin/python overlay_only.py <video_path> "<headline>" [options]

Examples:
  .venv/bin/python overlay_only.py ~/Movies/edit-1.mp4 "stop adding start subtracting"
  .venv/bin/python overlay_only.py edit.mp4 "the one fix that matters" \
      --music my-track.mp3 --music-volume 0.08 --output ~/Desktop/final.mp4
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config
from edit.probe import get_dimensions, get_duration, has_audio
from render.render_clip import render_clip


def _music_start(name: str) -> float:
    try:
        return float(json.loads(config.MUSIC_CONFIG.read_text()).get(name, 0))
    except Exception:
        return 0.0


def main():
    p = argparse.ArgumentParser(
        description="Add a headline, phrase captions and music to an already-edited video.")
    p.add_argument("video_path", help="Path to the already-edited input video")
    p.add_argument("headline", help="Headline text, shown exactly as typed")
    p.add_argument("--music", default=None,
                   help="File name in the music folder, or a full path (omit for no music)")
    p.add_argument("--music-volume", type=float, default=config.DEFAULT_MUSIC_VOLUME)
    p.add_argument("--no-captions", action="store_true",
                   help="Skip the captions (also skips transcription)")
    p.add_argument("--headline-duration", type=float, default=0.0,
                   help="Seconds the headline stays on screen (0 = whole clip)")
    p.add_argument("--headline-style", choices=["default", "pill"], default="default",
                   help="default = white text; pill = dark text in a white rounded box")
    p.add_argument("--mask-top", action="store_true",
                   help="Draw a solid black band at the top to cover a headline already in the video")
    p.add_argument("--output", default=None,
                   help="Output file (default: <output folder>/<input name>_overlay.mp4)")
    p.add_argument("--upload-folder", default=None,
                   help="Optional Google Drive folder id to upload the result to")
    args = p.parse_args()

    video = Path(args.video_path).expanduser().resolve()
    if not video.exists():
        sys.exit(f"Input not found: {video}")

    out = (Path(args.output).expanduser().resolve() if args.output
           else config.OUT_DIR / f"{video.stem}_overlay.mp4")
    if out == video:
        sys.exit("The output file must not be the input file.")
    out.parent.mkdir(parents=True, exist_ok=True)

    # 1. Probe orientation
    w, h = get_dimensions(video)
    orientation = "portrait" if h > w else "landscape"
    print(f"[probe] {video.name}: {w}x{h} ({orientation})")

    # 2. Transcribe (only when captions are wanted)
    captions = not args.no_captions
    if captions and not has_audio(video):
        print("[captions] the video has no audio track, so captions are skipped")
        captions = False
    if captions:
        from transcribe.whisper import transcribe
        print(f"[transcribe] {video.name}")
        t = transcribe(video)
        words = t["words"]
    else:
        words = []
    dur = get_duration(video)

    # 3. Resolve music (optional)
    music_path = None
    music_start = 0.0
    if args.music:
        music_path = config.resolve_music(args.music)
        if not music_path.exists():
            sys.exit(f"Music not found: {music_path}")
        music_start = _music_start(music_path.name)

    print(
        f"[render] {out.name} | headline={args.headline!r} "
        f"| duration={dur:.1f}s | headline-on-screen={args.headline_duration or 'full'}s "
        f"| captions={'ON' if captions else 'OFF'} "
        f"| music={args.music or 'OFF'}"
    )
    render_clip(
        stitched_video=video,
        headline=args.headline,
        words=words,
        duration_sec=dur,
        output_path=out,
        music_path=music_path,
        music_volume=args.music_volume,
        music_start_from_s=music_start,
        source_orientation=orientation,
        headline_duration_s=args.headline_duration,
        hide_captions=not captions,
        headline_style=args.headline_style,
        mask_top_for_headline=args.mask_top,
    )
    print(f"[done] {out}")

    if args.upload_folder:
        from drive.upload import upload_file
        result = upload_file(out, args.upload_folder, mime="video/mp4")
        print(f"[upload] {result.get('name')} -> {result.get('webViewLink')}")


if __name__ == "__main__":
    main()
