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

CHECK_SECONDS = int(os.getenv("CHECK_SECONDS", "5"))

SCREENSHOT_FILE = Path(
    os.getenv("SCREENSHOT_FILE", "/tmp/million_moves.png")
)


def make_signal_key(signal):
    direction = str(signal.get("direction", "")).upper()
    entry = signal.get("entry")

    if direction not in ("BUY", "SELL") or entry is None:
        return None

    try:
        entry = round(float(entry), 2)
    except (TypeError, ValueError):
        return None

    return f"{direction}|{entry:.2f}"


def format_message(signal):
    lines = [
        f"XAUUSD {signal.get('direction')}",
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


def process_signal(signal):
    if not signal:
        print("No signal detected", flush=True)
        return

    key = make_signal_key(signal)

    if key is None:
        print("Invalid signal", flush=True)
        return

    if signal_already_sent(key):
        print("Signal already sent:", key, flush=True)
        return

    if send_whatsapp(format_message(signal)):
        set_last_signal(key)
        print("Signal sent:", key, flush=True)
    else:
        print("WhatsApp send failed", flush=True)


def wait_for_video(page):
    try:
        page.locator("video").first.wait_for(
            state="attached",
            timeout=30000
        )

        page.locator("video").first.evaluate(
            """video => {
                video.muted = true;
                video.play().catch(() => {});
            }"""
        )

        return True

    except Exception as exc:
        print("Video not available:", exc, flush=True)
        return False


def capture_frame(page):
    video = page.locator("video").first

    if video.count() == 0:
        return None

    try:
        SCREENSHOT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        video.screenshot(
            path=str(SCREENSHOT_FILE),
            timeout=15000
        )

        frame = cv2.imread(str(SCREENSHOT_FILE))

        if frame is not None:
            print("FRAME CAPTURED:", frame.shape, flush=True)

        return frame

    except Exception as exc:
        print("Screenshot error:", exc, flush=True)
        return None


def monitor_loop():
    print("MILLION MOVES MONITOR STARTED", flush=True)

    while True:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage"
                    ]
                )

                try:
                    page = browser.new_page(
                        viewport={
                            "width": 1280,
                            "height": 900
                        }
                    )

                    print("OPENING YOUTUBE", flush=True)

                    page.goto(
                        YOUTUBE_URL,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    while True:
                        if not wait_for_video(page):
                            print(
                                "Video missing. Reloading page...",
                                flush=True
                            )

                            page.reload(
                                wait_until="domcontentloaded",
                                timeout=60000
                            )

                            time.sleep(10)
                            continue

                        frame = capture_frame(page)

                        if frame is None:
                            print(
                                "Frame missing. Reloading page...",
                                flush=True
                            )

                            page.reload(
                                wait_until="domcontentloaded",
                                timeout=60000
                            )

                            time.sleep(10)
                            continue

                        try:
                            signal = detect_signal(frame)
                            process_signal(signal)

                        except Exception as exc:
                            print(
                                "Detector error:",
                                exc,
                                flush=True
                            )

                        time.sleep(CHECK_SECONDS)

                finally:
                    browser.close()

        except Exception as exc:
            print("Monitor error:", exc, flush=True)
            time.sleep(10)


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