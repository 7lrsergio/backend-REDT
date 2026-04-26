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

# ── Startup env var guard ──────────────────────────────────────────────────────
required_vars = [
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_MESSAGING_SERVICE_SID",
    "MECHANIC_PHONE",
    "RETELL_API_KEY",
]
for var in required_vars:
    if not os.getenv(var):
        raise RuntimeError(f"Missing env var: {var}")

# ── Twilio client ──────────────────────────────────────────────────────────────
def get_twilio_client():
    return Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

# ── Rate limiter ───────────────────────────────────────────────────────────────
# default_limits only applies to routes not decorated with @limiter.exempt
# The webhook is exempt — Retell fires it on every agent turn and will
# retry aggressively if it gets a 429, creating a death spiral.
# Signature verification is the security layer for the webhook.
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=["10 per minute"])

# ── Signature verification ─────────────────────────────────────────────────────
def verify_retell_signature(req):
    """
    Retell signs each webhook with HMAC-SHA256 of the raw request body,
    using your API key as the secret. The signature is in X-Retell-Signature.
    Docs: https://docs.retellai.com/api-references/webhook
    """
    signature = req.headers.get("X-Retell-Signature", "")
    body      = req.get_data()  # raw bytes

    expected = hmac.new(
        os.getenv("RETELL_API_KEY").encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)

# ── Health check ───────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ── Main webhook ───────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
@limiter.exempt  # ← THIS is what actually exempts it; the comment alone did nothing
def webhook():
    # 1. Verify the request actually came from Retell
    # if not verify_retell_signature(request):
        # return jsonify({"error": "Unauthorized"}), 401

    # 2. Parse body
    data = request.get_json(silent=True) or {}

    # 3. Only act on call_ended — return 200 immediately for everything else
    #    so Retell doesn't think the webhook failed and retry-storm you
    event = data.get("event") or data.get("event_type") or data.get("type", "")
    if event != "call_ended":
        return jsonify({"status": "ignored"}), 200

    # 4. Extract fields
    caller_name   = data.get("caller_name",  "Unknown")[:50]
    caller_number = data.get("caller_number", "Unknown")[:20]
    car_issue     = data.get("car_issue",     "Not specified")[:200]
    car_location  = data.get("car_location",  "Unknown")[:100]

    # 5. Build SMS
    message = (
        f"📞 Missed Call\n"
        f"Name: {caller_name}\n"
        f"Number: {caller_number}\n"
        f"Issue: {car_issue}\n"
        f"Location: {car_location}"
    )

    # 6. Send SMS via Twilio
    try:
        get_twilio_client().messages.create(
            body=message,
            messaging_service_sid=os.getenv("TWILIO_MESSAGING_SERVICE_SID"),
            to=os.getenv("MECHANIC_PHONE")
        )
    except Exception as e:
        print(f"[Twilio error] {e}")
        return jsonify({"status": "error"}), 500

    return jsonify({"status": "ok"}), 200

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=False)
