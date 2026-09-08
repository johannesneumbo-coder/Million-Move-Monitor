import cv2
import numpy as np
import pytesseract
import re


def crop_chart(frame):

    height, width = frame.shape[:2]

    x1 = int(width * 0.05)
    x2 = int(width * 0.95)
    y1 = int(height * 0.08)
    y2 = int(height * 0.92)

    return frame[y1:y2, x1:x2]


def get_color_masks(frame):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

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


def color_pixels(mask):

    return cv2.countNonZero(mask)


def ocr_text(frame):

    try:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.resize(
            gray,
            None,
            fx=1.5,
            fy=1.5,
            interpolation=cv2.INTER_AREA
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

    if re.search(
        r"\bBUY\b",
        text
    ):

        return "BUY"

    if re.search(
        r"\bSELL\b",
        text
    ):

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

    yellow_count = color_pixels(
        yellow
    )

    red_count = color_pixels(
        red
    )

    green_count = color_pixels(
        green
    )

    # Do not run OCR unless a possible
    # yellow ENTRY area exists.
    if yellow_count < 80:

        return None

    print(
        "Possible yellow ENTRY detected.",
        flush=True
    )

    text = ocr_text(
        chart
    )

    direction = detect_direction(
        text
    )

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

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "yellow_found": True,
        "red_found": red_count >= 80,
        "green_found": green_count >= 80,
        "ocr_text": text
    }