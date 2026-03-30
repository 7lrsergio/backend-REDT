import os
from flask import Flask, request, jsonify
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()  # loads your .env file

app = Flask(__name__)

# Twilio client setup
client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

# ─────────────────────────────────────────
# This route is what Retell calls when a
# call ends. It sends the call data here.
# ─────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}

    # Pull info from what Retell sends
    caller_name   = data.get("caller_name", "Unknown")
    caller_number = data.get("caller_number", "Unknown")
    car_issue     = data.get("car_issue", "Not specified")
    can_drive     = data.get("can_drive", "Unknown")

    # Build the SMS message Miguel will receive
    message = (
        f"📞 Missed Call\n"
        f"Name: {caller_name}\n"
        f"Number: {caller_number}\n"
        f"Issue: {car_issue}\n"
        f"Driveable: {can_drive}"
    )

    # Send the SMS via Twilio
    client.messages.create(
        body=message,
        from_=os.getenv("TWILIO_FROM_NUMBER"),
        to=os.getenv("MECHANIC_PHONE")
    )

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=True)