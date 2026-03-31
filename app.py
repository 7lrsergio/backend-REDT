import os
from flask import Flask, request, jsonify
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

@app.route("/webhook", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}  # ← this line was missing

    caller_name   = data.get("caller_name", "Unknown")
    caller_number = data.get("caller_number", "Unknown")
    car_issue     = data.get("car_issue", "Not specified")
    can_drive     = data.get("can_drive", "Unknown")

    message = (
        f"📞 Missed Call\n"
        f"Name: {caller_name}\n"
        f"Number: {caller_number}\n"
        f"Issue: {car_issue}\n"
        f"Driveable: {can_drive}"
    )

    client.messages.create(
        body=message,
        from_=os.getenv("TWILIO_FROM_NUMBER"),
        to=os.getenv("MECHANIC_PHONE")
    )

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(debug=True)