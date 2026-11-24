"""List videos in the source Drive folder."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from drive.auth import drive_service

VIDEO_MIMES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/mpeg",
}


def list_videos(folder_id: str):
    svc = drive_service()
    query = f"'{folder_id}' in parents and trashed = false"
    fields = "files(id, name, mimeType, size, modifiedTime, videoMediaMetadata)"
    page_token = None
    files = []
    while True:
        resp = svc.files().list(
            q=query,
            fields=f"nextPageToken, {fields}",
            pageSize=100,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def _usage(text: str) -> None:
    """Print usage. Asking for help is a success; missing arguments is an error."""
    asked = "--help" in sys.argv or "-h" in sys.argv
    print(text, file=sys.stdout if asked else sys.stderr)
    sys.exit(0 if asked else 2)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _usage("usage: python drive/list_folder.py <drive_folder_id>")
    folder_id = sys.argv[1]
    files = list_videos(folder_id)
    print(f"Total items: {len(files)}\n")
    for f in files:
        size_mb = int(f.get("size", 0)) / (1024 * 1024) if f.get("size") else 0
        meta = f.get("videoMediaMetadata") or {}
        dur = meta.get("durationMillis")
        dur_str = f"{int(dur)/1000:.0f}s" if dur else "?"
        print(f"  [{f['id']}] {f['name']:60s} {f['mimeType']:25s} {size_mb:8.1f} MB  {dur_str}")
