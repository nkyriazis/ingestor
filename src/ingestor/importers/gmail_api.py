from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ingestor.importers.gmail import GmailAttachment, GmailMessage

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class RealGmailClient:
    """Talks to the real Gmail API. Requires an OAuth token obtained out of
    band (see README) — not exercised by the automated test suite, which
    uses a fake GmailClient against the same Protocol instead.

    Uses Gmail's History API for incremental sync: the checkpoint is a
    `historyId`, not a message ID (message IDs aren't chronologically
    orderable, so "give me messages after this one" isn't a query Gmail
    supports). On first run — no checkpoint yet — this bootstraps the
    checkpoint to the mailbox's current historyId without backfilling any
    existing mail, since a personal ingestion pipeline should start from
    "now", not replay the whole inbox.
    """

    def __init__(self, token_path: Path) -> None:
        credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
            str(token_path), SCOPES
        )
        self._service = build("gmail", "v1", credentials=credentials)

    def list_new_messages(
        self, checkpoint: str | None
    ) -> tuple[list[GmailMessage], str | None]:
        if checkpoint is None:
            profile = self._service.users().getProfile(userId="me").execute()
            return [], str(profile["historyId"])

        message_ids: list[str] = []
        latest_history_id = checkpoint
        page_token = ""
        while True:
            response = (
                self._service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=checkpoint,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                    pageToken=page_token,
                )
                .execute()
            )
            for record in response.get("history", []):
                latest_history_id = str(record.get("id", latest_history_id))
                for added in record.get("messagesAdded", []):
                    message_ids.append(added["message"]["id"])
            page_token = response.get("nextPageToken", "")
            if not page_token:
                latest_history_id = str(response.get("historyId", latest_history_id))
                break

        messages = [self._fetch(message_id) for message_id in message_ids]
        return messages, latest_history_id

    def _fetch(self, message_id: str) -> GmailMessage:
        raw = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = dict(raw["payload"])
        return GmailMessage(
            id=message_id,
            body_text=_extract_body_text(payload),
            attachments=self._fetch_attachments(message_id, payload),
        )

    def _fetch_attachments(
        self, message_id: str, payload: dict[str, Any]
    ) -> list[GmailAttachment]:
        attachments = []
        for filename, attachment_id in _iter_attachment_parts(payload):
            raw = (
                self._service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )
            data = base64.urlsafe_b64decode(raw["data"])
            attachments.append(GmailAttachment(filename=filename, data=data))
        return attachments


def _extract_body_text(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _extract_body_text(part)
        if text:
            return text
    return ""


def _iter_attachment_parts(payload: dict[str, Any]) -> list[tuple[str, str]]:
    found = []
    if payload.get("filename") and payload.get("body", {}).get("attachmentId"):
        found.append((payload["filename"], payload["body"]["attachmentId"]))
    for part in payload.get("parts", []):
        found.extend(_iter_attachment_parts(part))
    return found
