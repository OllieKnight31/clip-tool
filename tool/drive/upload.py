"""Upload finished clips to the output Drive folder, in per-source-video subfolders."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from drive.auth import drive_service

OUTPUT_FOLDER_ID = config.DRIVE_OUTPUT_FOLDER


def require_output_folder() -> str:
    if not OUTPUT_FOLDER_ID:
        sys.exit(
            "No Drive output folder is set. Put the folder id in config.env as "
            "CLIP_TOOL_OUTPUT_FOLDER (the id is the last part of the folder's web address)."
        )
    return OUTPUT_FOLDER_ID


def _q(value: str) -> str:
    """Escape a value for a Drive search query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_or_create_folder(name: str, parent_id: str) -> str:
    """Find a folder by name within parent. Create if missing. Returns folder id."""
    svc = drive_service()
    q = (
        f"name = '{_q(name)}' and '{parent_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    resp = svc.files().list(
        q=q, fields="files(id, name)",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]

    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return folder["id"]


def upload_file(local_path: Path, parent_folder_id: str, mime: str = None) -> dict:
    """Upload a local file to the given parent folder. Returns {id, name, webViewLink}."""
    from googleapiclient.http import MediaFileUpload
    import mimetypes

    svc = drive_service()
    if mime is None:
        mime = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"

    meta = {"name": local_path.name, "parents": [parent_folder_id]}
    media = MediaFileUpload(str(local_path), mimetype=mime, resumable=True)
    result = svc.files().create(
        body=meta, media_body=media,
        fields="id, name, webViewLink",
        supportsAllDrives=True,
    ).execute()
    return result


def upload_clip_bundle(
    source_video_name: str,
    clip_video: Path,
    transcript_text: str,
    edit_decision_json: str,
) -> dict:
    """Upload a finished clip + its transcript + the edit decision into the per-video folder."""
    # source_video_name = "C0043.MP4" -> folder "C0043"
    subfolder_name = Path(source_video_name).stem
    subfolder_id = find_or_create_folder(subfolder_name, require_output_folder())

    print(f"[upload] {clip_video.name} -> Clips/{subfolder_name}/")
    video_result = upload_file(clip_video, subfolder_id, mime="video/mp4")

    # Write transcript + decision to local temp then upload
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        transcript_path = td / f"{clip_video.stem}.transcript.txt"
        transcript_path.write_text(transcript_text)
        decision_path = td / f"{clip_video.stem}.edit-decision.json"
        decision_path.write_text(edit_decision_json)

        upload_file(transcript_path, subfolder_id, mime="text/plain")
        upload_file(decision_path, subfolder_id, mime="application/json")

    return {
        "video": video_result,
        "subfolder_id": subfolder_id,
        "subfolder_name": subfolder_name,
    }


if __name__ == "__main__":
    # Smoke test: list output folder
    svc = drive_service()
    resp = svc.files().list(
        q=f"'{require_output_folder()}' in parents and trashed = false",
        fields="files(id, name, mimeType)",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    for f in resp.get("files", []):
        print(f"  {f['name']:40s} {f['id']}  {f['mimeType']}")
