import os
import time

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

CHECK_SECONDS = max(5, int(os.getenv("CHECK_SECONDS", "5")))
RETRY_SECONDS = 300

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720


def make_signal_key(signal):
    direction = str(signal.get("direction", "")).upper()

    if direction not in ("BUY", "SELL"):
        return None

    try:
        entry = float(signal["entry"])
    except (KeyError, TypeError, ValueError):
        return None

    return f"{direction}|{entry:.2f}"


def price_text(value):
    if value is None:
        return "Not confirmed"

    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "Not confirmed"


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
        f"TP3: {price_text(signal.get('tp3'))}"
    )


def youtube_block_reason(page):
    try:
        body = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        return None

    if "sign in to confirm" in body and "not a bot" in body:
        return "YouTube requires sign-in verification"

    if "unusual traffic" in body:
        return "YouTube detected unusual traffic"

    return None


def video_state(page):
    return page.evaluate(
        """() => {
            const video = document.querySelector('video');

            if (!video) {
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
                ready: video.readyState,
                width: video.videoWidth,
                height: video.videoHeight,
                paused: video.paused,
                currentTime: video.currentTime
            };
        }"""
    )


def start_video(page):
    print("OPENING YOUTUBE:", YOUTUBE_URL, flush=True)

    page.goto(
        YOUTUBE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(5000)

    reason = youtube_block_reason(page)

    if reason:
        print("YOUTUBE ACCESS BLOCKED:", reason, flush=True)
        return False

    for attempt in range(1, 5):
        state = video_state(page)

        print(
            "VIDEO STATE:",
            state,
            flush=True
        )

        if state["found"]:
            try:
                page.evaluate(
                    """() => {
                        const video = document.querySelector('video');
                        video.muted = true;
                        video.play().catch(() => {});
                    }"""
                )
            except Exception as error:
                print("PLAY REQUEST ERROR:", error, flush=True)

        page.wait_for_timeout(5000)

        state = video_state(page)

        if (
            state["found"]
            and state["ready"] >= 2
            and state["width"] > 0
            and state["height"] > 0
            and not state["paused"]
        ):
            print("VIDEO PLAYBACK READY.", flush=True)
            return True

        reason = youtube_block_reason(page)

        if reason:
            print("YOUTUBE ACCESS BLOCKED:", reason, flush=True)
            return False

    print("VIDEO PLAYBACK NOT READY.", flush=True)
    return False


def capture_frame(page):
    state = video_state(page)

    if not (
        state["found"]
        and state["ready"] >= 2
        and state["width"] > 0
        and state["height"] > 0
        and not state["paused"]
    ):
        return None

    screenshot = page.locator("video").first.screenshot(
        type="jpeg",
        quality=90,
        timeout=15000
    )

    frame = cv2.imdecode(
        np.frombuffer(screenshot, dtype=np.uint8),
        cv2.IMREAD_COLOR
    )

    if frame is not None:
        print("FRAME CAPTURED:", frame.shape, flush=True)

    return frame


def process_signal(signal):
    if not signal:
        print("No signal detected.", flush=True)
        return

    key = make_signal_key(signal)

    if key is None:
        return

    if signal_already_sent(key):
        print("DUPLICATE IGNORED:", key, flush=True)
        return

    print("SIGNAL DETECTED:", signal, flush=True)

    if send_whatsapp(format_message(signal)):
        set_last_signal(key)
        print("WHATSAPP SENT:", key, flush=True)
    else:
        print("WHATSAPP FAILED.", flush=True)


def run_session(playwright):
    browser = None

    try:
        print("LAUNCHING CHROMIUM...", flush=True)

        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
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

        if not start_video(page):
            return

        print("LIVE MONITOR ACTIVE.", flush=True)

        failed_frames = 0

        while browser.is_connected() and not page.is_closed():
            try:
                frame = capture_frame(page)

                if frame is None:
                    failed_frames += 1

                    print(
                        "FRAME NOT READY:",
                        failed_frames,
                        flush=True
                    )

                    if failed_frames >= 6:
                        print(
                            "VIDEO STOPPED. REOPENING SESSION.",
                            flush=True
                        )
                        return

                    time.sleep(CHECK_SECONDS)
                    continue

                failed_frames = 0

                signal = detect_signal(frame)
                process_signal(signal)

            except Exception as error:
                print(
                    "MONITOR LOOP ERROR:",
                    type(error).__name__,
                    str(error),
                    flush=True
                )

                failed_frames += 1

                if failed_frames >= 6:
                    return

            time.sleep(CHECK_SECONDS)

    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

        print("BROWSER SESSION CLOSED.", flush=True)


def monitor():
    print("MILLION MOVES MONITOR STARTED.", flush=True)

    with sync_playwright() as playwright:
        while True:
            try:
                run_session(playwright)

            except Exception as error:
                print(
                    "MONITOR ERROR:",
                    type(error).__name__,
                    str(error),
                    flush=True
                )

            print(
                f"RETRYING IN {RETRY_SECONDS} SECONDS...",
                flush=True
            )

            time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    monitor()