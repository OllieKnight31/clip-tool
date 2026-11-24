"""Google Drive sign-in (optional feature).

Uses YOUR OWN Google OAuth client. Put the client file you download from
Google Cloud at <google dir>/google_credentials.json; the first Drive command
opens a browser to sign in and saves a token next to it. The folder defaults to
~/.config/clip-tool/google and can be changed with CLIP_TOOL_GOOGLE_DIR.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

GOOGLE_DIR = config.GOOGLE_DIR
CREDENTIALS_FILE = GOOGLE_DIR / "google_credentials.json"
TOKEN_FILE = GOOGLE_DIR / "google_token.json"
# drive: download sources and upload clips.
SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_credentials():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        sys.exit(
            "Google Drive support is not installed. Run:\n"
            f"  {sys.executable} -m pip install -r {config.ROOT / 'requirements-drive.txt'}"
        )

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                sys.exit(
                    f"No Google client file at {CREDENTIALS_FILE}.\n"
                    "See the Google Drive section of the README for the one-off setup, "
                    "or work from local video files instead (no Google setup needed)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        GOOGLE_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        try:
            TOKEN_FILE.chmod(0o600)
        except OSError:
            pass

    return creds


def drive_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)
