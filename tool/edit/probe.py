"""Probe a video for aspect ratio."""
import subprocess
import sys
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def get_dimensions(video_path: Path) -> Tuple[int, int]:
    """Returns (display_width, display_height) of the first video stream.

    Respects rotation metadata: phones often store frames as 1920x1080 with a
    rotation=90 tag, so the displayed video is portrait 1080x1920.
    """
    result = subprocess.run(
        [
            config.tool("ffprobe"), "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
            "-of", "default=noprint_wrappers=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    width = height = None
    rotation = 0
    for line in result.stdout.strip().splitlines():
        if line.startswith("width="):
            width = int(line.split("=", 1)[1])
        elif line.startswith("height="):
            height = int(line.split("=", 1)[1])
        elif line.startswith("TAG:rotate=") or line.startswith("rotate=") or line.startswith("rotation="):
            try:
                rotation = int(float(line.split("=", 1)[1]))
            except ValueError:
                pass
    if width is None or height is None:
        raise RuntimeError(f"Could not parse dimensions: {result.stdout!r}")
    if abs(rotation) in (90, 270):
        width, height = height, width
    return width, height


def has_audio(video_path: Path) -> bool:
    """True when the file has at least one audio stream."""
    result = subprocess.run(
        [config.tool("ffprobe"), "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def get_duration(video_path: Path) -> float:
    result = subprocess.run(
        [config.tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def is_portrait(video_path: Path) -> bool:
    """Returns True if source is taller than wide (9:16-ish)."""
    w, h = get_dimensions(video_path)
    return h > w


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _usage("usage: python edit/probe.py <video>")
    p = Path(sys.argv[1])
    w, h = get_dimensions(p)
    orient = "PORTRAIT" if h > w else "LANDSCAPE"
    print(f"{p.name}: {w}x{h} ({orient}, ratio {w/h:.3f})")
