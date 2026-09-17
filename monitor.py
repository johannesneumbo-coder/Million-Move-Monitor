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
    direction = signal.get("direction", "")
    entry = signal.get("entry")
    sl = signal.get("sl")
    tp1 = signal.get("tp1")
    tp2 = signal.get("tp2")
    tp3 = signal.get("tp3")

    lines = [
        f"XAUUSD {direction}",
        f"Entry: {entry}",
    ]

    if sl is not None:
        lines.append(f"SL: {sl}")

    if tp1 is not None:
        lines.append(f"TP1: {tp1}")

    if tp2 is not None:
        lines.append(f"TP2: {tp2}")

    if tp3 is not None:
        lines.append(f"TP3: {tp3}")

    return "\n".join(lines)


def process_signal(signal):
    if not signal:
        print("No signal detected", flush=True)
        return

    key = make_signal_key(signal)

    if key is None:
        print("Signal missing valid direction or entry", flush=True)
        return

    if signal_already_sent(key):
        print("Signal already sent:", key, flush=True)
        return

    message = format_message(signal)

    if send_whatsapp(message):
        set_last_signal(key)
        print("New signal saved:", key, flush=True)
    else:
        print("WhatsApp failed; signal not marked as sent", flush=True)


def capture_frame(page):
    video = page.locator("video").first

    if video.count() == 0:
        print("Video element not found", flush=True)
        return None

    try:
        video.scroll_into_view_if_needed(timeout=5000)

        SCREENSHOT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        video.screenshot(
            path=str(SCREENSHOT_FILE),
            timeout=15000
        )

        frame = cv2.imread(str(SCREENSHOT_FILE))

        if frame is None:
            print("Screenshot could not be read", flush=True)
            return None

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
                print("LAUNCHING CHROMIUM", flush=True)

                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ]
                )

                try:
                    page = browser.new_page(
                        viewport={
                            "width": 1280,
                            "height": 900,
                        }
                    )

                    print("OPENING YOUTUBE", flush=True)

                    page.goto(
                        YOUTUBE_URL,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    page.wait_for_timeout(8000)

                    try:
                        page.locator("video").first.evaluate(
                            "(video) => video.play()"
                        )
                    except Exception as exc:
                        print(
                            "Video play attempt:",
                            exc,
                            flush=True
                        )

                    while True:
                        print("Taking screenshot...", flush=True)

                        frame = capture_frame(page)

                        if frame is not None:
                            print(
                                "Running signal detector...",
                                flush=True
                            )

                            try:
                                signal = detect_signal(frame)
                                process_signal(signal)
                            except Exception as exc:
                                print(
                                    "Signal detector error:",
                                    exc,
                                    flush=True
                                )

                        time.sleep(CHECK_SECONDS)

                finally:
                    browser.close()
                    print("BROWSER SESSION CLOSED", flush=True)

        except Exception as exc:
            print("Monitor error:", exc, flush=True)
            print("Restarting browser in 10 seconds", flush=True)
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