"""Optional: transcribe a local video and let the Anthropic API pick the clips.

Not needed inside Claude Code, where Claude reads the transcript and writes the
decisions file itself. This is for unattended runs and needs ANTHROPIC_API_KEY
in config.env plus the optional `anthropic` package.

Usage:
  .venv/bin/python pick_clips.py <video> [max_clips] [--out decisions.json]

Writes a decisions file ready for process_local.py and prints its path.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config


def build_decisions(video: Path, picked: dict) -> dict:
    clips = []
    for i, clip in enumerate(picked.get("clips", []), start=1):
        clips.append({
            "clip_index": i,
            "headline": clip["headline"],
            "topic_slug": clip.get("topic_slug") or f"clip-{i}",
            "keep_segments": clip["keep_segments"],
        })
    return {"videos": [{"source_path": str(video), "clips": clips}]}


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


def main():
    argv = sys.argv[1:]
    out = None
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 >= len(argv):
            sys.exit("--out needs a file name")
        out = Path(argv[i + 1]).expanduser()
        del argv[i:i + 2]
    if not argv or argv[0] in ("-h", "--help"):
        _usage(__doc__.strip())

    video = Path(argv[0]).expanduser().resolve()
    if not video.exists():
        sys.exit(f"Video not found: {video}")
    max_clips = int(argv[1]) if len(argv) > 1 else 3

    from transcribe.whisper import transcribe
    from selector.select import select_clips

    transcript = transcribe(video)
    if not transcript["words"]:
        sys.exit("No speech was found in this video, so there is nothing to clip.")
    picked = select_clips(transcript, max_clips=max_clips)
    decisions = build_decisions(video, picked)
    if not decisions["videos"][0]["clips"]:
        sys.exit("The model found nothing worth clipping in this video.")

    out = out or (config.CACHE_DIR / f"decisions_{video.stem}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(decisions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[decisions] {out}")
    print(f"Next: {sys.executable} {ROOT / 'process_local.py'} {out}")


if __name__ == "__main__":
    main()
