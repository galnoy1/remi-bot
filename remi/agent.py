"""
RemiAgent — Claude-powered AI brain
Understands Hebrew, extracts intents, manages tasks, reminders & Google Calendar
"""

import os
import json
import tempfile
import requests
from datetime import datetime
import anthropic
from database import db
from calendar_sync import (
    get_events_today, get_events_range, create_event,
    format_events_hebrew, get_auth_url,
    save_token_from_code, is_authorized,
)

SYSTEM_PROMPT = """אתה רֶמי — עוזר אישי חכם בוואטסאפ, שמדבר עברית בצורה טבעית וחברותית.

תפקידך:
1. לנהל משימות — להוסיף, לסמן כבוצע, להציג רשימה
2. לנהל תזכורות — להגדיר תזכורות חד-פעמיות או חוזרות
3. לנהל יומן Google Calendar — לקרוא אירועים, ליצור פגישות חדשות
4. לענות לשאלות כלליות ולשוחח בצורה אנושית

תגיב תמיד עם JSON בלבד:
{
  "reply": "תשובה בעברית",
  "action": null | "add_task" | "list_tasks" | "complete_task" |
             "add_reminder" | "list_reminders" |
             "get_calendar_today" | "get_calendar_week" |
             "create_calendar_event" | "auth_google",
  "data": {}
}

דוגמאות ל-data:
- add_task: {"title": "לשלם חשבון", "due_at": "2025-01-20 10:00"}
- complete_task: {"task_id": 3}
- add_reminder: {"text": "פגישה", "remind_at": "2025-01-20 09:00", "recurring": null}
- create_calendar_event: {"title": "פגישת צוות", "start_dt": "2025-01-20T10:00:00", "end_dt": "2025-01-20T11:00:00", "location": "משרד"}

היום: {today} | שעה: {time}
"""


class RemiAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def _transcribe_audio(self, media_url: str) -> str:
        """Download audio from Twilio and transcribe using OpenAI Whisper."""
        try:
            import openai
            account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
            auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
            openai_key = os.environ.get("OPENAI_API_KEY", "")
            if not openai_key:
                return ""
            # Download audio from Twilio (requires auth)
            r = requests.get(media_url, auth=(account_sid, auth_token), timeout=15)
            if r.status_code != 200:
                return ""
            # Save to temp file
            suffix = ".ogg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(r.content)
                tmp_path = tmp.name
            # Transcribe with Whisper
            oai = openai.OpenAI(api_key=openai_key)
            with open(tmp_path, "rb") as audio_file:
                transcript = oai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="he",
                )
            os.unlink(tmp_path)
            return transcript.text.strip()
        except Exception as e:
            print(f"[transcribe] error: {e}")
            return ""

    async def process(self, user_id, user_phone, message, history, media_url=None, media_type=None):

        # Handle voice messages
        is_audio = media_type and media_type.startswith("audio/")
        if is_audio and media_url:
            transcribed = self._transcribe_audio(media_url)
            if transcribed:
                message = f"[הודעה קולית]: {transcribed}"
            elif not os.environ.get("OPENAI_API_KEY"):
                return "🎤 קיבלתי הודעה קולית! כדי שאוכל להבין אותה, צריך להוסיף OPENAI_API_KEY להגדרות ב-Railway."
            else:
                return "🎤 לא הצלחתי לתמלל את ההודעה הקולית. נסה שוב אה כתוב טקסט."

        # Google auth code flow
        if message.startswith("AUTH:") and len(message) > 10:
            code = message[5:].strip()
            try:
                save_token_from_code(user_id, code)
                return "✅ היומן חובר בהצלחה! עכשיו אני רואה ומעדכן את Google Calendar שלך 🗓️"
            except Exception as e:
                return f"❌ לא הצלחתי לחבר. נסה שוב.\nשגיאה: {e}"

        today = datetime.now().strftime("%Y-%m-%d")
        time_now = datetime.now().strftime("%H:%M")
        system = SYSTEM_PROMPT.replace("{today}", today).replace("{time}", time_now)

        messages = [{"role": h["role"], "content": h["content"]} for h in history]

        user_content = message
        if any(kw in message for kw in ["משימות", "תזכורות", "מה יש", "לוז", "היום", "מחר", "שבוע"]):
            tasks = db.get_tasks(user_id)
            ctx = f"\n[משימות פתוחות: {json.dumps([t['title'] for t in tasks], ensure_ascii=False)}]"
            if is_authorized(user_id):
                events = get_events_today(user_id)
                ctx += f"\n[אירועים היום: {json.dumps([e['title']+' '+e['start'] for e in events], ensure_ascii=False)}]"
            user_content = message + ctx

        messages.append({"role": "user", "content": user_content})

        resp = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system,
            messages=messages,
        )

        raw = resp.content[0].text.strip()
        # Strip markdown code block wrapper if present (e.g. ```json ... ```)
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw

        reply = parsed.get("reply", "סליחה, לא הצלחתי להבין 🙏")
        action = parsed.get("action")
        data = parsed.get("data", {})

        if action == "add_task":
            tid = db.add_task(user_id, data.get("title", message), data.get("due_at"))
            reply += f"\n✅ נוסף (#{tid})"

        elif action == "list_tasks":
            tasks = db.get_tasks(user_id)
            reply = ("המשימות שלך:\n" + "\n".join(f"⬜ #{t['id']} {t['title']}" for t in tasks)) if tasks else "אין משימות פתוחות 🎉"

        elif action == "complete_task":
            db.complete_task(data.get("task_id"), user_id)

        elif action == "add_reminder":
            rid = db.add_reminder(user_id, data.get("text", message), data.get("remind_at"), data.get("recurring"))
            reply += f"\n⏰ נשמר (#{rid})"

        elif action == "list_reminders":
            pending = [r for r in db.get_pending_reminders() if r.get("user_id") == user_id]
            reply = ("התזכורות הקרובות:\n" + "\n".join(f"⏰ {r['text']} — {r['remind_at']}" for r in pending)) if pending else "אין תזכורות 📭"

        elif action == "auth_google":
            if is_authorized(user_id):
                reply = "היומן כבר מחובר ✅"
            else:
                url = get_auth_url(user_id)
                reply = f"לחיבור Google Calendar:\n\n1️⃣ כנס לקישור:\n{url}\n\n2️⃣ אשר גישה\n3️⃣ שלח לי: AUTH:הקוד"

        elif action in ("get_calendar_today", "get_calendar_week"):
            if not is_authorized(user_id):
                reply = "שלח *חבר יומן* כדי לחבר את Google Calendar"
            else:
                days = 1 if action == "get_calendar_today" else 7
                events = get_events_range(user_id, days=days)
                label = "היום" if days == 1 else "השבוע"
                reply = f"📅 האירועים {label}:\n\n" + format_events_hebrew(events)

        elif action == "create_calendar_event":
            if not is_authorized(user_id):
                reply = "שלח *חבר יומן* כדי לחבר את Google Calendar"
            else:
                event = create_event(user_id, title=data.get("title", "אירוע"), start_dt=data.get("start_dt"),
                                     end_dt=data.get("end_dt"), location=data.get("location"))
                if event:
                    reply = f"✅ נוסף ליומן!\n📅 {event['title']}\n🕐 {event['start']}"
                    if event.get("link"):
                        reply += f"\n🔗 {event['link']}"
                else:
                    reply = "❌ לא הצלחתי להוסיף ליומן. נסה שוב."

        return reply
