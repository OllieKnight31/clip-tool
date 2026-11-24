"""Optional Google Drive mode: download sources from Drive, then cut, render and upload.

Needs the one-off Google setup described in the README. Without it, use
process_local.py on files that are already on this Mac.

Usage:
  .venv/bin/python batch_orchestrate.py <decisions.json> [--force]

The decisions file is the same as for process_local.py, except each video has
"drive_id" (and "source_name") instead of "source_path". Finished clips are saved
locally and uploaded to a `Done` folder inside CLIP_TOOL_OUTPUT_FOLDER, named
<source-name>_<NN>_<topic-slug>.mp4.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config


def process_batch(batch_path: Path, force: bool = False):
    from drive.download import download_file
    from drive.upload import find_or_create_folder, upload_file, require_output_folder, _q
    from drive.auth import drive_service
    import process_local

    batch = json.loads(Path(batch_path).expanduser().read_text(encoding="utf-8"))
    videos = batch.get("videos") or []
    if not videos:
        sys.exit("The decisions file needs a non-empty \"videos\" list.")
    for vi, vd in enumerate(videos, start=1):
        if not vd.get("drive_id"):
            sys.exit(f"video {vi} has no \"drive_id\"")

    done_id = find_or_create_folder("Done", require_output_folder())
    print(f"[batch] {len(videos)} video(s), Done folder = {done_id}")

    # 1. Download every source, then hand over to the local pipeline.
    local_videos = []
    for vd in videos:
        video = download_file(vd["drive_id"])
        local = {k: v for k, v in vd.items() if k != "drive_id"}
        local["source_path"] = str(video)
        local.setdefault("source_name", video.name)
        local_videos.append(local)

    local_batch = config.CACHE_DIR / f"_drive_{Path(batch_path).stem}.json"
    local_batch.parent.mkdir(parents=True, exist_ok=True)
    local_batch.write_text(json.dumps({"videos": local_videos}, indent=2), encoding="utf-8")
    summary, failures = process_local.process(local_batch, force=force)

    # 2. Upload what was rendered in this run, replacing same-named files.
    svc = drive_service()
    links = []
    for item in summary:
        final_local = Path(item["path"])
        existing = svc.files().list(
            q=f"'{done_id}' in parents and trashed = false and name = '{_q(final_local.name)}'",
            fields="files(id)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute().get("files", [])
        for e in existing:
            svc.files().delete(fileId=e["id"], supportsAllDrives=True).execute()
        print(f"  [upload] {final_local.name} -> Done/")
        uploaded = upload_file(final_local, done_id, mime="video/mp4")
        links.append({"clip": final_local.name, "drive_link": uploaded.get("webViewLink")})

    print("\n========== ALL DONE ==========")
    print(json.dumps(links, indent=2))
    return links, failures


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args or "--help" in sys.argv or "-h" in sys.argv:
        _usage(__doc__.strip())
    _, failed = process_batch(Path(args[0]), force="--force" in sys.argv)
    sys.exit(1 if failed else 0)
