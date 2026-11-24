"""Headless Remotion render driver.

Called by process_local.py, overlay_only.py and batch_orchestrate.py once a clip
has been cut and stitched. Stages the stitched video (and a pre-trimmed slice of
the music bed) into render/public/, writes the props to a JSON file, then shells
out to the Remotion CLI.

Props go via a FILE, never an inline --props= string. Inline props break on
non-ASCII characters (for example a pound sign in a caption word) because the
JSON has to survive a shell round-trip. A file sidesteps that entirely.

Staged media is removed from public/ after each render. render/public/ is copied
verbatim into the Remotion bundle on every run, so letting old intermediates pile
up there slows every later render until the headless browser times out.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

RENDER_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = RENDER_DIR / "public"
PROPS_DIR = RENDER_DIR / ".props"
ENTRY = "src/index.ts"
COMPOSITION_ID = "Clip"

FPS = 30
CRF = "18"
AUDIO_BITRATE = "192k"


def _video_aspect(video: Path) -> float:
    """Width/height of the stitched file.

    Read rather than assumed: a clip whose burned-in subtitles were cropped out
    at stitch time is no longer 16:9, and hardcoding the aspect would letterbox
    it wrong. Rotation metadata is respected so an unrotated phone file used in
    overlay mode is measured the way it is displayed.
    """
    from edit.probe import get_dimensions
    w, h = get_dimensions(video)
    return w / h


def _remotion_cli() -> Path:
    cli = RENDER_DIR / "node_modules" / ".bin" / "remotion"
    if not cli.exists():
        raise RuntimeError(
            f"The renderer is not installed (nothing at {cli}). "
            f"Run setup.sh in the tool folder, or `npm install` inside {RENDER_DIR}."
        )
    return cli


def _stage_music(music_path: Path, start_from_s: float, duration_sec: float, stem: str) -> str:
    """Trim the underbed to exactly the slice this clip needs.

    Trimming here rather than in the composition keeps us off Remotion's
    startFrom/trimBefore prop, which has changed across 4.x releases.
    """
    out_name = f"{stem}__music.m4a"
    out_path = PUBLIC_DIR / out_name
    cmd = [
        config.tool("ffmpeg"), "-y", "-loglevel", "error",
        "-ss", f"{max(0.0, float(start_from_s)):.3f}",
        "-i", str(music_path),
        "-t", f"{duration_sec + 0.5:.3f}",
        "-vn", "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_name


def render_clip(
    stitched_video: Path,
    headline: str,
    words: list,
    duration_sec: float,
    output_path: Path,
    music_path: Path = None,
    music_volume: float = 0.07,
    music_start_from_s: float = 0.0,
    source_orientation: str = "landscape",
    bg_blur_fill: bool = False,
    headline_duration_s: float = 0.0,
    hide_captions: bool = False,
    headline_style: str = "default",
    mask_top_for_headline: bool = False,
):
    stitched_video = Path(stitched_video).expanduser().resolve()
    # Resolved before the render: the Remotion CLI runs with render/ as its
    # working folder, so a relative output path would otherwise land in there.
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    PROPS_DIR.mkdir(parents=True, exist_ok=True)

    stem = output_path.stem
    staged = []

    video_name = f"{stem}__src{stitched_video.suffix}"
    import shutil
    shutil.copy2(stitched_video, PUBLIC_DIR / video_name)
    staged.append(PUBLIC_DIR / video_name)

    props_file = PROPS_DIR / f"{stem}.json"
    try:
        music_name = None
        if music_path:
            music_path = Path(music_path).expanduser()
            if music_path.exists():
                music_name = _stage_music(music_path, music_start_from_s, duration_sec, stem)
                staged.append(PUBLIC_DIR / music_name)
            else:
                print(f"  [warn] music not found, rendering without music: {music_path}")

        props = {
            "videoSrc": video_name,
            "headline": headline or "",
            "words": [] if hide_captions else words,
            "musicSrc": music_name,
            "musicVolume": float(music_volume),
            "orientation": "portrait" if source_orientation == "portrait" else "landscape",
            "durationSec": float(duration_sec),
            "videoAspect": _video_aspect(stitched_video),
            "bgBlurFill": bool(bg_blur_fill),
            "headlineDurationSec": float(headline_duration_s or 0.0),
            "hideCaptions": bool(hide_captions),
            "headlineStyle": "pill" if headline_style == "pill" else "default",
            "maskTop": bool(mask_top_for_headline),
        }
        props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

        cmd = [
            str(_remotion_cli()), "render", ENTRY, COMPOSITION_ID, str(output_path),
            f"--props={props_file}",
            "--codec=h264",
            f"--crf={CRF}",
            f"--audio-bitrate={AUDIO_BITRATE}",
            "--pixel-format=yuv420p",
            "--log=info",
            f"--concurrency={config.REMOTION_CONCURRENCY}",
        ]
        print(f"  [render] {stem} ({duration_sec:.1f}s, {props['orientation']})", flush=True)
        output_path.unlink(missing_ok=True)
        subprocess.run(cmd, cwd=str(RENDER_DIR), check=True)
    finally:
        for f in staged:
            f.unlink(missing_ok=True)
        # Props hold the clip's words; nothing needs them once the render ends.
        props_file.unlink(missing_ok=True)

    if not output_path.exists():
        raise RuntimeError(f"Remotion reported success but no output at {output_path}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [render] wrote {output_path.name} ({size_mb:.1f} MB)")
    return output_path
