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

CHECK_SECONDS = max(
    3,
    int(os.getenv("CHECK_SECONDS", "5"))
)

RETRY_SECONDS = 60

SCREENSHOT_FILE = Path(
    os.getenv(
        "SCREENSHOT_FILE",
        "/tmp/million_moves.png"
    )
)


def log(*items):
    print(*items, flush=True)


def make_signal_key(signal):
    direction = str(
        signal.get("direction", "")
    ).upper()

    try:
        entry = round(
            float(signal["entry"]),
            2
        )
    except (KeyError, TypeError, ValueError):
        return None

    if direction not in ("BUY", "SELL"):
        return None

    return f"{direction}|{entry:.2f}"


def format_message(signal):
    def price(value):
        if value is None:
            return "Not detected"

        return f"{float(value):.2f}"

    return (
        "MILLION MOVES XAUUSD\n"
        f"Signal: {signal['direction']}\n"
        f"Entry: {price(signal['entry'])}\n"
        f"SL: {price(signal.get('sl'))}\n"
        f"TP1: {price(signal['tp1'])}\n"
        f"TP2: {price(signal['tp2'])}\n"
        f"TP3: {price(signal['tp3'])}"
    )


def youtube_block_reason(page):
    try:
        text = page.locator("body").inner_text(
            timeout=5000
        ).lower()
    except Exception:
        return None

    indicators = (
        "sign in to confirm you're not a bot",
        "sign in to confirm you’re not a bot",
        "unusual traffic",
        "this helps protect our community",
        "verify it's you",
        "verify it’s you"
    )

    for indicator in indicators:
        if indicator in text:
            return indicator

    return None


def video_state(page):
    try:
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
                    paused: video.paused
                };
            }"""
        )
    except Exception as error:
        log("VIDEO STATE ERROR:", error)
        return None


def open_video(page):
    log("OPENING YOUTUBE")

    try:
        page.goto(
            YOUTUBE_URL,
            wait_until="domcontentloaded",
            timeout=30000
        )
    except Exception as error:
        log(
            "YOUTUBE PAGE LOAD ISSUE:",
            str(error)[:300]
        )

    deadline = time.monotonic() + 45

    while time.monotonic() < deadline:
        reason = youtube_block_reason(page)

        if reason:
            log(
                "YOUTUBE ACCESS BLOCKED:",
                reason
            )
            return False

        state = video_state(page)

        if state and state["found"]:
            try:
                page.evaluate(
                    """() => {
                        const video =
                            document.querySelector('video');

                        if (video && video.paused) {
                            video.play().catch(() => {});
                        }
                    }"""
                )
            except Exception:
                pass

            state = video_state(page)

            if (
                state
                and state["ready"] >= 2
                and state["width"] > 0
                and state["height"] > 0
                and not state["paused"]
            ):
                log(
                    "VIDEO PLAYING:",
                    state
                )
                return True

        time.sleep(3)

    log(
        "VIDEO NOT PLAYABLE AFTER 45 SECONDS."
    )

    return False


def capture_frame(page):
    try:
        video = page.locator("video").first

        if video.count() == 0:
            log("VIDEO ELEMENT MISSING")
            return None

        state = video_state(page)

        if not state:
            return None

        if (
            not state["found"]
            or state["ready"] < 2
            or state["width"] == 0
            or state["height"] == 0
            or state["paused"]
        ):
            log(
                "VIDEO NOT READY:",
                state
            )
            return None

        screenshot = video.screenshot(
            timeout=10000
        )

        SCREENSHOT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        SCREENSHOT_FILE.write_bytes(
            screenshot
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
            log("SCREENSHOT DECODE FAILED")
            return None

        log(
            "FRAME CAPTURED:",
            frame.shape
        )

        return frame

    except Exception as error:
        log(
            "SCREENSHOT ERROR:",
            str(error)[:300]
        )
        return None


def process_signal(frame):
    try:
        signal = detect_signal(frame)
    except Exception as error:
        log(
            "DETECTOR ERROR:",
            error
        )
        return

    if not signal:
        log("No signal detected")
        return

    key = make_signal_key(signal)

    if key is None:
        log("INVALID SIGNAL KEY")
        return

    if signal_already_sent(key):
        log(
            "DUPLICATE SIGNAL SKIPPED:",
            key
        )
        return

    message = format_message(signal)

    log(
        "SENDING WHATSAPP:",
        key
    )

    try:
        sent = send_whatsapp(message)
    except Exception as error:
        log(
            "WHATSAPP ERROR:",
            error
        )
        return

    if sent:
        set_last_signal(key)
        log(
            "SIGNAL SAVED:",
            key
        )
    else:
        log(
            "WHATSAPP SEND FAILED:",
            key
        )


def monitor():
    log(
        "MILLION MOVES MONITOR STARTED"
    )

    while True:
        try:
            with sync_playwright() as playwright:
                browser = None

                try:
                    log("LAUNCHING CHROMIUM")

                    browser = playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage"
                        ]
                    )

                    page = browser.new_page(
                        viewport={
                            "width": 1280,
                            "height": 720
                        },
                        device_scale_factor=1
                    )

                    if not open_video(page):
                        log(
                            "CLOSING UNAVAILABLE VIDEO SESSION"
                        )
                        continue

                    missing_frames = 0

                    while True:
                        reason = youtube_block_reason(page)

                        if reason:
                            log(
                                "YOUTUBE ACCESS BLOCKED:",
                                reason
                            )
                            break

                        frame = capture_frame(page)

                        if frame is None:
                            missing_frames += 1

                            log(
                                "MISSING FRAME:",
                                missing_frames
                            )

                            if missing_frames >= 3:
                                log(
                                    "VIDEO LOST. RESTARTING SESSION."
                                )
                                break

                        else:
                            missing_frames = 0
                            process_signal(frame)

                        time.sleep(CHECK_SECONDS)

                finally:
                    if browser is not None:
                        try:
                            browser.close()
                        except Exception:
                            pass

                    log(
                        "BROWSER SESSION CLOSED"
                    )

        except Exception as error:
            log(
                "MONITOR ERROR:",
                error
            )

        log(
            "RETRYING IN",
            RETRY_SECONDS,
            "SECONDS"
        )

        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    monitor()