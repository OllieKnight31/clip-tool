"""Central settings for the clip tool.

Every setting is an environment variable. On import this module also reads
`config.env` in the tool folder (KEY=VALUE lines) and fills in anything the
real environment has not already set, so a recipient edits one small file and
never touches the code.

Nothing here is personal: no paths, folder ids, brand names or keys are baked in.
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.env"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_env_file(CONFIG_FILE)


def get(name: str, default: str = "") -> str:
    value = os.environ.get(name, "")
    return value if value.strip() else default


def _path(name: str, default: Path) -> Path:
    value = get(name)
    return Path(value).expanduser() if value else default


# Folders
CACHE_DIR = _path("CLIP_TOOL_CACHE_DIR", ROOT / ".cache")
OUT_DIR = _path("CLIP_TOOL_OUT_DIR", ROOT / "output")
MUSIC_DIR = _path("CLIP_TOOL_MUSIC_DIR", ROOT / "music")
MUSIC_CONFIG = MUSIC_DIR / "music_config.json"

# Transcription
WHISPER_MODEL = get("CLIP_TOOL_WHISPER_MODEL", "small.en")

# Music: a file name inside MUSIC_DIR, or a full path. Empty means no music.
DEFAULT_MUSIC = get("CLIP_TOOL_DEFAULT_MUSIC")
DEFAULT_MUSIC_VOLUME = float(get("CLIP_TOOL_MUSIC_VOLUME", "0.07"))

# Optional automatic clip picking through the Anthropic API
ANTHROPIC_MODEL = get("CLIP_TOOL_ANTHROPIC_MODEL", "claude-opus-5-5")
CREATOR_NAME = get("CLIP_TOOL_CREATOR_NAME", "the creator")
BRAND_VOICE_FILE = _path("CLIP_TOOL_BRAND_VOICE", ROOT / "selector" / "brand_voice.md")

# Optional Google Drive
GOOGLE_DIR = _path("CLIP_TOOL_GOOGLE_DIR", Path.home() / ".config" / "clip-tool" / "google")
DRIVE_OUTPUT_FOLDER = get("CLIP_TOOL_OUTPUT_FOLDER")

# Rendering
REMOTION_CONCURRENCY = get("CLIP_TOOL_REMOTION_CONCURRENCY", "2")


def resolve_music(value) -> "Path | None":
    """Turn a music setting (file name or path) into a path, or None for no music."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    p = Path(value).expanduser()
    if not p.is_absolute() and not p.exists():
        p = MUSIC_DIR / value
    return p


def default_music() -> "Path | None":
    return resolve_music(DEFAULT_MUSIC)


def tool(name: str) -> str:
    """Full path to ffmpeg or ffprobe, with a clear message when it is missing."""
    found = shutil.which(name)
    if not found:
        for folder in ("/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local" / "bin")):
            candidate = Path(folder) / name
            if candidate.exists():
                return str(candidate)
        raise SystemExit(
            f"{name} was not found. Install it with `brew install ffmpeg` "
            f"(this provides both ffmpeg and ffprobe), then run again."
        )
    return found
