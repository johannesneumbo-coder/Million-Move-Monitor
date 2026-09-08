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
    os.getenv("CHECK_SECONDS", "5")
)

SCREENSHOT_FILE = Path(
    os.getenv(
        "SCREENSHOT_FILE",
        "/tmp/million_moves.png"
    )
)


def make_signal_key(signal):

    direction = signal.get(
        "direction"
    )

    entry = signal.get(
        "entry"
    )

    if entry is None:
        return None

    try:

        entry = round(
            float(entry),
            2
        )

    except Exception:

        return None

    # IMPORTANT:
    # Only BUY/SELL + ENTRY identifies
    # a signal.
    #
    # S/L and T/P are deliberately NOT
    # included because OCR can sometimes
    # read those values differently.
    #
    # Therefore the same signal cannot
    # create repeated WhatsApp messages.

    return (
        f"{direction}|"
        f"{entry:.2f}"
    )


def format_message(signal):

    direction = signal[
        "direction"
    ]

    entry = signal.get(
        "entry"
    )

    sl = signal.get(
        "sl"
    )

    tp = signal.get(
        "tp"
    )

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
        f"Detected from the Million Moves live stream."
    )


def save_page_screenshot(page):

    try:

        page.screenshot(
            path=str(
                SCREENSHOT_FILE
            ),
            type="png"
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

    with sync_playwright() as p:

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

            context = browser.new_context(
                viewport={
                    "width": 1920,
                    "height": 1080
                },
                device_scale_factor=1
            )

            page = context.new_page()

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

            try:

                page.get_by_role(
                    "button",
                    name="Accept all"
                ).click(
                    timeout=3000
                )

            except Exception:

                pass

            try:

                page.get_by_role(
                    "button",
                    name="Skip"
                ).click(
                    timeout=3000
                )

            except Exception:

                pass

            try:

                page.locator(
                    "video"
                ).click(
                    timeout=5000
                )

            except Exception:

                pass

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
                        "Screenshot saved:",
                        str(
                            SCREENSHOT_FILE
                        ),
                        flush=True
                    )

                    print(
                        "Reading screenshot...",
                        flush=True
                    )

                    frame = cv2.imread(
                        str(
                            SCREENSHOT_FILE
                        )
                    )

                    if frame is None:

                        print(
                            "Could not read screenshot.",
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

                        if signal_key is None:

                            print(
                                "Signal ignored: "
                                "no valid entry.",
                                flush=True
                            )

                            time.sleep(
                                CHECK_SECONDS
                            )

                            continue

                        print(
                            "Signal key:",
                            signal_key,
                            flush=True
                        )

                        if signal_already_sent(
                            signal_key
                        ):

                            print(
                                "Duplicate signal "
                                "ignored:",
                                signal_key,
                                flush=True
                            )

                        else:

                            print(
                                "NEW SIGNAL:",
                                signal_key,
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
                                    "WhatsApp message sent "
                                    "and signal saved.",
                                    flush=True
                                )

                            else:

                                print(
                                    "WhatsApp failed. "
                                    "Signal NOT marked "
                                    "as sent.",
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

                except Exception:

                    pass

    print(
        "Browser monitor stopped.",
        flush=True
    )


if __name__ == "__main__":

    monitor()