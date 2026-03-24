"""
רֶמי — WhatsApp AI Assistant
FastAPI backend connecting Twilio WhatsApp + Claude AI
"""

from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse
import anthropic
import os
from database import db
from agent import RemiAgent

app = FastAPI(title="Remi AI Assistant")
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

    # Get or create user
    user = db.get_or_create_user(user_phone)

    # Load conversation history (last 10 messages)
    history = db.get_history(user["id"], limit=10)

    # Let the agent process the message
    reply = await agent.process(
        user_id=user["id"],
        user_phone=user_phone,
        message=message_text,
        history=history,
        media_url=MediaUrl0,
        media_type=MediaContentType0,
    )

    # Save to history
    db.save_message(user["id"], "user", message_text or "[הודעה קולית]")
    db.save_message(user["id"], "assistant", reply)

    # Send back via Twilio TwiML — must return text/xml so Twilio parses it
    resp = MessagingResponse()
    resp.message(reply)
    return Response(content=str(resp), media_type="text/xml")


@app.get("/health")
def health():
    return {"status": "ok", "service": "remi-ai"}
