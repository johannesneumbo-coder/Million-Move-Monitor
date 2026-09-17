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

MAX_PLAYBACK_ATTEMPTS = 3

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
# FORMAT PRICES
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

            const e = v.error;

            return {
                found: true,
                ready: v.readyState,
                network: v.networkState,
                width: v.videoWidth,
                height: v.videoHeight,
                paused: v.paused,
                currentTime: v.currentTime,
                error: e ? {
                    code: e.code,
                    message: e.message
                } : null
            };
        }"""
    )


# ============================================================
# REQUEST VIDEO PLAYBACK
# ============================================================

def request_playback(page):

    return page.evaluate(
        """async () => {
            const v = document.querySelector('video');

            if (!v) {
                return 'VIDEO_MISSING';
            }

            v.muted = true;
            v.autoplay = true;

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

            } catch (e) {
                return String(e);
            }
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

    page.goto(
        YOUTUBE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(5000)

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

    # Skip advertisements when possible
    try:

        page.locator(
            ".ytp-ad-skip-button, "
            ".ytp-skip-ad-button"
        ).first.click(timeout=2000)

    except Exception:
        pass

    print(
        "YouTube page loaded.",
        flush=True
    )


# ============================================================
# ENSURE VIDEO PLAYBACK
# ============================================================

def ensure_video_playing(page):

    for attempt in range(
        1,
        MAX_PLAYBACK_ATTEMPTS + 1
    ):

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

            page.wait_for_timeout(5000)
            continue

        if state.get("error"):

            print(
                "VIDEO ERROR:",
                state["error"],
                flush=True
            )

        # Request playback
        result = request_playback(page)

        print(
            "PLAY RESULT:",
            result,
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

        # Try clicking YouTube's play button
        try:

            page.locator(
                ".ytp-play-button"
            ).first.click(timeout=3000)

        except Exception:
            pass

        page.wait_for_timeout(3000)

    print(
        "VIDEO PLAYBACK FAILED.",
        flush=True
    )

    return False


# ============================================================
# CAPTURE VIDEO FRAME
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

        print(
            "VIDEO NOT READY FOR CAPTURE.",
            flush=True
        )

        return None

    video = page.locator("video").first

    screenshot = video.screenshot(
        type="jpeg",
        quality=85,
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
            "FRAME DECODE FAILED.",
            flush=True
        )

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

        print(
            "Invalid signal key.",
            flush=True
        )

        return

    if signal_already_sent(key):

        print(
            "Duplicate signal ignored:",
            key,
            flush=True
        )

        return

    message = format_message(signal)

    print(
        "Sending WhatsApp:",
        key,
        flush=True
    )

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

        # Log page errors for troubleshooting
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

                print(
                    "FAILED FRAMES:",
                    failed_frames,
                    flush=True
                )

                if failed_frames >= 3:

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