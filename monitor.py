import os
import time
import re
from pathlib import Path

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

RESTART_SECONDS = 15

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720

DIAGNOSTIC_FILE = Path(
    "/tmp/youtube_diagnostic.jpg"
)


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

        entry = round(
            float(entry),
            2
        )

    except (TypeError, ValueError):
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
# PAGE DIAGNOSTICS
# ============================================================

def diagnose_page(page):

    print(
        "========== YOUTUBE DIAGNOSTICS ==========",
        flush=True
    )

    try:

        print(
            "PAGE URL:",
            page.url,
            flush=True
        )

        print(
            "PAGE TITLE:",
            page.title(),
            flush=True
        )

        body = page.locator("body").inner_text(
            timeout=10000
        )

        body = re.sub(
            r"\s+",
            " ",
            body
        )

        # Only print a short excerpt.
        # Avoid exposing cookies or full page HTML.
        print(
            "PAGE TEXT:",
            body[:1500],
            flush=True
        )

        lower = body.lower()

        indicators = [
            "sign in to confirm",
            "not a bot",
            "unusual traffic",
            "verify",
            "captcha",
            "video unavailable",
            "this video is unavailable",
            "playback error",
            "confirm you're not a bot"
        ]

        matches = [
            item
            for item in indicators
            if item in lower
        ]

        print(
            "CHALLENGE INDICATORS:",
            matches,
            flush=True
        )

        print(
            "VIDEO ELEMENT COUNT:",
            page.locator("video").count(),
            flush=True
        )

        print(
            "IFRAME COUNT:",
            page.locator("iframe").count(),
            flush=True
        )

        try:

            page.screenshot(
                path=str(DIAGNOSTIC_FILE),
                type="jpeg",
                quality=65,
                timeout=10000,
                animations="disabled"
            )

            print(
                "DIAGNOSTIC SCREENSHOT:",
                str(DIAGNOSTIC_FILE),
                flush=True
            )

        except Exception as error:

            print(
                "DIAGNOSTIC SCREENSHOT ERROR:",
                type(error).__name__,
                str(error),
                flush=True
            )

    except Exception as error:

        print(
            "DIAGNOSTIC ERROR:",
            type(error).__name__,
            str(error),
            flush=True
        )

    print(
        "========== END DIAGNOSTICS ==========",
        flush=True
    )


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
                    error: 'Video element missing'
                };

            }

            return {

                found: true,
                ready: v.readyState,
                network: v.networkState,
                width: v.videoWidth,
                height: v.videoHeight,
                paused: v.paused,
                currentTime: v.currentTime,

                error: v.error ? {
                    code: v.error.code,
                    message: v.error.message
                } : null

            };

        }"""
    )


# ============================================================
# OPEN YOUTUBE
# ============================================================

def open_youtube(page):

    print(
        "Opening YouTube:",
        YOUTUBE_URL,
        flush=True
    )

    response = page.goto(
        YOUTUBE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    if response is not None:

        print(
            "HTTP STATUS:",
            response.status,
            flush=True
        )

    page.wait_for_timeout(8000)

    diagnose_page(page)

    # Cookie consent
    for name in [
        "Accept all",
        "I agree"
    ]:

        try:

            page.get_by_role(
                "button",
                name=name,
                exact=True
            ).click(timeout=2000)

            break

        except Exception:
            pass

    page.wait_for_timeout(3000)


# ============================================================
# PLAY VIDEO
# ============================================================

def ensure_video_playing(page):

    for attempt in range(1, 4):

        print(
            "PLAYBACK ATTEMPT:",
            attempt,
            flush=True
        )

        state = get_video_state(page)

        print(
            "VIDEO STATE:",
            state,
            flush=True
        )

        if not state.get("found"):

            diagnose_page(page)

            page.wait_for_timeout(5000)

            continue

        try:

            result = page.evaluate(
                """async () => {

                    const v = document.querySelector('video');

                    v.muted = true;

                    try {

                        await Promise.race([
                            v.play(),
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

        print(
            "VIDEO STATE AFTER PLAY:",
            state,
            flush=True
        )

        if (
            state.get("ready", 0) >= 2
            and state.get("width", 0) > 0
            and state.get("height", 0) > 0
            and not state.get("paused", True)
        ):

            print(
                "VIDEO PLAYBACK READY.",
                flush=True
            )

            return True

    diagnose_page(page)

    print(
        "VIDEO PLAYBACK FAILED.",
        flush=True
    )

    return False


# ============================================================
# CAPTURE FRAME
# ============================================================

def capture_video(page):

    state = get_video_state(page)

    print(
        "CAPTURE STATE:",
        state,
        flush=True
    )

    if not state.get("found"):
        return None

    if (
        state.get("ready", 0) < 2
        or state.get("width", 0) == 0
        or state.get("height", 0) == 0
        or state.get("paused", True)
    ):

        return None

    screenshot = page.locator(
        "video"
    ).first.screenshot(
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
        return None

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

    print(
        "SIGNAL DETECTED:",
        signal,
        flush=True
    )

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
            "Launching Chromium...",
            flush=True
        )

        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
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

        page.on(
            "pageerror",
            lambda error: print(
                "PAGE ERROR:",
                str(error),
                flush=True
            )
        )

        page.on(
            "crash",
            lambda _: print(
                "CHROMIUM PAGE CRASHED.",
                flush=True
            )
        )

        open_youtube(page)

        if not ensure_video_playing(page):

            raise RuntimeError(
                "YouTube video failed to start."
            )

        print(
            "LIVE MONITOR ACTIVE.",
            flush=True
        )

        failed_frames = 0

        while True:

            if not browser.is_connected():

                raise RuntimeError(
                    "Browser disconnected."
                )

            if page.is_closed():

                raise RuntimeError(
                    "Browser page closed."
                )

            frame = capture_video(page)

            if frame is None:

                failed_frames += 1

                if failed_frames >= 3:

                    diagnose_page(page)

                    raise RuntimeError(
                        "Video stopped producing frames."
                    )

                time.sleep(CHECK_SECONDS)

                continue

            failed_frames = 0

            signal = detect_signal(frame)

            process_signal(signal)

            time.sleep(CHECK_SECONDS)

    finally:

        print(
            "Closing Chromium...",
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

    with sync_playwright() as playwright:

        while True:

            try:

                run_browser_session(
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
                "Restarting browser in",
                RESTART_SECONDS,
                "seconds...",
                flush=True
            )

            time.sleep(RESTART_SECONDS)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    monitor()