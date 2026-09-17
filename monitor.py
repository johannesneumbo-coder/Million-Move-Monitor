import os
import time
import re

import cv2
import numpy as np

from playwright.sync_api import sync_playwright

from detector import detect_signal
from storage import signal_already_sent, set_last_signal
from whatsapp import send_whatsapp


# ============================================================
# SETTINGS
# ============================================================

YOUTUBE_URL = os.getenv(
    "YOUTUBE_URL",
    "https://www.youtube.com/watch?v=-ps7V40GrA4"
)

CHECK_SECONDS = max(
    5,
    int(os.getenv("CHECK_SECONDS", "5"))
)

BLOCKED_RETRY_SECONDS = 300
ERROR_RETRY_SECONDS = 60

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720


# ============================================================
# SIGNAL KEY
# ============================================================

def make_signal_key(signal):

    direction = str(
        signal.get("direction", "")
    ).upper()

    if direction not in ("BUY", "SELL"):
        return None

    try:
        entry = float(signal["entry"])
    except (KeyError, TypeError, ValueError):
        return None

    return f"{direction}|{entry:.2f}"


# ============================================================
# PRICE FORMAT
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

    emoji = "🟢" if direction == "BUY" else "🔴"

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
# CHECK YOUTUBE ACCESS
# ============================================================

def youtube_block_reason(page):

    try:

        body = page.locator("body").inner_text(
            timeout=5000
        ).lower()

    except Exception:

        return None

    indicators = [
        "sign in to confirm",
        "not a bot",
        "unusual traffic",
        "our systems have detected unusual traffic",
        "captcha"
    ]

    for indicator in indicators:

        if indicator in body:

            return indicator

    return None


# ============================================================
# VIDEO STATE
# ============================================================

def get_video_state(page):

    return page.evaluate(
        """() => {

            const v = document.querySelector('video');

            if (!v) {
                return {
                    found: false,
                    ready: 0,
                    width: 0,
                    height: 0,
                    paused: true
                };
            }

            return {
                found: true,
                ready: v.readyState,
                width: v.videoWidth,
                height: v.videoHeight,
                paused: v.paused,
                currentTime: v.currentTime,
                error: v.error ? v.error.message : null
            };

        }"""
    )


# ============================================================
# OPEN VIDEO
# ============================================================

def open_youtube(page):

    print(
        "OPENING YOUTUBE:",
        YOUTUBE_URL,
        flush=True
    )

    page.goto(
        YOUTUBE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(5000)

    print(
        "PAGE TITLE:",
        page.title(),
        flush=True
    )

    reason = youtube_block_reason(page)

    if reason:

        print(
            "YOUTUBE ACCESS BLOCKED:",
            reason,
            flush=True
        )

        return False

    print(
        "YOUTUBE PAGE OPENED.",
        flush=True
    )

    return True


# ============================================================
# START PLAYBACK
# ============================================================

def start_video(page):

    for attempt in range(1, 4):

        reason = youtube_block_reason(page)

        if reason:

            print(
                "YOUTUBE ACCESS BLOCKED:",
                reason,
                flush=True
            )

            return False

        state = get_video_state(page)

        print(
            "PLAYBACK ATTEMPT:",
            attempt,
            "STATE:",
            state,
            flush=True
        )

        if not state["found"]:

            page.wait_for_timeout(5000)
            continue

        if (
            state["ready"] >= 2
            and state["width"] > 0
            and state["height"] > 0
            and not state["paused"]
        ):

            print(
                "VIDEO PLAYBACK READY.",
                flush=True
            )

            return True

        try:

            result = page.evaluate(
                """async () => {

                    const video =
                        document.querySelector('video');

                    if (!video) {
                        return 'VIDEO_MISSING';
                    }

                    video.muted = true;

                    try {

                        await Promise.race([
                            video.play(),

                            new Promise((_, reject) =>
                                setTimeout(
                                    () => reject(
                                        new Error('PLAY_TIMEOUT')
                                    ),
                                    8000
                                )
                            )
                        ]);

                        return 'PLAY_REQUEST_SUCCEEDED';

                    } catch (error) {

                        return String(error);

                    }

                }"""
            )

            print(
                "PLAY RESULT:",
                result,
                flush=True
            )

        except Exception as error:

            print(
                "PLAY ERROR:",
                str(error),
                flush=True
            )

        page.wait_for_timeout(5000)

        state = get_video_state(page)

        if (
            state["found"]
            and state["ready"] >= 2
            and state["width"] > 0
            and state["height"] > 0
            and not state["paused"]
        ):

            print(
                "VIDEO PLAYBACK READY.",
                flush=True
            )

            return True

    print(
        "VIDEO PLAYBACK FAILED.",
        flush=True
    )

    return False


# ============================================================
# CAPTURE VIDEO
# ============================================================

def capture_video(page):

    state = get_video_state(page)

    if not state["found"]:
        return None

    if (
        state["ready"] < 2
        or state["width"] <= 0
        or state["height"] <= 0
        or state["paused"]
    ):

        return None

    screenshot = page.locator(
        "video"
    ).first.screenshot(
        type="jpeg",
        quality=85,
        timeout=15000
    )

    image_array = np.frombuffer(
        screenshot,
        dtype=np.uint8
    )

    frame = cv2.imdecode(
        image_array,
        cv2.IMREAD_COLOR
    )

    if frame is not None:

        print(
            "FRAME CAPTURED:",
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

    key = make_signal_key(signal)

    if key is None:
        return

    if signal_already_sent(key):

        print(
            "Duplicate ignored:",
            key,
            flush=True
        )

        return

    message = format_message(signal)

    sent = send_whatsapp(message)

    if sent:

        set_last_signal(key)

        print(
            "WHATSAPP SENT:",
            key,
            flush=True
        )

    else:

        print(
            "WHATSAPP FAILED.",
            flush=True
        )


# ============================================================
# BROWSER SESSION
# ============================================================

def run_browser_session(playwright):

    browser = None

    try:

        print(
            "LAUNCHING CHROMIUM...",
            flush=True
        )

        browser = playwright.chromium.launch(
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
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT
            },
            device_scale_factor=1
        )

        page = context.new_page()

        page.set_default_timeout(15000)

        if not open_youtube(page):

            return BLOCKED_RETRY_SECONDS

        if not start_video(page):

            if youtube_block_reason(page):

                return BLOCKED_RETRY_SECONDS

            return ERROR_RETRY_SECONDS

        print(
            "LIVE MONITOR ACTIVE.",
            flush=True
        )

        failed_frames = 0

        while True:

            if not browser.is_connected():

                print(
                    "BROWSER DISCONNECTED.",
                    flush=True
                )

                return ERROR_RETRY_SECONDS

            if page.is_closed():

                print(
                    "BROWSER PAGE CLOSED.",
                    flush=True
                )

                return ERROR_RETRY_SECONDS

            reason = youtube_block_reason(page)

            if reason:

                print(
                    "YOUTUBE ACCESS LOST:",
                    reason,
                    flush=True
                )

                return BLOCKED_RETRY_SECONDS

            frame = capture_video(page)

            if frame is None:

                failed_frames += 1

                print(
                    "FRAME UNAVAILABLE:",
                    failed_frames,
                    flush=True
                )

                if failed_frames >= 3:

                    print(
                        "VIDEO STOPPED. RESTARTING SESSION.",
                        flush=True
                    )

                    return ERROR_RETRY_SECONDS

                time.sleep(CHECK_SECONDS)

                continue

            failed_frames = 0

            signal = detect_signal(frame)

            process_signal(signal)

            time.sleep(CHECK_SECONDS)

    finally:

        print(
            "CLOSING CHROMIUM...",
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
        "MILLION MOVES MONITOR STARTED.",
        flush=True
    )

    with sync_playwright() as playwright:

        while True:

            retry_seconds = ERROR_RETRY_SECONDS

            try:

                retry_seconds = run_browser_session(
                    playwright
                )

            except Exception as error:

                print(
                    "MONITOR ERROR:",
                    type(error).__name__,
                    str(error),
                    flush=True
                )

            print(
                "RETRYING IN",
                retry_seconds,
                "SECONDS...",
                flush=True
            )

            time.sleep(retry_seconds)


# ============================================================
# DIRECT START
# ============================================================

if __name__ == "__main__":

    monitor()
