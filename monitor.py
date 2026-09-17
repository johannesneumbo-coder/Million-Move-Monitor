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


def log(*args):
    print(*args, flush=True)


def make_signal_key(signal):
    direction = str(
        signal.get("direction", "")
    ).upper()

    if direction not in ("BUY", "SELL"):
        return None

    try:
        entry = float(signal["entry"])
    except (KeyError, ValueError, TypeError):
        return None

    return f"{direction}|{entry:.2f}"


def format_message(signal):
    lines = [
        "MILLION MOVES XAUUSD",
        f"Signal: {signal['direction']}",
        f"Entry: {signal['entry']}"
    ]

    for name in ("sl", "tp1", "tp2", "tp3"):
        value = signal.get(name)

        if value is not None:
            lines.append(
                f"{name.upper()}: {value}"
            )

    return "\n".join(lines)


def check_youtube(page):
    try:
        text = page.locator("body").inner_text(
            timeout=3000
        ).lower()

        if (
            "sign in to confirm" in text
            or "unusual traffic" in text
            or "not a bot" in text
        ):
            log(
                "YOUTUBE ACCESS BLOCKED: "
                "Sign-in verification required"
            )
            return False

    except Exception:
        pass

    return True


def get_video_state(page):
    try:
        return page.evaluate(
            """() => {
                const v = document.querySelector('video');

                if (!v) {
                    return null;
                }

                return {
                    ready: v.readyState,
                    width: v.videoWidth,
                    height: v.videoHeight,
                    paused: v.paused,
                    currentTime: v.currentTime
                };
            }"""
        )

    except Exception as error:
        log("VIDEO STATE ERROR:", error)
        return None


def open_youtube(page):
    log("OPENING YOUTUBE")

    try:
        page.goto(
            YOUTUBE_URL,
            wait_until="domcontentloaded",
            timeout=45000
        )

    except Exception as error:
        log(
            "PAGE LOAD ERROR:",
            str(error)[:250]
        )

    deadline = time.monotonic() + 45

    while time.monotonic() < deadline:

        if not check_youtube(page):
            return False

        state = get_video_state(page)

        if state is None:
            log("WAITING FOR VIDEO ELEMENT")

            time.sleep(3)
            continue

        try:
            page.evaluate(
                """() => {
                    const v = document.querySelector('video');

                    if (v && v.paused) {
                        v.play().catch(() => {});
                    }
                }"""
            )

        except Exception as error:
            log(
                "PLAY ATTEMPT ERROR:",
                str(error)[:150]
            )

        state = get_video_state(page)

        if state is not None:

            if (
                state["ready"] >= 2
                and state["width"] > 0
                and state["height"] > 0
                and not state["paused"]
            ):
                log(
                    "VIDEO READY:",
                    state
                )

                return True

        time.sleep(3)

    log(
        "VIDEO DID NOT BECOME PLAYABLE"
    )

    return False


def capture_frame(page):
    try:
        video = page.locator("video").first

        if video.count() == 0:
            log("VIDEO ELEMENT MISSING")
            return None

        state = get_video_state(page)

        if (
            state is None
            or state["ready"] < 2
            or state["width"] == 0
            or state["height"] == 0
        ):
            log(
                "VIDEO FRAME NOT READY:",
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

        image = np.frombuffer(
            screenshot,
            dtype=np.uint8
        )

        frame = cv2.imdecode(
            image,
            cv2.IMREAD_COLOR
        )

        if frame is None:
            log("FRAME DECODE FAILED")
            return None

        log(
            "FRAME CAPTURED:",
            frame.shape
        )

        return frame

    except Exception as error:
        log(
            "CAPTURE ERROR:",
            str(error)[:250]
        )

        return None


def process_frame(frame):
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
        log("INVALID SIGNAL")
        return

    if signal_already_sent(key):
        log(
            "DUPLICATE SIGNAL SKIPPED:",
            key
        )

        return

    message = format_message(signal)

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
            "WHATSAPP SIGNAL SENT:",
            key
        )

    else:
        log(
            "WHATSAPP SEND FAILED"
        )


def monitor_loop():
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
                            "height": 900
                        }
                    )

                    video_ready = open_youtube(page)

                    if video_ready:

                        missing_frames = 0

                        while True:

                            if not check_youtube(page):
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
                                        "VIDEO LOST. "
                                        "RESTARTING BROWSER."
                                    )

                                    break

                            else:

                                missing_frames = 0

                                process_frame(frame)

                            time.sleep(
                                CHECK_SECONDS
                            )

                    else:
                        log(
                            "VIDEO UNAVAILABLE. "
                            "SESSION WILL RESTART."
                        )

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

        time.sleep(
            RETRY_SECONDS
        )


def run_monitor():
    monitor_loop()


def start_monitor():
    monitor_loop()


def monitor():
    monitor_loop()


def run():
    monitor_loop()


if __name__ == "__main__":
    monitor_loop()