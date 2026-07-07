from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from ingestor.google_auth import load_credentials
from ingestor.importers.drive import DriveFile

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

# Native Google Docs/Sheets/Slides have no bytes of their own — get_media()
# 403s on them — so they must be exported to a concrete format instead.
# Slides export to pptx so ConvertStep's existing slide-deck handling picks
# them up unchanged; Docs/Sheets export to plain text formats good enough
# for markitdown/extraction.
_GOOGLE_NATIVE_EXPORT_FORMATS = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}


class RealDriveClient:
    """Talks to the real Drive API. Requires the shared Google OAuth token
    (see ingestor.google_auth, README) — not exercised by the automated
    test suite, which uses a fake DriveClient against the same Protocol
    instead.

    Uses Drive's Changes API for incremental sync: the checkpoint is a
    `pageToken`, mirroring RealGmailClient's historyId-as-opaque-checkpoint
    shape. On first run — no checkpoint yet — this bootstraps to the
    account's current start page token without backfilling existing files,
    same "start from now" reasoning as Gmail. The Changes API reports
    changes account-wide, with no server-side "only within this folder"
    filter, so each change is checked against the configured folder ids
    locally instead.

    `folders` is a list of folder names or slash-separated paths (e.g.
    "Work/Notes") — see `resolve_folder_id` for how ambiguity between
    same-named folders is handled.
    """

    def __init__(self, token_path: Path, folders: Sequence[str]) -> None:
        self._service = build("drive", "v3", credentials=load_credentials(token_path))
        all_folders = self._list_all_folders()
        self._folder_ids = {resolve_folder_id(all_folders, folder) for folder in folders}

    def _list_all_folders(self) -> list[Mapping[str, Any]]:
        folders: list[Mapping[str, Any]] = []
        page_token = ""
        while True:
            list_response = (
                self._service.files()
                .list(
                    q=f"mimeType='{FOLDER_MIME_TYPE}' and trashed=false",
                    fields="nextPageToken, files(id, name, parents)",
                    pageToken=page_token,
                )
                .execute()
            )
            folders.extend(list_response.get("files", []))
            page_token = list_response.get("nextPageToken", "")
            if not page_token:
                return folders

    def list_new_files(self, checkpoint: str | None) -> tuple[list[DriveFile], str | None]:
        if checkpoint is None:
            start_response = self._service.changes().getStartPageToken().execute()
            return [], str(start_response["startPageToken"])

        files: list[DriveFile] = []
        page_token = checkpoint
        latest_token = checkpoint
        while True:
            changes_response = (
                self._service.changes()
                .list(
                    pageToken=page_token,
                    fields=(
                        "nextPageToken, newStartPageToken, "
                        "changes(fileId, file(id, name, parents, trashed, mimeType))"
                    ),
                )
                .execute()
            )
            for change in changes_response.get("changes", []):
                file = change.get("file")
                if file and not file.get("trashed") and self._in_watched_folder(file):
                    files.append(
                        self._fetch(str(file["id"]), str(file["name"]), str(file.get("mimeType", "")))
                    )
            page_token = changes_response.get("nextPageToken", "")
            if not page_token:
                latest_token = str(changes_response.get("newStartPageToken", latest_token))
                break
        return files, latest_token

    def _in_watched_folder(self, file: Mapping[str, Any]) -> bool:
        return any(parent in self._folder_ids for parent in file.get("parents") or [])

    def _fetch(self, file_id: str, name: str, mime_type: str) -> DriveFile:
        export_format = _GOOGLE_NATIVE_EXPORT_FORMATS.get(mime_type)
        if export_format is None:
            request = self._service.files().get_media(fileId=file_id)
        else:
            export_mime_type, extension = export_format
            request = self._service.files().export_media(fileId=file_id, mimeType=export_mime_type)
            name = f"{name}{extension}"
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return DriveFile(id=file_id, name=name, data=buffer.getvalue())


def resolve_folder_id(folders: Sequence[Mapping[str, Any]], path: str) -> str:
    """Resolves a Drive folder by name or slash-separated path (e.g.
    "Work/Notes") to its folder id. `folders` is the flat list of
    {id, name, parents} entries the caller already fetched from Drive —
    Drive allows multiple folders with the same name, so a bare name only
    resolves when it's unambiguous; a fuller path disambiguates by walking
    each candidate's parent chain.
    """
    by_id = {str(folder["id"]): folder for folder in folders}
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        raise ValueError(f"Empty Drive folder path: {path!r}")

    def matches(folder_id: str, remaining: list[str]) -> bool:
        folder = by_id.get(folder_id)
        if folder is None or folder["name"] != remaining[-1]:
            return False
        if len(remaining) == 1:
            return True
        parents = folder.get("parents") or []
        return any(matches(parent_id, remaining[:-1]) for parent_id in parents)

    matching_ids = [folder_id for folder_id in by_id if matches(folder_id, segments)]
    if not matching_ids:
        raise ValueError(f"No Drive folder matches path {path!r}")
    if len(matching_ids) > 1:
        candidate_paths = sorted(_full_path(by_id, folder_id) for folder_id in matching_ids)
        raise ValueError(
            f"Ambiguous Drive folder path {path!r}: matches {candidate_paths} "
            "— use a longer path (e.g. 'Parent/Name') to disambiguate"
        )
    return matching_ids[0]


def _full_path(by_id: Mapping[str, Mapping[str, Any]], folder_id: str) -> str:
    folder = by_id.get(folder_id)
    if folder is None:
        return "?"
    parents = folder.get("parents") or []
    if not parents:
        return str(folder["name"])
    return f"{_full_path(by_id, parents[0])}/{folder['name']}"
