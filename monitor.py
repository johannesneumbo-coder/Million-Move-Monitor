import os
import time
import cv2
import yt_dlp

from detector import detect_signal
from storage import signal_already_sent, set_last_signal
from whatsapp import send_whatsapp


YOUTUBE_URL = os.getenv(
    "YOUTUBE_URL",
    "https://www.youtube.com/watch?v=-ps7V40GrA4"
)

CHECK_SECONDS = int(os.getenv("CHECK_SECONDS", "3"))


def get_stream_url():
    options = {
        "quiet": True,
        "no_warnings": True,
        "format": "best[height<=720]/best"
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            YOUTUBE_URL,
            download=False
        )

        return info.get("url")


def make_signal_key(signal):
    direction = signal.get("direction")
    entry = signal.get("entry")
    sl = signal.get("sl")
    tp = signal.get("tp")

    return f"{direction}|{entry}|{sl}|{tp}"


def format_message(signal):
    direction = signal["direction"]

    entry = signal.get("entry")
    sl = signal.get("sl")
    tp = signal.get("tp")

    entry_text = f"{entry:.2f}" if entry is not None else "Detected"
    sl_text = f"{sl:.2f}" if sl is not None else "Not detected"
    tp_text = f"{tp:.2f}" if tp is not None else "Not detected"

    if direction == "BUY":
        emoji = "🟢"
    else:
        emoji = "🔴"

    return (
        f"{emoji} MILLION MOVES V5 SIGNAL\n\n"
        f"XAUUSD 1M\n"
        f"{direction}\n\n"
        f"ENTRY: {entry_text}\n"
        f"S/L: {sl_text}\n"
        f"T/P: {tp_text}\n\n"
        f"Detected from the live TradingView stream."
    )


def monitor():
    print("Million Moves monitor started.")
    print("YouTube:", YOUTUBE_URL)

    while True:
        capture = None

        try:
            stream_url = get_stream_url()

            if not stream_url:
                print("Could not obtain live stream URL.")
                time.sleep(15)
                continue

            print("Live stream connected.")

            capture = cv2.VideoCapture(stream_url)

            if not capture.isOpened():
                print("Could not open live stream.")
                time.sleep(15)
                continue

            while True:
                success, frame = capture.read()

                if not success:
                    print("Stream frame unavailable.")
                    break

                signal = detect_signal(frame)

                if signal:
                    signal_key = make_signal_key(signal)

                    print("SIGNAL:", signal)

                    if not signal_already_sent(signal_key):
                        message = format_message(signal)

                        sent = send_whatsapp(message)

                        if sent:
                            set_last_signal(signal_key)
                            print("New signal sent.")

                time.sleep(CHECK_SECONDS)

        except Exception as e:
            print("Monitor error:", e)

        finally:
            if capture is not None:
                capture.release()

        print("Reconnecting...")
        time.sleep(10)


if __name__ == "__main__":
    monitor()