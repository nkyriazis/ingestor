from __future__ import annotations

from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# The one set of scopes every official-API Importer needs, so the user
# consents once for a single shared token file rather than once per source.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def load_credentials(token_path: Path) -> Credentials:
    """Loads the shared OAuth token every official-API Importer (Gmail,
    Drive) authenticates with. Obtained once via `run_consent_flow` /
    `python -m ingestor.setup_google_auth` — see README.
    """
    return Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call, no-any-return]
        str(token_path), SCOPES
    )


def run_consent_flow(client_secrets_path: Path, token_path: Path) -> None:
    """One-time interactive setup: runs the OAuth consent flow covering
    every scope our Importers need, and writes the resulting token to
    token_path. Meant to be run by hand (see README), not by the ingestor
    service itself.
    """
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
    credentials = flow.run_local_server(port=0)
    token_path.write_text(credentials.to_json())
