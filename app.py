import os
import hmac
import hashlib
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Twilio client ──────────────────────────────────────────────────────────────
def get_twilio_client():
    return Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(get_remote_address, app=app, default_limits=["10 per minute"])

# ── Signature verification ─────────────────────────────────────────────────────
def verify_retell_signature(req):
    """
    Retell signs every webhook with your API key.
    Header names confirmed from Retell docs — double-check in your Retell dashboard
    under Developer > Webhooks if verification keeps failing.
    """
    signature = req.headers.get("X-Retell-Signature", "")
    ts        = req.headers.get("X-Retell-Timestamp", "")
    body      = req.get_data(as_text=True)

    combined = ts + body
    expected = hmac.new(
        os.getenv("RETELL_API_KEY").encode(),  # ← your Retell API key from Retell dashboard
        combined.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)

# ── Health check ───────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ── Main webhook ───────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
@limiter.limit("5 per minute")
def webhook():
    # 1. Verify the request actually came from Retell
    if not verify_retell_signature(request):
        return jsonify({"error": "Unauthorized"}), 401

    # 2. Parse body
    data = request.get_json(silent=True) or {}

    # 3. Extract fields with length caps (prevents oversized injection payloads)
    #    ↓ these key names must match exactly what your Retell agent sends —
    #      check your agent's "Variables" tab in the Retell dashboard
    caller_name   = data.get("caller_name",  "Unknown")[:50]
    caller_number = data.get("caller_number", "Unknown")[:20]
    car_issue     = data.get("car_issue",     "Not specified")[:200]
    car_location  = data.get("car_location",  "Unknown")[:100]  # fixed typo from "can_location"

    # 4. Build SMS
    message = (
        f"📞 Missed Call\n"
        f"Name: {caller_name}\n"
        f"Number: {caller_number}\n"
        f"Issue: {car_issue}\n"
        f"Location: {car_location}"
    )

    # 5. Send SMS via Twilio — wrapped so errors don't leak stack traces
    try:
        get_twilio_client().messages.create(
            body=message,
            messaging_service_sid=os.getenv("TWILIO_MESSAGING_SERVICE_SID"),  # ← starts with MG...
            to=os.getenv("MECHANIC_PHONE")  # ← mechanic's number e.g. +14795551234
        )
    except Exception as e:
        print(f"[Twilio error] {e}")  # visible in Render logs, NOT in the HTTP response
        return jsonify({"status": "error"}), 500

    return jsonify({"status": "ok"}), 200

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=False)  # never True on Render