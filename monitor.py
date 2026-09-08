import os
import time
from pathlib import Path

import cv2
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
    os.getenv(
        "SCREENSHOT_FILE",
        "/tmp/million_moves.png"
    )
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

    print(
        "Taking screenshot...",
        flush=True
    )

    try:

        page.screenshot(
            path=str(SCREENSHOT_FILE),
            type="png"
        )

        print(
            "Screenshot saved:",
            str(SCREENSHOT_FILE),
            flush=True
        )

        return True

    except Exception as e:

        print(
            "Screenshot error:",
            type(e).__name__,
            str(e),
            flush=True
        )

        return False


def monitor():

    print(
        "Million Moves browser monitor started.",
        flush=True
    )

    print(
        "YouTube:",
        YOUTUBE_URL,
        flush=True
    )

    print(
        "Starting Playwright...",
        flush=True
    )

    with sync_playwright() as p:

        print(
            "Playwright started.",
            flush=True
        )

        browser = None

        try:

            print(
                "Launching Chromium...",
                flush=True
            )

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--autoplay-policy=no-user-gesture-required"
                ]
            )

            print(
                "Chromium launched.",
                flush=True
            )

            context = browser.new_context(
                viewport={
                    "width": 1920,
                    "height": 1080
                },
                device_scale_factor=1
            )

            print(
                "Browser context created.",
                flush=True
            )

            page = context.new_page()

            print(
                "Browser page created.",
                flush=True
            )

            print(
                "Opening YouTube live page...",
                flush=True
            )

            page.goto(
                YOUTUBE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print(
                "YouTube page opened.",
                flush=True
            )

            time.sleep(10)

            print(
                "Checking YouTube consent...",
                flush=True
            )

            try:

                page.get_by_role(
                    "button",
                    name="Accept all"
                ).click(
                    timeout=3000
                )

                print(
                    "YouTube consent accepted.",
                    flush=True
                )

            except Exception:

                print(
                    "No consent button found.",
                    flush=True
                )

            print(
                "Checking Skip button...",
                flush=True
            )

            try:

                page.get_by_role(
                    "button",
                    name="Skip"
                ).click(
                    timeout=3000
                )

                print(
                    "Skip button clicked.",
                    flush=True
                )

            except Exception:

                print(
                    "No Skip button found.",
                    flush=True
                )

            print(
                "Checking video element...",
                flush=True
            )

            try:

                page.locator(
                    "video"
                ).click(
                    timeout=5000
                )

                print(
                    "Video clicked.",
                    flush=True
                )

            except Exception:

                print(
                    "Video click not required.",
                    flush=True
                )

            time.sleep(5)

            print(
                "Browser monitoring is active.",
                flush=True
            )

            while True:

                try:

                    print(
                        "Monitor loop running...",
                        flush=True
                    )

                    if page.is_closed():

                        raise RuntimeError(
                            "YouTube browser page closed."
                        )

                    if not save_page_screenshot(
                        page
                    ):

                        time.sleep(
                            CHECK_SECONDS
                        )

                        continue

                    print(
                        "Reading screenshot...",
                        flush=True
                    )

                    frame = cv2.imread(
                        str(SCREENSHOT_FILE)
                    )

                    if frame is None:

                        print(
                            "Could not read browser screenshot.",
                            flush=True
                        )

                        time.sleep(
                            CHECK_SECONDS
                        )

                        continue

                    print(
                        "Running signal detector...",
                        flush=True
                    )

                    signal = detect_signal(
                        frame
                    )

                    if signal:

                        print(
                            "Signal detected:",
                            signal,
                            flush=True
                        )

                        signal_key = (
                            make_signal_key(
                                signal
                            )
                        )

                        if not signal_already_sent(
                            signal_key
                        ):

                            print(
                                "New signal. Sending WhatsApp...",
                                flush=True
                            )

                            message = (
                                format_message(
                                    signal
                                )
                            )

                            sent = (
                                send_whatsapp(
                                    message
                                )
                            )

                            if sent:

                                set_last_signal(
                                    signal_key
                                )

                                print(
                                    "New signal sent to WhatsApp.",
                                    flush=True
                                )

                    else:

                        print(
                            "No signal detected.",
                            flush=True
                        )

                    time.sleep(
                        CHECK_SECONDS
                    )

                except Exception as e:

                    print(
                        "Monitoring error:",
                        type(e).__name__,
                        str(e),
                        flush=True
                    )

                    time.sleep(10)

        except Exception as e:

            print(
                "Browser startup error:",
                type(e).__name__,
                str(e),
                flush=True
            )

        finally:

            print(
                "Closing browser...",
                flush=True
            )

            if browser is not None:

                try:

                    browser.close()

                    print(
                        "Browser closed.",
                        flush=True
                    )

                except Exception as e:

                    print(
                        "Browser close error:",
                        type(e).__name__,
                        str(e),
                        flush=True
                    )

    print(
        "Browser monitor stopped.",
        flush=True
    )


if __name__ == "__main__":

    monitor()