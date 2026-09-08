import cv2
import numpy as np
import pytesseract
import re


def crop_chart(frame):
    height, width = frame.shape[:2]

    x1 = int(width * 0.03)
    x2 = int(width * 0.97)
    y1 = int(height * 0.05)
    y2 = int(height * 0.95)

    return frame[y1:y2, x1:x2]


def get_color_masks(frame):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    # YELLOW ENTRY
    yellow_lower = np.array(
        [18, 80, 80]
    )

    yellow_upper = np.array(
        [40, 255, 255]
    )

    yellow = cv2.inRange(
        hsv,
        yellow_lower,
        yellow_upper
    )

    # RED S/L
    red_lower_1 = np.array(
        [0, 80, 80]
    )

    red_upper_1 = np.array(
        [10, 255, 255]
    )

    red_lower_2 = np.array(
        [170, 80, 80]
    )

    red_upper_2 = np.array(
        [180, 255, 255]
    )

    red1 = cv2.inRange(
        hsv,
        red_lower_1,
        red_upper_1
    )

    red2 = cv2.inRange(
        hsv,
        red_lower_2,
        red_upper_2
    )

    red = cv2.bitwise_or(
        red1,
        red2
    )

    # GREEN T/P
    green_lower = np.array(
        [35, 60, 50]
    )

    green_upper = np.array(
        [95, 255, 255]
    )

    green = cv2.inRange(
        hsv,
        green_lower,
        green_upper
    )

    return yellow, red, green


def mask_has_signal(mask):

    pixels = cv2.countNonZero(
        mask
    )

    return pixels > 80


def ocr_text(frame):

    try:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.resize(
            gray,
            None,
            fx=2,
            fy=2,
            interpolation=cv2.INTER_CUBIC
        )

        gray = cv2.GaussianBlur(
            gray,
            (3, 3),
            0
        )

        _, threshold = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY +
            cv2.THRESH_OTSU
        )

        text = pytesseract.image_to_string(
            threshold,
            config="--psm 11"
        )

        return text.upper()

    except Exception as e:

        print(
            "OCR error:",
            type(e).__name__,
            str(e),
            flush=True
        )

        return ""


def detect_direction(text):

    buy = re.search(
        r"\bBUY\b",
        text
    )

    sell = re.search(
        r"\bSELL\b",
        text
    )

    if buy and not sell:
        return "BUY"

    if sell and not buy:
        return "SELL"

    return None


def extract_prices(text):

    values = []

    matches = re.findall(
        r"\b\d{3,5}(?:\.\d{1,3})?\b",
        text
    )

    for value in matches:

        try:

            number = float(value)

            if 1000 <= number <= 10000:

                values.append(
                    number
                )

        except ValueError:

            pass

    return values


def detect_signal(frame):

    chart = crop_chart(
        frame
    )

    yellow, red, green = (
        get_color_masks(chart)
    )

    yellow_found = mask_has_signal(
        yellow
    )

    red_found = mask_has_signal(
        red
    )

    green_found = mask_has_signal(
        green
    )

    text = ocr_text(
        chart
    )

    direction = detect_direction(
        text
    )

    # We need the yellow ENTRY area
    # before considering it a signal.
    if not yellow_found:

        return None

    # If OCR gives the direction,
    # use it.
    if direction is None:

        # Try to determine direction
        # from nearby OCR text.
        if "BUY" in text:

            direction = "BUY"

        elif "SELL" in text:

            direction = "SELL"

    if direction is None:

        return None

    prices = extract_prices(
        text
    )

    entry = (
        prices[0]
        if len(prices) >= 1
        else None
    )

    sl = (
        prices[1]
        if len(prices) >= 2
        else None
    )

    tp = (
        prices[2]
        if len(prices) >= 3
        else None
    )

    # Require at least one supporting
    # SL/TP colour when available.
    if not red_found and not green_found:

        return None

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "yellow_found": yellow_found,
        "red_found": red_found,
        "green_found": green_found,
        "ocr_text": text
    }