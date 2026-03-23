# רֶמי — WhatsApp AI Assistant

עוזר אישי חכם בוואטסאפ: ניהול משימות, תזכורות ויומן.

## ארכיטקטורה
WhatsApp → Twilio → FastAPI (Python) → Claude AI
                          ↕
                      SQLite DB + Scheduler

## קבצים
- main.py       — FastAPI server + Twilio webhook
- agent.py      — Claude AI brain
- database.py   — SQLite: משתמשים, משימות, תזכורות
- scheduler.py  — שולח תזכורות אוטומטיות

## התקנה

pip install -r requirements.txt
cp .env.example .env  # מלא מפתחות

uvicorn main:app --host 0.0.0.0 --port 8000
python scheduler.py  # בטרמינל נפרד

## מפתחות נדרשים
- ANTHROPIC_API_KEY   — console.anthropic.com
- TWILIO_ACCOUNT_SID  — twilio.com
- TWILIO_AUTH_TOKEN
- TWILIO_WHATSAPP_FROM

## Twilio Webhook
הגדר ב-Twilio Sandbox: POST → https://your-domain.com/webhook

## פריסה מהירה
Railway.app — הכי פשוט, ~$5/חודש

## חיבור Google Calendar

1. כנס ל-[Google Cloud Console](https://console.cloud.google.com)
2. צור פרויקט חדש → הפעל **Google Calendar API**
3. צור **OAuth 2.0 Client ID** (Desktop app)
4. הורד את `client_secrets.json` ושים אותו בתיקיית הפרויקט
5. הוסף ל-.env: `GOOGLE_CLIENT_SECRETS_FILE=client_secrets.json`

כשמשתמש שולח "חבר יומן", רֶמי ישלח לו קישור אישי לאישור.
לאחר האישור שולחים: AUTH:הקוד
