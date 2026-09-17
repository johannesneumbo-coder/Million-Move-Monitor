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
    2,
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
    direction = str(
        signal.get("direction", "")
    ).strip().upper()

    if direction not in ("BUY", "SELL"):
        return None

    entry = signal.get("entry")

    if entry is None:
        return None

    try:
        entry = round(float(entry), 2)
    except (TypeError, ValueError):
        return None

    return f"{direction}|{entry:.2f}"


def format_signal(signal):
    direction = str(
        signal.get("direction", "")
    ).upper()

    lines = [
        "LIVE XAUUSD SIGNAL",
        f"Direction: {direction}",
        f"Entry: {signal.get('entry')}"
    ]

    for key, label in (
        ("sl", "SL"),
        ("tp1", "TP1"),
        ("tp2", "TP2"),
        ("tp3", "TP3")
    ):
        value = signal.get(key)

        if value is not None:
            lines.append(f"{label}: {value}")

    return "\n".join(lines)


def open_video(browser):
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
        page.locator(
            "button:has-text('Accept all')"
        ).first.click(timeout=2000)
    except Exception:
        pass

    video = page.locator("video").first

    video.wait_for(
        state="attached",
        timeout=45000
    )

    try:
        video.evaluate(
            """
            video => {
                video.muted = true;
                video.play().catch(() => {});
            }
            """
        )
    except Exception:
        pass

    log("VIDEO ELEMENT FOUND")

    return context, page, video


def capture_frame(video):
    video.screenshot(
        path=str(SCREENSHOT_FILE),
        timeout=20000
    )

    frame = cv2.imread(
        str(SCREENSHOT_FILE)
    )

    if frame is None:
        raise RuntimeError(
            "Screenshot could not be read"
        )

    log(
        f"FRAME CAPTURED: {frame.shape}"
    )

    return frame


def process_frame(frame):
    log("RUNNING SIGNAL DETECTOR")

    signal = detect_signal(frame)

    if not signal:
        log("NO SIGNAL DETECTED")
        return

    if not isinstance(signal, dict):
        log("INVALID DETECTOR RESULT")
        return

    key = make_signal_key(signal)

    if key is None:
        log("SIGNAL HAS NO VALID DIRECTION OR ENTRY")
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

                try:
                    context, page, video = open_video(
                        browser
                    )

                    log("MONITORING LIVE VIDEO")

                    while True:
                        if page.is_closed():
                            raise RuntimeError(
                                "YouTube page closed"
                            )

                        if video.count() == 0:
                            raise RuntimeError(
                                "Video element disappeared"
                            )

                        frame = capture_frame(video)

                        process_frame(frame)

                        time.sleep(CHECK_SECONDS)

                finally:
                    if context is not None:
                        try:
                            context.close()
                        except Exception:
                            pass

                    try:
                        browser.close()
                    except Exception:
                        pass

        except KeyboardInterrupt:
            log("MONITOR STOPPED")
            return

        except Exception as error:
            log(
                f"MONITOR ERROR: "
                f"{type(error).__name__}: {error}"
            )

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