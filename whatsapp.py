import os
import requests
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "").strip()
WHATSAPP_TO = os.getenv("WHATSAPP_TO", "").strip().replace("+", "").replace(" ", "")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0").strip()


def send_whatsapp(message):

    if not WHATSAPP_TOKEN:
        print("WHATSAPP ERROR: WHATSAPP_TOKEN is missing.", flush=True)
        return False

    if not PHONE_NUMBER_ID:
        print("WHATSAPP ERROR: PHONE_NUMBER_ID is missing.", flush=True)
        return False

    if not WHATSAPP_TO:
        print("WHATSAPP ERROR: WHATSAPP_TO is missing.", flush=True)
        return False

    url = (
        f"https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": WHATSAPP_TO,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": str(message)
        }
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        if response.ok:
            print("WHATSAPP API ACCEPTED MESSAGE.", flush=True)
            return True

        print(
            "WHATSAPP ERROR:",
            response.status_code,
            response.text,
            flush=True
        )

        return False

    except requests.RequestException as error:
        print(
            "WHATSAPP CONNECTION ERROR:",
            str(error),
            flush=True
        )

        return False