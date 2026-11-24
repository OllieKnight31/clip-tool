"""Download a file from Drive to local cache, resumable, with progress."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from drive.auth import drive_service

CACHE_DIR = config.CACHE_DIR / "videos"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def download_file(file_id: str, dest_dir: Path = CACHE_DIR) -> Path:
    from googleapiclient.http import MediaIoBaseDownload

    svc = drive_service()
    meta = svc.files().get(
        fileId=file_id,
        fields="id,name,size,mimeType",
        supportsAllDrives=True,
    ).execute()

    name = meta["name"]
    total_bytes = int(meta.get("size", 0))
    out = dest_dir / name

    if out.exists() and out.stat().st_size == total_bytes:
        print(f"[cache] {name} ({total_bytes/1024/1024:.1f} MB)")
        return out

    print(f"[downloading] {name} ({total_bytes/1024/1024:.1f} MB)")
    request = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(out, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=16 * 1024 * 1024)
        done = False
        last_pct = -1
        while not done:
            status, done = downloader.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if pct >= last_pct + 5:
                    print(f"  {pct}%", flush=True)
                    last_pct = pct
    print(f"[done] {out}")
    return out


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _usage("usage: python drive/download.py <drive_file_id>")
    download_file(sys.argv[1])
