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
    return (
        "LIVE XAUUSD SIGNAL\n"
        f"Direction: {signal['direction']}\n"
        f"Entry: {signal['entry']:.2f}\n"
        f"SL: {signal['sl']:.2f}\n"
        f"TP1: {signal['tp1']:.2f}\n"
        f"TP2: {signal['tp2']:.2f}\n"
        f"TP3: {signal['tp3']:.2f}"
    )


def check_blocked(page):
    try:
        text = page.locator("body").inner_text(
            timeout=3000
        ).lower()

        blocked_messages = (
            "sign in to confirm you're not a bot",
            "sign in to confirm you’re not a bot",
            "unusual traffic",
            "verify that you're not a bot",
            "verify that you’re not a bot"
        )

        if any(
            message in text
            for message in blocked_messages
        ):
            raise RuntimeError(
                "YouTube sign-in verification required"
            )

    except RuntimeError:
        raise

    except Exception:
        pass


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

    check_blocked(page)

    try:
        page.get_by_role(
            "button",
            name="Accept all"
        ).click(timeout=2000)
    except Exception:
        pass

    try:
        video = page.locator("video").first

        video.wait_for(
            state="attached",
            timeout=20000
        )

        video.evaluate(
            """
            video => {
                video.muted = true;
                video.play().catch(() => {});
            }
            """
        )

        log("VIDEO ELEMENT FOUND")

    except Exception as error:
        log(
            "VIDEO ELEMENT NOT READY: "
            f"{type(error).__name__}: {error}"
        )

    return context, page


def capture_frame(page):
    if page.is_closed():
        raise RuntimeError(
            "YouTube page closed"
        )

    check_blocked(page)

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

    # Prefer the player region when its position is available.
    # Otherwise the detector receives the entire page.
    try:
        player = page.locator(
            "#movie_player"
        ).first

        bounds = player.bounding_box(
            timeout=2000
        )

        if bounds:
            height, width = frame.shape[:2]

            x1 = max(
                0,
                int(bounds["x"])
            )

            y1 = max(
                0,
                int(bounds["y"])
            )

            x2 = min(
                width,
                int(
                    bounds["x"] +
                    bounds["width"]
                )
            )

            y2 = min(
                height,
                int(
                    bounds["y"] +
                    bounds["height"]
                )
            )

            if (
                x2 - x1 >= 300
                and y2 - y1 >= 200
            ):
                frame = frame[
                    y1:y2,
                    x1:x2
                ]

                log("PLAYER REGION CROPPED")

    except Exception:
        log(
            "PLAYER CROP UNAVAILABLE; "
            "USING PAGE SCREENSHOT"
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
        log("INVALID SIGNAL KEY")
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

    # Only record the signal after the send function
    # returns without an explicit failure.
    set_last_signal(key)

    log("SIGNAL SENT AND SAVED")


def monitor_loop():
    log("MONITOR STARTED")

    while True:
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

                context = None

                try:
                    context, page = open_youtube(
                        browser
                    )

                    log("MONITORING STARTED")

                    consecutive_errors = 0

                    while True:
                        try:
                            frame = capture_frame(
                                page
                            )

                            process_frame(
                                frame
                            )

                            consecutive_errors = 0

                        except RuntimeError as error:
                            if (
                                "sign-in verification"
                                in str(error).lower()
                            ):
                                raise

                            consecutive_errors += 1

                            log(
                                f"CAPTURE ERROR "
                                f"{consecutive_errors}: "
                                f"{error}"
                            )

                        except Exception as error:
                            consecutive_errors += 1

                            log(
                                "PROCESSING ERROR: "
                                f"{type(error).__name__}: "
                                f"{error}"
                            )

                        if consecutive_errors >= 3:
                            raise RuntimeError(
                                "Three consecutive failures"
                            )

                        time.sleep(
                            CHECK_SECONDS
                        )

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
                "MONITOR ERROR: "
                f"{type(error).__name__}: "
                f"{error}"
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