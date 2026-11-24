"""Cut and render clips from LOCAL video files, driven by a decisions JSON.

Usage:
  .venv/bin/python process_local.py <decisions.json> [--force]

  --force   re-render clips even if an identical one was already finished

Decision JSON format (see examples/decisions.example.json):
{
  "videos": [
    {
      "source_path": "/full/path/to/video.mp4",
      "clips": [
        {
          "headline": "lowercase three to seven words",
          "topic_slug": "kebab-case-slug",
          "keep_segments": [{"start": 0.5, "end": 12.3}, {"start": 20.0, "end": 31.4}],
          "music_path": "my-track.mp3",
          "music_volume": 0.07
        }
      ]
    }
  ]
}

Optional per video: source_name, crop_bottom_px, strip_music, word_fixes,
phrase_fixes, name_fixes. Optional per clip: clip_index, music_path (a file name
in the music folder, a full path, or null for none), no_music, music_volume,
music_start_from_s, strip_music, bg_blur_fill.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config
from transcribe.whisper import transcribe
from edit.cut_stitch import stitch, validate_segments
from edit.probe import get_dimensions, has_audio
from render.render_clip import render_clip

MUSIC_CONFIG_PATH = config.MUSIC_CONFIG
OUT = config.OUT_DIR
DEFAULT_MUSIC_VOL = config.DEFAULT_MUSIC_VOLUME
STATE_FILE = config.CACHE_DIR / config.get("CLIP_TOOL_STATE_FILE", "state.json")


def _ascii_sanitize(s: str) -> str:
    """Drop control characters only.

    This used to strip everything non-ASCII, because props were passed to the
    Remotion CLI as an inline --props= shell argument and a pound sign in a
    caption token would stall the headless render. render_clip.py now writes
    props to a UTF-8 JSON file instead, so currency symbols survive the
    round-trip and are worth keeping.
    """
    return "".join(c for c in s if ord(c) >= 32 or c in "\t")


def _sanitize_words(words: list) -> list:
    out = []
    for w in words:
        ww = dict(w)
        ww["w"] = _ascii_sanitize(ww.get("w", ""))
        out.append(ww)
    return out


def _apply_word_fixes(words: list, fixes: list) -> list:
    """Correct individual ASR mis-hears before they get burned into captions.

    Keyed on timestamp rather than token text so a fix can never spill onto a
    legitimate use of the same word elsewhere in the video. Each fix is
    {"at": <word start seconds>, "w": "<correct token>"}.
    """
    if not fixes:
        return words
    out = [dict(w) for w in words]
    for fix in fixes:
        at = float(fix["at"])
        target = min(out, key=lambda w: abs(w["start"] - at))
        if abs(target["start"] - at) <= 0.25:
            print(f"  [word-fix] {target['start']:.2f} {target['w']!r} -> {fix['w']!r}")
            target["w"] = fix["w"]
        else:
            print(f"  [word-fix] no word near {at:.2f}s, skipped")
    return out


def _norm(tok: str) -> str:
    return tok.lower().strip(".,!?;:'\"")


def _apply_phrase_fixes(words: list, fixes: list) -> list:
    """Correct multi-word ASR mishears without desynchronising the captions.

    Single-token replacement cannot fix what the model often gets wrong: it
    hears "the clothes" for "the close", or splits a name into three ordinary
    words. The error spans several tokens and the corrected text rarely has the
    same token count.

    The fix: locate the misheard span, then redistribute the span's OWN time
    range evenly across the replacement tokens. The span starts and ends at
    exactly the same moment it did before, so every caption after it stays in
    sync no matter how the token count changes.

    Each fix is {"at": <approx seconds>, "heard": "...", "correct": "..."}.
    Applied back-to-front so earlier edits cannot shift later match indices.
    """
    if not fixes:
        return words
    out = [dict(w) for w in words]

    for fix in sorted(fixes, key=lambda f: -float(f["at"])):
        heard = [_norm(t) for t in str(fix["heard"]).split() if _norm(t)]
        correct = str(fix["correct"]).split()
        at = float(fix["at"])
        if not heard or not correct:
            continue

        n = len(heard)
        cands = []
        for i in range(len(out) - n + 1):
            if abs(out[i]["start"] - at) > 3.0:
                continue
            if [_norm(out[j]["w"]) for j in range(i, i + n)] == heard:
                cands.append(i)
        if not cands:
            print(f"  [phrase-fix] NO MATCH {fix['heard']!r} near {at:.2f}s, skipped")
            continue

        i = min(cands, key=lambda i: abs(out[i]["start"] - at))
        span_start = out[i]["start"]
        span_end = out[i + n - 1]["end"]
        step = (span_end - span_start) / len(correct)
        new = [
            {"w": tok,
             "start": round(span_start + k * step, 3),
             "end": round(span_start + (k + 1) * step, 3)}
            for k, tok in enumerate(correct)
        ]
        print(f"  [phrase-fix] {fix['heard']!r} -> {fix['correct']!r} @ {span_start:.2f}s")
        out[i:i + n] = new

    return out


def _apply_name_fixes(words: list, fixes: list) -> list:
    """Correct a proper noun the ASR never gets right, everywhere it appears.

    Distinct from _apply_word_fixes: that one is timestamp-keyed because the same
    token can be right in one place and wrong in another. A brand or person's name
    the model simply cannot spell is wrong every single time, and there are too
    many occurrences to key each one by hand.

    Each fix is {"heard": "...", "correct": "..."}. Matched on the token stripped
    of surrounding punctuation, so "Acmee." and "Acmee," are both caught and keep
    their punctuation.
    """
    if not fixes:
        return words
    table = {f["heard"].lower(): f["correct"] for f in fixes}
    out = []
    hits = 0
    for w in words:
        ww = dict(w)
        tok = ww.get("w", "")
        core = tok.strip(".,!?;:'\"")
        repl = table.get(core.lower())
        if repl:
            ww["w"] = tok.replace(core, repl, 1)
            hits += 1
        out.append(ww)
    if hits:
        print(f"  [name-fix] {hits} token(s) corrected")
    return out


def _music_start_for(music_path: Path) -> float:
    try:
        cfg = json.loads(MUSIC_CONFIG_PATH.read_text())
        return float(cfg.get(music_path.name, 0))
    except Exception:
        return 0.0


def _load_state():
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except ValueError:
            state = {}
    else:
        state = {}
    state.setdefault("completed_clips", [])
    state.setdefault("signatures", {})
    return state


def _save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _clip_signature(vd: dict, clip: dict, source_path: Path) -> str:
    """Fingerprint of everything that decides what a finished clip looks like.

    A clip is skipped as already done only when this matches, so editing the
    headline, the segments or the music and running again re-renders it.
    """
    st = source_path.stat()
    video_keys = {k: v for k, v in vd.items() if k != "clips"}
    payload = json.dumps(
        {"video": video_keys, "clip": clip, "size": st.st_size, "mtime": int(st.st_mtime),
         "default_music": config.DEFAULT_MUSIC},
        sort_keys=True, default=str,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _load_batch(batch_path: Path) -> dict:
    if not batch_path.exists():
        sys.exit(f"Decisions file not found: {batch_path}")
    try:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{batch_path.name} is not valid JSON: {e}")
    if not isinstance(batch.get("videos"), list) or not batch["videos"]:
        sys.exit(f"{batch_path.name} needs a non-empty \"videos\" list. See examples/decisions.example.json.")
    for vi, vd in enumerate(batch["videos"], start=1):
        if not vd.get("source_path"):
            sys.exit(f"video {vi} has no \"source_path\"")
        if not isinstance(vd.get("clips"), list):
            sys.exit(f"video {vi} has no \"clips\" list")
        for ci, clip in enumerate(vd["clips"], start=1):
            for field in ("headline", "topic_slug", "keep_segments"):
                if field not in clip:
                    sys.exit(f"video {vi} clip {ci} is missing \"{field}\"")
            try:
                validate_segments(clip["keep_segments"])
            except ValueError as e:
                sys.exit(f"video {vi} clip {ci}: {e}")
    return batch


def process(batch_path: Path, force: bool = False):
    batch = _load_batch(Path(batch_path).expanduser())
    OUT.mkdir(parents=True, exist_ok=True)
    state = _load_state()
    summary = []
    failures = []
    skipped = 0
    n = len(batch["videos"])

    for vidx, vd in enumerate(batch["videos"], start=1):
        source_path = Path(vd["source_path"]).expanduser()
        source_name = vd.get("source_name", source_path.name)
        source_stem = Path(source_name).stem
        clips = vd["clips"]
        print(f"\n========== [{vidx}/{n}] {source_name} ({len(clips)} clip(s)) ==========")

        if not source_path.exists():
            print(f"  [FAIL] source not found: {source_path}")
            failures.append(f"{source_name} (source not found)")
            continue
        if not has_audio(source_path):
            print(f"  [FAIL] {source_name} has no audio track, so there is nothing to caption or cut on")
            failures.append(f"{source_name} (no audio track)")
            continue

        transcript = transcribe(source_path)
        source_words = _apply_word_fixes(transcript["words"], vd.get("word_fixes"))
        source_words = _apply_phrase_fixes(source_words, vd.get("phrase_fixes"))
        source_words = _apply_name_fixes(source_words, vd.get("name_fixes"))
        src_w, src_h = get_dimensions(source_path)
        is_portrait = src_h > src_w
        orientation = "portrait" if is_portrait else "landscape"
        target_dim = (1080, 1920) if is_portrait else None
        print(f"  source: {src_w}x{src_h} ({orientation})")

        for default_cidx, clip in enumerate(clips, start=1):
            cidx = clip.get("clip_index", default_cidx)
            slug = clip["topic_slug"]
            stem = f"{source_stem}_{cidx:02d}_{slug}"
            signature = _clip_signature(vd, clip, source_path)
            final_local = OUT / f"{stem}.mp4"

            if (not force and final_local.exists()
                    and state["signatures"].get(stem) == signature):
                print(f"  [skip-completed] {stem} (unchanged; use --force to render again)")
                skipped += 1
                continue

            print(f"\n  --- Clip {cidx}: {stem} ---")
            try:
                validate_segments(clip["keep_segments"], transcript.get("duration"))
                _render_one(vd, clip, source_path, source_words, stem,
                            target_dim, orientation, final_local)
            except Exception as e:
                # One bad clip must not cost the rest. State is only written on
                # success, so a failed clip is simply retried on the next run.
                failures.append(stem)
                print(f"  [FAIL] {stem}: {type(e).__name__}: {e}")
                continue

            if stem not in state["completed_clips"]:
                state["completed_clips"].append(stem)
            state["signatures"][stem] = signature
            _save_state(state)
            summary.append({"stem": stem, "path": str(final_local)})
            print(f"  [OK] {final_local}")

    if failures:
        print(f"\n[failed] {len(failures)}: " + ", ".join(failures))
    print(f"\n[done] {len(summary)} clip(s) rendered, {skipped} unchanged, "
          f"{len(failures)} failed. Folder: {OUT}")
    return summary, failures


def _render_one(vd, clip, source_path, source_words, stem,
                target_dim, orientation, final_local):
    stitched = stitch(
        source_video=source_path,
        keep_segments=clip["keep_segments"],
        source_words=source_words,
        out_stem=stem,
        target_dim=target_dim,
        crop_bottom_px=vd.get("crop_bottom_px", 0),
    )

    # Source footage already carries a music bed? Pull it out here, before the
    # render, so a new track can be laid under the cut. Needs the optional
    # demucs package.
    clip_video = stitched["video_path"]
    if clip.get("strip_music", vd.get("strip_music", False)):
        from edit.isolate_voice import strip_music
        clip_video = strip_music(
            clip_video, stem,
            device=config.get("DEMUCS_DEVICE", "cpu"),
        )

    # music_path: a file name in the music folder or a full path. null (JSON) or
    # no_music:true renders with NO music. Absent means the configured default,
    # which is no music until CLIP_TOOL_DEFAULT_MUSIC is set.
    if clip.get("no_music") or ("music_path" in clip and clip["music_path"] is None):
        music_path = None
    elif clip.get("music_path"):
        music_path = config.resolve_music(clip["music_path"])
    else:
        music_path = config.default_music()
    music_vol = clip.get("music_volume", DEFAULT_MUSIC_VOL)
    music_start = clip.get("music_start_from_s")
    if music_start is None:
        music_start = _music_start_for(music_path) if music_path else 0.0

    render_clip(
        stitched_video=clip_video,
        headline=_ascii_sanitize(clip["headline"]),
        words=_sanitize_words(stitched["words"]),
        duration_sec=stitched["duration"],
        output_path=final_local,
        music_path=music_path,
        music_volume=music_vol,
        music_start_from_s=music_start,
        source_orientation=orientation,
        bg_blur_fill=bool(clip.get("bg_blur_fill", vd.get("bg_blur_fill", False))),
    )


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args or "--help" in sys.argv or "-h" in sys.argv:
        _usage(__doc__.strip())
    _, failed = process(Path(args[0]), force="--force" in sys.argv)
    sys.exit(1 if failed else 0)
