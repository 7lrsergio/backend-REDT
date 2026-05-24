import os
import json
import hmac
import hashlib
import time
import threading
import requests
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

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

def get_twilio_client():
    return Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

limiter = Limiter(key_func=get_remote_address, app=app, default_limits=["10 per minute"])

def fetch_and_send(call_id, from_number):
    time.sleep(10)  # wait for Retell analysis to finish

    try:
        resp = requests.get(
            f"https://api.retellai.com/v2/get-call/{call_id}",
            headers={"Authorization": f"Bearer {os.getenv('RETELL_API_KEY')}"}
        )
        call_data = resp.json()
        print("[DEBUG fetched call]", json.dumps(call_data.get("call_analysis", {}), indent=2))
    except Exception as e:
        print(f"[Retell fetch error] {e}")
        return

    analysis = call_data.get("call_analysis", {})
    custom   = analysis.get("custom_analysis_data", {})

    caller_name   = custom.get("caller_name",  "Unknown")[:50]
    car_issue     = custom.get("car_issue",    "Not specified")[:200]
    car_location  = custom.get("car_location", "Unknown")[:100]
    caller_number = from_number[:20]

    print(f"[DEBUG] name={caller_name} issue={car_issue} location={car_location} number={caller_number}")

    message = (
        f"📞 Missed Call\n"
        f"Name: {caller_name}\n"
        f"Number: {caller_number}\n"
        f"Issue: {car_issue}\n"
        f"Location: {car_location}"
    )

    try:
        get_twilio_client().messages.create(
            body=message,
            messaging_service_sid=os.getenv("TWILIO_MESSAGING_SERVICE_SID"),
            to=os.getenv("MECHANIC_PHONE")
        )
        print("[SMS sent]")
    except Exception as e:
        print(f"[Twilio error] {e}")

@app.route("/webhook", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/webhook", methods=["POST"])
@limiter.exempt
def webhook():
    data = request.get_json(silent=True) or {}

    event = data.get("event") or data.get("event_type") or data.get("type", "")
    if event != "call_ended":
        return jsonify({"status": "ignored"}), 200

    call        = data.get("call", {})
    call_id     = call.get("call_id", "")
    from_number = call.get("from_number", "Unknown")

    print(f"[call_ended] call_id={call_id} from={from_number}")

    threading.Thread(target=fetch_and_send, args=(call_id, from_number), daemon=True).start()

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(debug=False)
