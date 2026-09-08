import cv2
import numpy as np
import pytesseract
import re


def crop_chart(frame):
    height, width = frame.shape[:2]

    # Ignore most of the TradingView interface.
    # Keep the central chart area.
    x1 = int(width * 0.05)
    x2 = int(width * 0.95)
    y1 = int(height * 0.08)
    y2 = int(height * 0.92)

    return frame[y1:y2, x1:x2]


def ocr_text(frame):
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        gray = cv2.resize(
            gray,
            None,
            fx=2,
            fy=2,
            interpolation=cv2.INTER_CUBIC
        )

        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        _, threshold = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        text = pytesseract.image_to_string(
            threshold,
            config="--psm 11"
        )

        return text.upper()

    except Exception as e:
        print("OCR error:", e)
        return ""


def detect_direction(text):
    buy = re.search(r"\bBUY\b", text)
    sell = re.search(r"\bSELL\b", text)

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

            # XAUUSD price range filter.
            if 1000 <= number <= 10000:
                values.append(number)

        except ValueError:
            pass

    return values


def detect_signal(frame):
    chart = crop_chart(frame)

    text = ocr_text(chart)

    direction = detect_direction(text)

    if not direction:
        return None

    prices = extract_prices(text)

    entry = prices[0] if len(prices) >= 1 else None
    sl = prices[1] if len(prices) >= 2 else None
    tp = prices[2] if len(prices) >= 3 else None

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "ocr_text": text
    }