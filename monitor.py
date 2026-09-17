import os
import time

import cv2
import numpy as np

from playwright.sync_api import sync_playwright

from detector import detect_signal
from storage import signal_already_sent, set_last_signal
from whatsapp import send_whatsapp


# ============================================================
# CONFIGURATION
# ============================================================

YOUTUBE_URL = os.getenv(
    "YOUTUBE_URL",
    "https://www.youtube.com/watch?v=-ps7V40GrA4"
)

CHECK_SECONDS = max(
    5,
    int(os.getenv("CHECK_SECONDS", "5"))
)

RESTART_SECONDS = 10

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720


# ============================================================
# SIGNAL KEY
# ============================================================

def make_signal_key(signal):

    direction = str(
        signal.get("direction", "")
    ).upper()

    entry = signal.get("entry")

    if direction not in ("BUY", "SELL"):
        return None

    if entry is None:
        return None

    try:

        entry = round(float(entry), 2)

    except (TypeError, ValueError):
        return None

    return f"{direction}|{entry:.2f}"


# ============================================================
# PRICE FORMATTING
# ============================================================

def price_text(value):

    if value is None:
        return "Not confirmed"

    try:

        return f"{float(value):.2f}"

    except (TypeError, ValueError):
        return "Not confirmed"


# ============================================================
# WHATSAPP MESSAGE
# ============================================================

def format_message(signal):

    direction = signal["direction"]

    emoji = (
        "🟢"
        if direction == "BUY"
        else "🔴"
    )

    return (
        f"{emoji} MILLION MOVES V5 SIGNAL\n\n"
        f"XAUUSD 1M\n"
        f"{direction}\n\n"
        f"ENTRY: {price_text(signal.get('entry'))}\n"
        f"S/L: {price_text(signal.get('sl'))}\n"
        f"TP1: {price_text(signal.get('tp1'))}\n"
        f"TP2: {price_text(signal.get('tp2'))}\n"
        f"TP3: {price_text(signal.get('tp3'))}\n\n"
        f"Detected from the Million Moves stream."
    )


# ============================================================
# START VIDEO
# ============================================================

def start_video(page):

    print(
        "Opening YouTube...",
        flush=True
    )

    page.goto(
        YOUTUBE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(5000)

    # Cookie consent
    try:

        page.get_by_role(
            "button",
            name="Accept all"
        ).click(timeout=2000)

    except Exception:
        pass

    # YouTube skip button
    try:

        page.get_by_role(
            "button",
            name="Skip"
        ).click(timeout=2000)

    except Exception:
        pass

    video = page.locator("video").first

    video.wait_for(
        state="attached",
        timeout=30000
    )

    try:

        video.evaluate(
            """video => {
                video.muted = true;
                video.play().catch(() => {});
            }"""
        )

    except Exception as error:

        print(
            "Video playback request:",
            str(error),
            flush=True
        )

    page.wait_for_timeout(5000)

    print(
        "YouTube video initialized.",
        flush=True
    )


# ============================================================
# CAPTURE VIDEO
# ============================================================

def capture_video(page):

    video = page.locator("video").first

    # Check that the video exists.
    if video.count() == 0:

        print(
            "Video element missing.",
            flush=True
        )

        return None

    # Confirm that actual video frames are available.
    state = video.evaluate(
        """video => ({
            ready: video.readyState,
            width: video.videoWidth,
            height: video.videoHeight,
            paused: video.paused
        })"""
    )

    print(
        "VIDEO STATE:",
        state,
        flush=True
    )

    if (
        state["ready"] < 2
        or state["width"] == 0
        or state["height"] == 0
    ):

        print(
            "Video frame not ready.",
            flush=True
        )

        return None

    # Screenshot only the video, not the entire page.
    screenshot = video.screenshot(
        type="jpeg",
        quality=80,
        timeout=15000,
        animations="disabled"
    )

    image_array = np.frombuffer(
        screenshot,
        dtype=np.uint8
    )

    frame = cv2.imdecode(
        image_array,
        cv2.IMREAD_COLOR
    )

    if frame is None:

        print(
            "Screenshot decoding failed.",
            flush=True
        )

        return None

    print(
        "Video frame captured:",
        frame.shape,
        flush=True
    )

    return frame


# ============================================================
# PROCESS SIGNAL
# ============================================================

def process_signal(signal):

    if not signal:

        print(
            "No signal detected.",
            flush=True
        )

        return

    print(
        "SIGNAL DETECTED:",
        signal,
        flush=True
    )

    signal_key = make_signal_key(
        signal
    )

    if signal_key is None:

        print(
            "Invalid signal key.",
            flush=True
        )

        return

    if signal_already_sent(signal_key):

        print(
            "Duplicate signal ignored:",
            signal_key,
            flush=True
        )

        return

    message = format_message(
        signal
    )

    print(
        "Sending WhatsApp:",
        signal_key,
        flush=True
    )

    sent = send_whatsapp(
        message
    )

    if sent:

        set_last_signal(
            signal_key
        )

        print(
            "WhatsApp sent. Signal saved.",
            flush=True
        )

    else:

        print(
            "WhatsApp failed. Signal not saved.",
            flush=True
        )


# ============================================================
# BROWSER SESSION
# ============================================================

def run_browser_session(playwright):

    browser = None

    try:

        print(
            "Launching Chromium...",
            flush=True
        )

        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-renderer-backgrounding",
                "--no-first-run",
                "--autoplay-policy=no-user-gesture-required"
            ]
        )

        context = browser.new_context(
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT
            },
            device_scale_factor=1,
            reduced_motion="reduce"
        )

        page = context.new_page()

        page.set_default_timeout(
            15000
        )

        # Avoid loading unnecessary images and fonts.
        # Do not block YouTube scripts or video resources.
        def block_resources(route):

            resource_type = route.request.resource_type

            if resource_type in (
                "image",
                "font"
            ):

                route.abort()

            else:

                route.continue_()

        page.route(
            "**/*",
            block_resources
        )

        start_video(
            page
        )

        print(
            "Browser monitoring active.",
            flush=True
        )

        while True:

            if not browser.is_connected():

                raise RuntimeError(
                    "Chromium disconnected."
                )

            if page.is_closed():

                raise RuntimeError(
                    "YouTube page closed."
                )

            try:

                print(
                    "Capturing live video...",
                    flush=True
                )

                frame = capture_video(
                    page
                )

                if frame is not None:

                    print(
                        "Running detector...",
                        flush=True
                    )

                    signal = detect_signal(
                        frame
                    )

                    process_signal(
                        signal
                    )

                else:

                    print(
                        "No usable video frame.",
                        flush=True
                    )

            except Exception as error:

                print(
                    "BROWSER ERROR:",
                    type(error).__name__,
                    str(error),
                    flush=True
                )

                # A crashed screenshot target should
                # restart the browser, not loop forever.
                raise

            time.sleep(
                CHECK_SECONDS
            )

    finally:

        print(
            "Closing browser session...",
            flush=True
        )

        if browser is not None:

            try:

                browser.close()

            except Exception:
                pass


# ============================================================
# MAIN MONITOR
# ============================================================

def monitor():

    print(
        "Million Moves monitor started.",
        flush=True
    )

    print(
        "YouTube URL:",
        YOUTUBE_URL,
        flush=True
    )

    with sync_playwright() as playwright:

        while True:

            try:

                run_browser_session(
                    playwright
                )

            except Exception as error:

                print(
                    "Browser session failed:",
                    type(error).__name__,
                    str(error),
                    flush=True
                )

            print(
                "Restarting browser in",
                RESTART_SECONDS,
                "seconds...",
                flush=True
            )

            time.sleep(
                RESTART_SECONDS
            )


# ============================================================
# DIRECT START
# ============================================================

if __name__ == "__main__":

    monitor()