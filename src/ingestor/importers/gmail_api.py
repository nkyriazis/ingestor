from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build

from ingestor.google_auth import load_credentials
from ingestor.importers.gmail import GmailAttachment, GmailMessage


class RealGmailClient:
    """Talks to the real Gmail API. Requires the shared Google OAuth token
    (see ingestor.google_auth, README) — not exercised by the automated
    test suite, which uses a fake GmailClient against the same Protocol
    instead.

    Uses Gmail's History API for incremental sync: the checkpoint is a
    `historyId`, not a message ID (message IDs aren't chronologically
    orderable, so "give me messages after this one" isn't a query Gmail
    supports). On first run — no checkpoint yet — this bootstraps the
    checkpoint to the mailbox's current historyId without backfilling any
    existing mail, since a personal ingestion pipeline should start from
    "now", not replay the whole inbox.

    `label` scopes which label's history to watch (defaults to INBOX,
    matching the prior hardcoded behavior); `query` additionally restricts
    to messages matching a Gmail search (`q=`) string. The History API has
    no `q=` parameter itself, so `query` is applied as a second pass: see
    `filter_by_query`.
    """

    def __init__(
        self, token_path: Path, label: str | None = None, query: str | None = None
    ) -> None:
        self._service = build("gmail", "v1", credentials=load_credentials(token_path))
        if label is None:
            self._label_id = "INBOX"
        else:
            labels = self._service.users().labels().list(userId="me").execute()
            self._label_id = resolve_label_id(labels.get("labels", []), label)
        self._query = query

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
                    labelId=self._label_id,
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

        if self._query is not None and message_ids:
            message_ids = self._apply_query_filter(message_ids, self._query)

        messages = [self._fetch(message_id) for message_id in message_ids]
        return messages, latest_history_id

    def _apply_query_filter(self, message_ids: list[str], query: str) -> list[str]:
        # Newly-discovered messages are, by construction, recent — and Gmail
        # orders q= results newest-first — so a single unpaginated page is
        # always enough to cover them at personal-mailbox polling cadence.
        response = (
            self._service.users()
            .messages()
            .list(userId="me", q=query, labelIds=[self._label_id], maxResults=500)
            .execute()
        )
        matching_ids = {message["id"] for message in response.get("messages", [])}
        return filter_by_query(message_ids, matching_ids)

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


def resolve_label_id(labels: Sequence[Mapping[str, Any]], label_name: str) -> str:
    """Gmail's system labels (INBOX, SENT, ...) use their own name as their
    id, but user-created labels have generated ids unrelated to their
    display name — so a configured label name needs a lookup against the
    account's actual labels, not a string-uppercase guess.
    """
    for label in labels:
        if label["name"] == label_name:
            return str(label["id"])
    raise ValueError(f"No Gmail label named {label_name!r} found")


def filter_by_query(message_ids: list[str], matching_ids: set[str]) -> list[str]:
    """Gmail's History API has no `q=` search parameter, so an additional
    free-text query filter is applied by intersecting newly-discovered
    message ids against a separate `messages.list(q=...)` call's results.
    """
    return [message_id for message_id in message_ids if message_id in matching_ids]


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
