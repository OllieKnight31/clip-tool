"""FFmpeg cut + stitch with word-level remapping.

Takes a list of KEEP segments (start, end) from the source video and:
1. Cuts each segment with frame-accurate boundaries
2. Applies a 50ms audio fade in/out per segment (anti-click)
3. Concatenates into a single MP4 (re-encoded for clean splice points)
4. Returns the path to the stitched video + the remapped word timeline
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

CACHE_DIR = config.CACHE_DIR / "edits"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FADE_S = 0.05  # 50ms audio fade at each cut boundary


def validate_segments(keep_segments: List[Dict], source_duration: float = None) -> None:
    """Fail early, in plain words, on a decisions file ffmpeg would choke on."""
    if not keep_segments:
        raise ValueError("clip has no keep_segments")
    for i, seg in enumerate(keep_segments, start=1):
        try:
            s, e = float(seg["start"]), float(seg["end"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"segment {i} needs numeric 'start' and 'end' in seconds")
        if s < 0 or e <= s:
            raise ValueError(f"segment {i} is empty or backwards (start={s}, end={e})")
        if source_duration is not None and s >= source_duration:
            raise ValueError(
                f"segment {i} starts at {s:.2f}s but the video is only {source_duration:.2f}s long"
            )


def _signature(source_video: Path, keep_segments, target_width, target_dim, crop_bottom_px) -> str:
    st = Path(source_video).stat()
    payload = json.dumps({
        "src": str(Path(source_video).resolve()), "size": st.st_size, "mtime": int(st.st_mtime),
        "segs": [[round(float(s["start"]), 3), round(float(s["end"]), 3)] for s in keep_segments],
        "w": target_width, "dim": list(target_dim) if target_dim else None,
        "crop": int(crop_bottom_px),
    }, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def stitch(
    source_video: Path,
    keep_segments: List[Dict],   # [{"start": float, "end": float}, ...]
    source_words: List[Dict],    # [{"w": str, "start": float, "end": float}, ...]
    out_stem: str,
    target_width: int = 1080,
    target_dim: tuple = None,    # explicit (w, h), overrides target_width
    crop_bottom_px: int = 0,     # trim N px off the bottom BEFORE scaling
) -> Dict:
    """Returns: {'video_path': Path, 'words': [...remapped...], 'duration': float}

    Stitch is an INTERMEDIATE step. The source is often 4K: scaling to target_width
    here (default 1080) before encoding cuts ffmpeg work about tenfold. The renderer
    resizes to 1080x1920 anyway so nothing is lost.

    crop_bottom_px trims a band off the bottom of the frame before scaling. Use it
    when the source has burned-in subtitles from the creator's own edit, otherwise
    they collide with the phrase captions rendered on top. The crop changes the
    aspect ratio, which the renderer reads back off the stitched file rather than
    assuming 16:9.
    """
    source_video = Path(source_video)
    validate_segments(keep_segments)
    out_video = CACHE_DIR / f"{out_stem}.mp4"
    out_words_path = CACHE_DIR / f"{out_stem}.words.json"
    key_path = CACHE_DIR / f"{out_stem}.key"

    # The cached cut is reused only when it was made from the same source with the
    # same segments. Keying on the name alone would hand back the OLD cut after an
    # edit to the decisions file, with captions timed for the new one.
    signature = _signature(source_video, keep_segments, target_width, target_dim, crop_bottom_px)
    cached = out_video.exists() and key_path.exists() and key_path.read_text().strip() == signature

    if cached:
        print(f"[stitch-cache] {out_video.name}")
    else:
        # Portrait: fill the 1080x1920 frame, cropping the overflow, so a 4:5 or
        # 3:4 phone video is never stretched. A true 9:16 source is unchanged.
        if target_dim is not None:
            w, h = target_dim
            scale_str = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},setsar=1"
            )
        else:
            scale_str = f"scale={target_width}:-2,setsar=1"

        crop_str = f"crop=iw:ih-{int(crop_bottom_px)}:0:0," if crop_bottom_px else ""

        # One INPUT per segment, each with its own -ss/-t seek.
        #
        # The obvious implementation is a single input plus trim= filters, but
        # trim decodes the source from t=0 to reach each segment: on a 36-minute
        # source a clip at 2000s costs minutes of pure seeking, per clip. Input
        # seeking (-ss before -i) jumps to the preceding keyframe instead, which
        # is frame-accurate here because we re-encode.
        inputs = []
        filter_parts = []
        for i, seg in enumerate(keep_segments):
            s, e = float(seg["start"]), float(seg["end"])
            seg_dur = e - s
            inputs += ["-ss", f"{s:.3f}", "-t", f"{seg_dur:.3f}", "-i", str(source_video)]
            filter_parts.append(
                f"[{i}:v:0]setpts=PTS-STARTPTS,fps=30,{crop_str}{scale_str}[v{i}]"
            )
            fade_out_start = max(0, seg_dur - FADE_S)
            filter_parts.append(
                f"[{i}:a:0]asetpts=PTS-STARTPTS,aresample=48000,"
                f"aformat=channel_layouts=stereo,"
                f"afade=t=in:d={FADE_S},afade=t=out:st={fade_out_start:.3f}:d={FADE_S}[a{i}]"
            )

        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(len(keep_segments)))
        filter_parts.append(
            f"{concat_inputs}concat=n={len(keep_segments)}:v=1:a=1[outv][outa]"
        )
        filter_complex = ";".join(filter_parts)

        cmd = [
            config.tool("ffmpeg"), "-y", "-loglevel", "error",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-crf", "20", "-preset", "superfast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_video),
        ]
        print(f"[stitch] {len(keep_segments)} segments -> {out_video.name}", flush=True)
        key_path.unlink(missing_ok=True)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            out_video.unlink(missing_ok=True)
            tail = "\n".join(result.stderr.strip().splitlines()[-6:])
            raise RuntimeError(f"ffmpeg could not cut {source_video.name}:\n{tail}")
        key_path.write_text(signature)

    # Remap words: for each KEEP segment with offset O = sum of prior durations,
    # any word with w.start in [s, e] becomes {start: w.start - s + O, end: w.end - s + O}
    new_words = []
    offset = 0.0
    for seg in keep_segments:
        s, e = float(seg["start"]), float(seg["end"])
        for w in source_words:
            # Include word if it starts within the segment (be lenient on end overlap)
            if w["start"] >= s - 0.01 and w["start"] < e:
                new_w = {
                    "w": w["w"],
                    "start": max(0.0, w["start"] - s + offset),
                    "end": min(offset + (e - s), w["end"] - s + offset),
                }
                new_words.append(new_w)
        offset += (e - s)

    final_duration = offset

    out_words_path.write_text(json.dumps({
        "duration": final_duration,
        "words": new_words,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "video_path": out_video,
        "words": new_words,
        "duration": final_duration,
    }


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    if len(sys.argv) < 5 or sys.argv[1] in ("-h", "--help"):
        _usage("usage: python edit/cut_stitch.py <source.mp4> <transcript.json> <decision.json> <out_stem>")
    source = Path(sys.argv[1])
    transcript = json.loads(Path(sys.argv[2]).read_text())
    decision = json.loads(Path(sys.argv[3]).read_text())
    stem = sys.argv[4]
    clip = decision["clips"][0]
    result = stitch(source, clip["keep_segments"], transcript["words"], stem)
    print(json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in result.items()}, indent=2)[:500])
