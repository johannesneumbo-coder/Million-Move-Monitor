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

CHECK_SECONDS = max(
    3,
    int(os.getenv("CHECK_SECONDS", "5"))
)

SCREENSHOT_FILE = Path(
    os.getenv(
        "SCREENSHOT_FILE",
        "/tmp/million_moves.png"
    )
)

SCREENSHOT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


def log(message):
    print(message, flush=True)


def make_signal_key(signal):
    if not isinstance(signal, dict):
        return None

    direction = str(
        signal.get("direction", "")
    ).strip().upper()

    if direction not in ("BUY", "SELL"):
        return None

    try:
        entry = float(signal["entry"])
    except (KeyError, TypeError, ValueError):
        return None

    return f"{direction}|{entry:.2f}"


def format_signal(signal):
    lines = [
        "LIVE XAUUSD SIGNAL",
        f"Direction: {signal['direction']}",
        f"Entry: {float(signal['entry']):.2f}"
    ]

    for key, label in (
        ("sl", "SL"),
        ("tp1", "TP1"),
        ("tp2", "TP2"),
        ("tp3", "TP3")
    ):
        value = signal.get(key)

        if value is not None:
            lines.append(
                f"{label}: {float(value):.2f}"
            )

    return "\n".join(lines)


def open_youtube(browser):
    context = browser.new_context(
        viewport={
            "width": 1920,
            "height": 1080
        },
        device_scale_factor=1
    )

    page = context.new_page()

    log("OPENING YOUTUBE")

    page.goto(
        YOUTUBE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(8000)

    try:
        page.get_by_role(
            "button",
            name="Accept all"
        ).click(timeout=2000)
    except Exception:
        pass

    log("YOUTUBE PAGE LOADED")

    return context, page


def prepare_video(page):
    video = page.locator("video").first

    if video.count() == 0:
        log("VIDEO ELEMENT NOT FOUND")
        return None

    try:
        video.evaluate(
            """
            video => {
                video.muted = true;
                video.play().catch(() => {});
            }
            """
        )

        log("VIDEO PLAY REQUESTED")

    except Exception as error:
        log(
            "VIDEO PLAY ERROR: "
            f"{type(error).__name__}: {error}"
        )

    return video


def capture_frame(page):
    if page.is_closed():
        raise RuntimeError(
            "YouTube page closed"
        )

    video = prepare_video(page)

    if video is None:
        raise RuntimeError(
            "Video element unavailable"
        )

    state = video.evaluate(
        """
        video => ({
            readyState: video.readyState,
            width: video.videoWidth,
            height: video.videoHeight,
            currentTime: video.currentTime,
            paused: video.paused
        })
        """
    )

    log(f"VIDEO STATE: {state}")

    if (
        state["readyState"] < 2
        or state["width"] <= 0
        or state["height"] <= 0
    ):
        raise RuntimeError(
            "Video has not produced a frame"
        )

    log("TAKING PAGE SCREENSHOT")

    page.screenshot(
        path=str(SCREENSHOT_FILE),
        full_page=False,
        timeout=30000
    )

    frame = cv2.imread(
        str(SCREENSHOT_FILE)
    )

    if frame is None:
        raise RuntimeError(
            "Screenshot could not be read"
        )

    player = page.locator(
        "#movie_player"
    ).first

    bounds = player.bounding_box(
        timeout=5000
    )

    if bounds is None:
        raise RuntimeError(
            "Video player position unavailable"
        )

    height, width = frame.shape[:2]

    x1 = max(0, int(bounds["x"]))
    y1 = max(0, int(bounds["y"]))

    x2 = min(
        width,
        int(bounds["x"] + bounds["width"])
    )

    y2 = min(
        height,
        int(bounds["y"] + bounds["height"])
    )

    if x2 - x1 < 300 or y2 - y1 < 200:
        raise RuntimeError(
            "Video player crop too small"
        )

    frame = frame[y1:y2, x1:x2]

    if frame.size == 0:
        raise RuntimeError(
            "Empty player frame"
        )

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    if gray.std() < 3:
        raise RuntimeError(
            "Blank player frame"
        )

    log(
        f"FRAME CAPTURED: {frame.shape}"
    )

    return frame


def process_frame(frame):
    log("RUNNING SIGNAL DETECTOR")

    signal = detect_signal(frame)

    if not signal:
        log("NO COMPLETE SIGNAL DETECTED")
        return

    key = make_signal_key(signal)

    if key is None:
        log("INVALID SIGNAL")
        return

    log(f"SIGNAL DETECTED: {key}")

    if signal_already_sent(key):
        log("DUPLICATE SIGNAL - NOT SENDING")
        return

    message = format_signal(signal)

    log("SENDING WHATSAPP MESSAGE")

    result = send_whatsapp(message)

    if result is False:
        log("WHATSAPP SEND FAILED")
        return

    set_last_signal(key)

    log("SIGNAL SENT AND SAVED")


def monitor_loop():
    log("MONITOR STARTED")

    while True:
        context = None
        browser = None

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--autoplay-policy=no-user-gesture-required"
                    ]
                )

                context, page = open_youtube(
                    browser
                )

                log("MONITORING LIVE VIDEO")

                failures = 0

                while True:
                    try:
                        frame = capture_frame(
                            page
                        )

                        failures = 0

                        process_frame(frame)

                    except Exception as error:
                        failures += 1

                        log(
                            f"CAPTURE ERROR {failures}: "
                            f"{type(error).__name__}: "
                            f"{error}"
                        )

                    if failures >= 6:
                        raise RuntimeError(
                            "Restarting browser after "
                            "six consecutive failures"
                        )

                    time.sleep(
                        CHECK_SECONDS
                    )

        except KeyboardInterrupt:
            log("MONITOR STOPPED")
            return

        except Exception as error:
            log(
                f"SESSION ERROR: "
                f"{type(error).__name__}: "
                f"{error}"
            )

        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass

            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

        log("RECONNECTING IN 30 SECONDS")
        time.sleep(30)


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