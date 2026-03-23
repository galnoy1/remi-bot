"""
calendar_sync.py — Google Calendar integration for Remi
Handles OAuth2 auth, reading events, and creating new ones
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKENS_DIR = Path(os.getenv("TOKENS_DIR", "tokens"))


def _token_path(user_id: int) -> Path:
    TOKENS_DIR.mkdir(exist_ok=True)
    return TOKENS_DIR / f"user_{user_id}.json"


def get_calendar_service(user_id: int):
    """Returns an authenticated Google Calendar service for this user, or None if not authorized."""
    token_path = _token_path(user_id)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        else:
            return None  # User needs to authorize first

    return build("calendar", "v3", credentials=creds)


def get_auth_url(user_id: int) -> str:
    """Returns a Google OAuth URL the user must visit to authorize."""
    client_secrets = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "client_secrets.json")
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets,
        SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=str(user_id),
    )
    return auth_url


def save_token_from_code(user_id: int, auth_code: str):
    """Exchange auth code for tokens and save them."""
    client_secrets = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "client_secrets.json")
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets,
        SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    flow.fetch_token(code=auth_code)
    creds = flow.credentials
    _token_path(user_id).write_text(creds.to_json())


def is_authorized(user_id: int) -> bool:
    return _token_path(user_id).exists()


# ── Reading events ────────────────────────────────────────

def get_events_today(user_id: int) -> list[dict]:
    return get_events_range(user_id, days=1)


def get_events_range(user_id: int, days: int = 7) -> list[dict]:
    """Returns upcoming events within the next N days."""
    service = get_calendar_service(user_id)
    if not service:
        return []

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days)).isoformat() + "Z"

    result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = []
    for e in result.get("items", []):
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        end = e["end"].get("dateTime", e["end"].get("date", ""))
        events.append({
            "id": e["id"],
            "title": e.get("summary", "(ללא כותרת)"),
            "start": start,
            "end": end,
            "location": e.get("location", ""),
            "description": e.get("description", ""),
        })
    return events


def format_events_hebrew(events: list[dict]) -> str:
    """Formats a list of events as a readable Hebrew WhatsApp message."""
    if not events:
        return "אין אירועים מתוכננים 📭"

    lines = []
    for e in events:
        start = e["start"]
        # Parse ISO datetime to readable
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            time_str = dt.strftime("%d/%m %H:%M")
        except Exception:
            time_str = start[:10]

        line = f"📅 {time_str} — {e['title']}"
        if e.get("location"):
            line += f"\n   📍 {e['location']}"
        lines.append(line)

    return "\n".join(lines)


# ── Creating events ───────────────────────────────────────

def create_event(
    user_id: int,
    title: str,
    start_dt: str,
    end_dt: str = None,
    location: str = None,
    description: str = None,
) -> dict | None:
    """
    Creates a Google Calendar event.
    start_dt / end_dt: ISO format strings, e.g. "2025-01-20T09:00:00"
    Returns the created event dict or None on failure.
    """
    service = get_calendar_service(user_id)
    if not service:
        return None

    # Default: 1-hour event
    if not end_dt:
        try:
            start = datetime.fromisoformat(start_dt)
            end_dt = (start + timedelta(hours=1)).isoformat()
        except Exception:
            end_dt = start_dt

    event_body = {
        "summary": title,
        "start": {"dateTime": start_dt, "timeZone": "Asia/Jerusalem"},
        "end": {"dateTime": end_dt, "timeZone": "Asia/Jerusalem"},
    }
    if location:
        event_body["location"] = location
    if description:
        event_body["description"] = description

    created = service.events().insert(calendarId="primary", body=event_body).execute()
    return {
        "id": created["id"],
        "title": created.get("summary"),
        "start": created["start"].get("dateTime"),
        "link": created.get("htmlLink"),
    }


def delete_event(user_id: int, event_id: str) -> bool:
    service = get_calendar_service(user_id)
    if not service:
        return False
    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return True
    except Exception:
        return False
