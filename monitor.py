import os
import time
from pathlib import Path

import cv2
import numpy as np

from playwright.sync_api import sync_playwright

from detector import detect_signal
from storage import signal_already_sent, set_last_signal
from whatsapp import send_whatsapp


YOUTUBE_URL = os.getenv(
    "YOUTUBE_URL",
    "https://www.youtube.com/watch?v=-ps7V40GrA4"
)

CHECK_SECONDS = int(
    os.getenv("CHECK_SECONDS", "3")
)

SCREENSHOT_FILE = Path(
    os.getenv("SCREENSHOT_FILE", "/tmp/million_moves.png")
)


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
        f"Detected from the Million Moves live stream."
    )


def save_page_screenshot(page):
    try:
        page.screenshot(
            path=str(SCREENSHOT_FILE),
            type="png"
        )
        return True

    except Exception as e:
        print(
            "Screenshot error:",
            type(e).__name__,
            str(e)
        )
        return False


def monitor():
    print("Million Moves browser monitor started.")
    print("YouTube:", YOUTUBE_URL)

    with sync_playwright() as p:

        browser = None

        try:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--autoplay-policy=no-user-gesture-required"
                ]
            )

            context = browser.new_context(
                viewport={
                    "width": 1920,
                    "height": 1080
                },
                device_scale_factor=1
            )

            page = context.new_page()

            print("Opening YouTube live page...")

            page.goto(
                YOUTUBE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print("YouTube page opened.")

            time.sleep(10)

            # Attempt to dismiss common YouTube overlays.
            try:
                page.get_by_role(
                    "button",
                    name="Accept all"
                ).click(timeout=3000)
                print("YouTube consent accepted.")

            except Exception:
                pass

            try:
                page.get_by_role(
                    "button",
                    name="Skip"
                ).click(timeout=3000)

            except Exception:
                pass

            # Attempt to start the video.
            try:
                page.locator(
                    "video"
                ).click(timeout=5000)

            except Exception:
                pass

            time.sleep(5)

            print("Browser monitoring is active.")

            while True:

                try:
                    if page.is_closed():
                        raise RuntimeError(
                            "YouTube browser page closed."
                        )

                    save_page_screenshot(page)

                    frame = cv2.imread(
                        str(SCREENSHOT_FILE)
                    )

                    if frame is None:
                        print(
                            "Could not read browser screenshot."
                        )

                        time.sleep(CHECK_SECONDS)
                        continue

                    signal = detect_signal(frame)

                    if signal:

                        print(
                            "Signal detected:",
                            signal
                        )

                        signal_key = make_signal_key(
                            signal
                        )

                        if not signal_already_sent(
                            signal_key
                        ):

                            message = format_message(
                                signal
                            )

                            sent = send_whatsapp(
                                message
                            )

                            if sent:
                                set_last_signal(
                                    signal_key
                                )

                                print(
                                    "New signal sent to WhatsApp."
                                )

                    time.sleep(CHECK_SECONDS)

                except Exception as e:

                    print(
                        "Monitoring error:",
                        type(e).__name__,
                        str(e)
                    )

                    time.sleep(10)

        except Exception as e:

            print(
                "Browser startup error:",
                type(e).__name__,
                str(e)
            )

        finally:

            if browser is not None:

                try:
                    browser.close()

                except Exception:
                    pass

    print("Browser monitor stopped.")


if __name__ == "__main__":
    monitor()