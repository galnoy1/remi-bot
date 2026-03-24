"""
רֶמי — WhatsApp AI Assistant
FastAPI backend connecting Twilio WhatsApp + Claude AI
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Form
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse
import asyncio
import os
from datetime import datetime, timedelta
from database import db
from agent import RemiAgent


# ── Background Scheduler ──────────────────────────────────────────────────────

async def scheduler_loop():
    """Runs in the background. Every 30 seconds checks for due reminders and sends them via WhatsApp."""
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    twilio_from = os.environ.get("TWILIO_WHATSAPP_FROM", "")

    if not all([twilio_sid, twilio_token, twilio_from]):
        print("[scheduler] Missing Twilio credentials — scheduler disabled.")
        return

    twilio = TwilioClient(twilio_sid, twilio_token)
    print("[scheduler] Started ✅ — checking every 30 seconds")

    while True:
        try:
            pending = db.get_pending_reminders()
            for reminder in pending:
                try:
                    twilio.messages.create(
                        from_=twilio_from,
                        to=f"whatsapp:{reminder['phone']}",
                        body=f"⏰ תזכורת מרֶמי:\n{reminder['text']}",
                    )
                    print(f"[scheduler] Sent to {reminder['phone']}: {reminder['text']}")

                    # Handle recurring reminders — reschedule next occurrence
                    recurring = reminder.get("recurring")
                    if recurring:
                        remind_at = datetime.strptime(reminder["remind_at"], "%Y-%m-%d %H:%M")
                        if recurring in ("daily", "יומי"):
                            next_at = remind_at + timedelta(days=1)
                        elif recurring in ("weekly", "שבועי"):
                            next_at = remind_at + timedelta(weeks=1)
                        elif recurring in ("monthly", "חודשי"):
                            next_at = remind_at + timedelta(days=30)
                        else:
                            next_at = None

                        if next_at:
                            db.add_reminder(
                                reminder["user_id"],
                                reminder["text"],
                                next_at.strftime("%Y-%m-%d %H:%M"),
                                recurring,
                            )

                    db.mark_reminder_sent(reminder["id"])

                except Exception as e:
                    print(f"[scheduler] Error sending to {reminder['phone']}: {e}")

        except Exception as e:
            print(f"[scheduler] Error checking reminders: {e}")

        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(scheduler_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Remi AI Assistant", lifespan=lifespan)
agent = RemiAgent()


@app.post("/webhook")
async def webhook(
    From: str = Form(...),
    Body: str = Form(...),
    MediaUrl0: str = Form(default=None),
    MediaContentType0: str = Form(default=None),
):
    """Twilio sends incoming WhatsApp messages here."""
    user_phone = From.replace("whatsapp:", "")
    message_text = Body.strip()

    user = db.get_or_create_user(user_phone)
    history = db.get_history(user["id"], limit=10)

    reply = await agent.process(
        user_id=user["id"],
        user_phone=user_phone,
        message=message_text,
        history=history,
        media_url=MediaUrl0,
        media_type=MediaContentType0,
    )

    db.save_message(user["id"], "user", message_text or "[הודעה קולית]")
    db.save_message(user["id"], "assistant", reply)

    resp = MessagingResponse()
    resp.message(reply)
    return Response(content=str(resp), media_type="text/xml")


@app.get("/health")
def health():
    return {"status": "ok", "service": "remi-ai"}
