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
        "no_warnings": False,
        "skip_download": True,
        "noplaylist": True,
        "live_from_start": False,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            YOUTUBE_URL,
            download=False
        )

        if not info:
            raise RuntimeError(
                "YouTube did not return stream information."
            )

        # First try the URL selected by yt-dlp.
        direct_url = info.get("url")

        if direct_url:
            return direct_url

        # If there is no selected URL, find an available
        # video stream manually.
        formats = info.get("formats", [])

        video_formats = []

        for fmt in formats:
            url = fmt.get("url")

            if not url:
                continue

            protocol = str(fmt.get("protocol", "")).lower()
            height = fmt.get("height") or 0
            vcodec = fmt.get("vcodec")

            if vcodec and vcodec != "none":
                video_formats.append(
                    (
                        height,
                        protocol,
                        url
                    )
                )

        if not video_formats:
            raise RuntimeError(
                "No usable live video format was returned by YouTube."
            )

        # Prefer the highest available video format.
        video_formats.sort(
            key=lambda x: x[0],
            reverse=True
        )

        return video_formats[0][2]


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

    entry_text = (
        f"{entry:.2f}"
        if entry is not None
        else "Not detected"
    )

    sl_text = (
        f"{sl:.2f}"
        if sl is not None
        else "Not detected"
    )

    tp_text = (
        f"{tp:.2f}"
        if tp is not None
        else "Not detected"
    )

    emoji = "🟢" if direction == "BUY" else "🔴"

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
            print("Getting live YouTube stream...")

            stream_url = get_stream_url()

            print("Live stream URL obtained.")
            print("Connecting to live stream...")

            capture = cv2.VideoCapture(stream_url)

            if not capture.isOpened():
                raise RuntimeError(
                    "OpenCV could not open the YouTube stream."
                )

            print("Live stream connected.")

            while True:
                success, frame = capture.read()

                if not success:
                    print("Stream frame unavailable.")
                    break

                signal = detect_signal(frame)

                if signal:
                    print("Signal detected:", signal)

                    signal_key = make_signal_key(signal)

                    if not signal_already_sent(signal_key):
                        message = format_message(signal)

                        sent = send_whatsapp(message)

                        if sent:
                            set_last_signal(signal_key)
                            print(
                                "New signal sent to WhatsApp."
                            )
                        else:
                            print(
                                "WhatsApp message was not sent."
                            )

                time.sleep(CHECK_SECONDS)

        except Exception as e:
            print(
                "Monitor error:",
                type(e).__name__,
                str(e)
            )

        finally:
            if capture is not None:
                capture.release()

        print("Reconnecting to YouTube...")
        time.sleep(10)


if __name__ == "__main__":
    monitor()