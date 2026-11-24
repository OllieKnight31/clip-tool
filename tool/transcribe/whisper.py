"""faster-whisper wrapper with word-level timestamps.

Run directly to transcribe one video and print where the transcript was saved:
  .venv/bin/python transcribe/whisper.py <video> [--text]
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

CACHE_DIR = config.CACHE_DIR / "transcripts"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# small.en is fast enough on CPU and accurate enough for English talking-head
# footage. Change CLIP_TOOL_WHISPER_MODEL in config.env for other languages or
# higher accuracy.
MODEL_SIZE = config.WHISPER_MODEL


def cache_path(video_path: Path) -> Path:
    """Where this video's transcript is cached.

    The key covers the file's full path, size and modified time as well as the
    model, so two different videos that share a name (every phone produces an
    IMG_0001.MOV) never pick up each other's transcript, and switching model
    never returns the previous model's words.
    """
    video_path = Path(video_path).expanduser().resolve()
    st = video_path.stat()
    key = f"{video_path}|{st.st_size}|{int(st.st_mtime)}|{MODEL_SIZE}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return CACHE_DIR / f"{video_path.stem}.{digest}.json"


def transcribe(video_path: Path) -> dict:
    """Transcribe with word-level timestamps. Returns:
    {
      'language': str,
      'duration': float,
      'words': [{'w': str, 'start': float, 'end': float}, ...],
      'text': str,  # full text
      'segments': [{'start','end','text'}, ...],  # sentence-ish segments
    }
    Cached under <cache>/transcripts/.
    """
    video_path = Path(video_path).expanduser().resolve()
    if not video_path.exists():
        raise SystemExit(f"Video not found: {video_path}")
    cache = cache_path(video_path)
    if cache.exists():
        print(f"[transcript-cache] {cache.name}")
        return json.loads(cache.read_text(encoding="utf-8"))

    print(f"[transcribing] {video_path.name} (model={MODEL_SIZE})")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit(
            "faster-whisper is not installed in this Python. Run setup.sh in the tool "
            "folder, then use .venv/bin/python to run the tool."
        )
    try:
        model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    except Exception as e:
        raise SystemExit(
            f"Could not load the speech model '{MODEL_SIZE}': {type(e).__name__}: {e}\n"
            "The model is downloaded once on first use, so the first run needs an "
            "internet connection and about 500 MB of free disk for small.en."
        )

    segments_iter, info = model.transcribe(
        str(video_path),
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        beam_size=5,
        condition_on_previous_text=False,
    )

    words = []
    segments = []
    full_text_parts = []
    for seg in segments_iter:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        full_text_parts.append(seg.text.strip())
        for w in (seg.words or []):
            tok = (w.word or "").strip()
            if tok:
                words.append({"w": tok, "start": float(w.start), "end": float(w.end)})

    out = {
        "language": info.language,
        "duration": float(info.duration),
        "words": words,
        "text": " ".join(full_text_parts),
        "segments": segments,
    }
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {len(words)} words, {info.duration:.1f}s, lang={info.language}")
    return out


def readable(transcript: dict) -> str:
    """Timestamped lines for a person or Claude to read when picking clips."""
    lines = []
    current = []
    start = None
    for w in transcript["words"]:
        if start is None:
            start = w["start"]
        current.append(w["w"])
        if w["w"].endswith((".", "?", "!")) or len(current) >= 18:
            lines.append(f"[{start:.2f} > {w['end']:.2f}]  {' '.join(current)}")
            current, start = [], None
    if current:
        lines.append(f"[{start:.2f} > {transcript['words'][-1]['end']:.2f}]  {' '.join(current)}")
    return "\n".join(lines)


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args or "--help" in sys.argv or "-h" in sys.argv:
        _usage("usage: python transcribe/whisper.py <video> [--text]\n"
                 "  --text  also print the timestamped transcript")
    video = Path(args[0])
    result = transcribe(video)
    print(f"[transcript] {cache_path(video)}")
    print(f"[summary] {len(result['words'])} words, {result['duration']:.1f}s")
    if "--text" in sys.argv:
        print(readable(result))
