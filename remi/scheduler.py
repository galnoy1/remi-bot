"""
scheduler.py — runs in background, sends WhatsApp reminders when due
Run separately: python scheduler.py
"""

import os
import time
from twilio.rest import Client as TwilioClient
from database import db

TWILIO_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM = os.environ["TWILIO_WHATSAPP_FROM"]  # e.g. "whatsapp:+14155238886"

twilio = TwilioClient(TWILIO_SID, TWILIO_TOKEN)


def send_reminder(phone: str, text: str):
    twilio.messages.create(
        from_=TWILIO_FROM,
        to=f"whatsapp:{phone}",
        body=f"⏰ תזכורת מרֶמי:\n{text}",
    )
    print(f"[scheduler] Sent reminder to {phone}: {text}")


def run():
    print("[scheduler] Starting reminder loop...")
    while True:
        try:
            pending = db.get_pending_reminders()
            for reminder in pending:
                send_reminder(reminder["phone"], reminder["text"])
                db.mark_reminder_sent(reminder["id"])
        except Exception as e:
            print(f"[scheduler] Error: {e}")
        time.sleep(30)  # Check every 30 seconds


if __name__ == "__main__":
    run()
