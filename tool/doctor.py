"""Check that everything the clip tool needs is in place.

Usage:
  .venv/bin/python doctor.py      (or: python3 doctor.py before setup)

Prints one line per check. Exits 0 when every REQUIRED item passes.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config

results = []


def check(name: str, ok: bool, detail: str, required: bool = True, fix: str = ""):
    tag = "PASS" if ok else ("FAIL" if required else "INFO")
    results.append((tag, required))
    line = f"[{tag}] {name}: {detail}"
    if not ok and fix:
        line += f"\n       fix: {fix}"
    print(line)


def _version(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception:
        return ""


def _find(name):
    try:
        return config.tool(name)
    except SystemExit:
        return ""


def main():
    v = sys.version_info
    check("Python", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro} at {sys.executable}",
          fix="install Python 3.9 or newer (brew install python)")

    for name in ("ffmpeg", "ffprobe"):
        path = _find(name)
        check(name, bool(path), path or "not found", fix="brew install ffmpeg")

    node = shutil.which("node")
    node_v = _version([node, "--version"]) if node else ""
    try:
        node_major = int(node_v.lstrip("v").split(".")[0])
    except ValueError:
        node_major = 0
    check("Node.js", node_major >= 18, f"{node_v or 'not found'}",
          fix="install Node.js 18 or newer (brew install node)")

    in_venv = Path(sys.executable).resolve().parent.parent == (ROOT / ".venv").resolve() \
        or sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    fw = importlib.util.find_spec("faster_whisper") is not None
    check("faster-whisper (transcription)", fw,
          "installed" if fw else "not installed in this Python",
          fix=f"run {ROOT / 'setup.sh'}" + ("" if in_venv else
              f", then run this check with {ROOT / '.venv' / 'bin' / 'python'}"))

    cli = ROOT / "render" / "node_modules" / ".bin" / "remotion"
    check("Renderer (Remotion)", cli.exists(),
          "installed" if cli.exists() else "render/node_modules is missing",
          fix=f"run {ROOT / 'setup.sh'} (or npm install inside {ROOT / 'render'})")

    font = ROOT / "render" / "node_modules" / "@fontsource" / "inter" / "latin-700.css"
    check("Caption font (Inter)", font.exists(),
          "bundled with the renderer" if font.exists() else "not installed yet",
          fix=f"run {ROOT / 'setup.sh'}")

    for label, folder in (("Output folder", config.OUT_DIR), ("Cache folder", config.CACHE_DIR)):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            ok = os.access(str(folder), os.W_OK)
        except OSError:
            ok = False
        check(label, ok, str(folder), fix="choose a folder you can write to in config.env")

    free_gb = shutil.disk_usage(str(ROOT)).free / (1024 ** 3)
    check("Free disk space", free_gb >= 3, f"{free_gb:.1f} GB free",
          required=False, fix="renders need a few GB of scratch space; free some up")

    # Optional items
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    model_dir = hub / f"models--Systran--faster-whisper-{config.WHISPER_MODEL}"
    check("Speech model", model_dir.exists(),
          f"{config.WHISPER_MODEL} is downloaded" if model_dir.exists()
          else f"{config.WHISPER_MODEL} not downloaded yet (it downloads on the first transcription)",
          required=False)

    check("Settings file", config.CONFIG_FILE.exists(),
          str(config.CONFIG_FILE) if config.CONFIG_FILE.exists() else "config.env not created (defaults in use)",
          required=False, fix=f"cp {ROOT / 'config.example.env'} {config.CONFIG_FILE}")

    tracks = [p.name for p in config.MUSIC_DIR.glob("*")
              if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac")] if config.MUSIC_DIR.exists() else []
    check("Music", bool(tracks), f"{len(tracks)} track(s)" if tracks else "none added (clips render without music)",
          required=False)
    dm = config.default_music()
    if config.DEFAULT_MUSIC:
        check("Default music", bool(dm and dm.exists()), str(dm),
              fix="CLIP_TOOL_DEFAULT_MUSIC points at a file that does not exist")

    voice = config.BRAND_VOICE_FILE.exists()
    check("Brand voice notes", voice,
          str(config.BRAND_VOICE_FILE) if voice else "not written yet (the neutral example is used)",
          required=False)

    key = bool(config.get("ANTHROPIC_API_KEY") or config.get("ANTHROPIC_AUTH_TOKEN"))
    check("Anthropic API key", key,
          "set" if key else "not set (only needed for pick_clips.py; Claude Code picks clips without it)",
          required=False)

    gcred = (config.GOOGLE_DIR / "google_credentials.json").exists()
    check("Google Drive", gcred,
          "client file present" if gcred else "not set up (only needed for Drive mode)",
          required=False)

    failed = [1 for tag, required in results if tag == "FAIL" and required]
    print()
    if failed:
        print(f"{len(failed)} required item(s) need attention before the tool can run.")
        sys.exit(1)
    print("All required checks passed.")


if __name__ == "__main__":
    main()
