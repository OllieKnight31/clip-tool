"""Strip the background music bed out of a clip, leaving dialogue only.

Source footage that was already edited for YouTube usually has a music underbed
baked into the mix. When the client wants to lay their own track under the short
form cut, that bed has to come out first: you cannot subtract it downstream.

Demucs separates the mix into vocals / no-vocals stems; we keep the vocals stem
and remux it over the original video track.

Applied AFTER stitching rather than to the whole source: a 45s clip is ~40x less
audio to separate than a 22-minute source, and the splice points are already
made, so there is nothing for the separation to smear across.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

CACHE_DIR = config.CACHE_DIR / "voiceonly"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
# The interpreter running the tool, so demucs comes from the same environment.
VENV_PY = Path(sys.executable)

MODEL = "htdemucs"


def _ffmpeg() -> str:
    return config.tool("ffmpeg")


def strip_music(video_path: Path, out_stem: str, device: str = "cpu",
                voice_gain_db: float = 2.0) -> Path:
    """Return a copy of `video_path` whose audio is the isolated vocal stem.

    voice_gain_db compensates for the level drop from removing the bed: the
    separated voice sits noticeably quieter than the original mix.

    Video is stream-copied, so this costs one audio pass, not a re-encode.
    """
    video_path = Path(video_path)
    out_video = CACHE_DIR / f"{out_stem}.mp4"
    try:
        import demucs  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "strip_music needs the optional demucs package (a large download). Install it with: "
            f"{sys.executable} -m pip install -r {config.ROOT / 'requirements-optional.txt'}"
        )
    if out_video.exists():
        print(f"  [voice-cache] {out_video.name}")
        return out_video

    work = CACHE_DIR / f"_work_{out_stem}"
    work.mkdir(parents=True, exist_ok=True)
    wav = work / "mix.wav"

    # Demucs wants a plain PCM wav; 44.1k stereo is the model's native rate.
    subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(video_path),
         "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )

    print(f"  [demucs] separating {out_stem} ...", flush=True)
    # On a Mac with little memory the GPU (mps) run can be killed outright rather
    # than failing cleanly. CPU uses less memory, so it is the retry.
    devices = [device] + (["cpu"] if device != "cpu" else [])
    last = None
    for dev in devices:
        try:
            subprocess.run(
                [str(VENV_PY), "-m", "demucs",
                 "--two-stems=vocals", "-n", MODEL, "-d", dev,
                 "-o", str(work), str(wav)],
                check=True, capture_output=True,
            )
            last = None
            break
        except subprocess.CalledProcessError as e:
            last = e
            print(f"  [demucs] {dev} failed ({e.returncode}), retrying" if dev != devices[-1]
                  else f"  [demucs] {dev} failed ({e.returncode})")
    if last is not None:
        raise last

    vocals = work / MODEL / wav.stem / "vocals.wav"
    if not vocals.exists():
        raise RuntimeError(f"demucs produced no vocals stem at {vocals}")

    subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error",
         "-i", str(video_path), "-i", str(vocals),
         "-filter_complex", f"[1:a]volume={voice_gain_db}dB[a]",
         "-map", "0:v:0", "-map", "[a]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(out_video)],
        check=True,
    )

    shutil.rmtree(work, ignore_errors=True)
    print(f"  [demucs] voice-only -> {out_video.name}")
    return out_video


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _usage("usage: python edit/isolate_voice.py <video> [out_stem]")
    print(strip_music(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "test"))
