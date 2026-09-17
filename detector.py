import cv2
import numpy as np
import pytesseract
import re


# =========================================================
# PRICE EXTRACTION
# =========================================================

def extract_prices(text):

    if not text:
        return []

    values = []

    patterns = re.findall(
        r"\d{1,2}[,]?\d{3}[.]\d{1,3}|\d{4,5}[.]\d{1,3}",
        text
    )

    for value in patterns:

        try:

            number = float(
                value.replace(",", "")
            )

            if 1000 <= number <= 10000:
                values.append(number)

        except Exception:
            pass

    return values


# =========================================================
# OCR
# =========================================================

def run_ocr(image, psm=6):

    try:

        if image is None or image.size == 0:
            return ""

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.resize(
            gray,
            None,
            fx=5,
            fy=5,
            interpolation=cv2.INTER_CUBIC
        )

        # Improve small text
        gray = cv2.GaussianBlur(
            gray,
            (3, 3),
            0
        )

        _, threshold = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY
            + cv2.THRESH_OTSU
        )

        texts = []

        for img in [gray, threshold]:

            try:

                text = pytesseract.image_to_string(
                    img,
                    config=f"--psm {psm}"
                )

                if text:
                    texts.append(
                        text.upper().strip()
                    )

            except Exception:
                pass

        return " ".join(texts)

    except Exception as e:

        print(
            "OCR error:",
            type(e).__name__,
            str(e),
            flush=True
        )

        return ""


# =========================================================
# SAFE CROP
# =========================================================

def safe_crop(
    frame,
    x1,
    y1,
    x2,
    y2
):

    height, width = frame.shape[:2]

    x1 = max(0, int(x1))
    y1 = max(0, int(y1))
    x2 = min(width, int(x2))
    y2 = min(height, int(y2))

    if x2 <= x1 or y2 <= y1:
        return None

    return frame[
        y1:y2,
        x1:x2
    ]


# =========================================================
# RIGHT-SIDE TRADING PANEL
# =========================================================

def get_trading_panel(frame):

    height, width = frame.shape[:2]

    # Million Moves labels are on the right side.
    # Keep a large area because the labels can move.
    x1 = int(width * 0.73)
    x2 = int(width * 0.985)

    y1 = int(height * 0.25)
    y2 = int(height * 0.96)

    return safe_crop(
        frame,
        x1,
        y1,
        x2,
        y2
    ), x1, y1


# =========================================================
# OCR THE WHOLE RIGHT PANEL
# =========================================================

def read_right_panel(frame):

    panel, px, py = get_trading_panel(
        frame
    )

    if panel is None:
        return ""

    texts = []

    for psm in [6, 11, 12]:

        text = run_ocr(
            panel,
            psm=psm
        )

        if text:
            texts.append(text)

    result = " | ".join(texts)

    print(
        "RIGHT PANEL OCR:",
        result,
        flush=True
    )

    return result


# =========================================================
# FIND YELLOW / ORANGE ENTRY BOX
# =========================================================

def find_yellow_entry(frame):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    height, width = frame.shape[:2]

    # Entry box is on right side.
    roi_x1 = int(width * 0.72)
    roi_x2 = int(width * 0.98)

    roi = hsv[
        :,
        roi_x1:roi_x2
    ]

    # Million Moves yellow/orange entry labels
    # can vary in hue, so use a broad range.
    mask1 = cv2.inRange(
        roi,
        np.array([8, 70, 70]),
        np.array([45, 255, 255])
    )

    # Morphology joins broken letters/background.
    kernel = np.ones(
        (3, 3),
        np.uint8
    )

    mask1 = cv2.morphologyEx(
        mask1,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=2
    )

    contours, _ = cv2.findContours(
        mask1,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        area = cv2.contourArea(
            contour
        )

        if area < 100:
            continue

        if w < 30 or w > 260:
            continue

        if h < 8 or h > 80:
            continue

        real_x = x + roi_x1

        # Ignore the far-right price scale.
        if real_x > width * 0.96:
            continue

        candidates.append(
            (
                real_x,
                y,
                w,
                h,
                area
            )
        )

    if not candidates:
        return None

    # Try every candidate rather than only the largest one.
    results = []

    for x, y, w, h, area in candidates:

        crop = safe_crop(
            frame,
            x - 25,
            y - 15,
            x + w + 25,
            y + h + 15
        )

        text = run_ocr(
            crop,
            psm=7
        )

        prices = extract_prices(
            text
        )

        if prices:

            for price in prices:

                results.append(
                    {
                        "entry": price,
                        "text": text,
                        "x": x,
                        "y": y,
                        "w": w,
                        "h": h,
                        "area": area
                    }
                )

    if not results:
        return None

    # Prefer OCR containing ENTRY.
    entry_words = [
        item
        for item in results
        if "ENTRY" in item["text"]
    ]

    if entry_words:
        results = entry_words

    # Prefer price closest to the normal XAUUSD range
    # and the largest label.
    results.sort(
        key=lambda item: (
            -item["area"],
            abs(item["entry"] - 4300)
        )
    )

    selected = results[0]

    print(
        "ENTRY DETECTED:",
        selected["entry"],
        "| OCR:",
        selected["text"],
        flush=True
    )

    return selected


# =========================================================
# FIND RED STOP LOSS
# =========================================================

def find_red_stop_loss(frame):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    height, width = frame.shape[:2]

    roi_x1 = int(width * 0.72)
    roi_x2 = int(width * 0.98)

    roi = hsv[
        :,
        roi_x1:roi_x2
    ]

    red1 = cv2.inRange(
        roi,
        np.array([0, 80, 60]),
        np.array([12, 255, 255])
    )

    red2 = cv2.inRange(
        roi,
        np.array([160, 80, 60]),
        np.array([180, 255, 255])
    )

    mask = cv2.bitwise_or(
        red1,
        red2
    )

    kernel = np.ones(
        (3, 3),
        np.uint8
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=2
    )

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        area = cv2.contourArea(
            contour
        )

        if area < 80:
            continue

        if w < 25 or w > 280:
            continue

        if h < 8 or h > 90:
            continue

        real_x = x + roi_x1

        if real_x > width * 0.96:
            continue

        candidates.append(
            (
                real_x,
                y,
                w,
                h,
                area
            )
        )

    results = []

    for x, y, w, h, area in candidates:

        crop = safe_crop(
            frame,
            x - 30,
            y - 18,
            x + w + 30,
            y + h + 18
        )

        for psm in [6, 7, 11]:

            text = run_ocr(
                crop,
                psm=psm
            )

            prices = extract_prices(
                text
            )

            for price in prices:

                results.append(
                    {
                        "sl": price,
                        "text": text,
                        "x": x,
                        "y": y,
                        "w": w,
                        "h": h,
                        "area": area
                    }
                )

    if not results:
        return None

    stop_words = [
        item
        for item in results
        if "STOP" in item["text"]
        or "LOSS" in item["text"]
    ]

    if stop_words:
        results = stop_words

    results.sort(
        key=lambda item: -item["area"]
    )

    selected = results[0]

    print(
        "STOP LOSS DETECTED:",
        selected["sl"],
        "| OCR:",
        selected["text"],
        flush=True
    )

    return selected


# =========================================================
# GREEN TP LABELS
# =========================================================

def find_green_targets(
    frame,
    entry
):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    height, width = frame.shape[:2]

    roi_x1 = int(width * 0.72)
    roi_x2 = int(width * 0.98)

    roi = hsv[
        :,
        roi_x1:roi_x2
    ]

    # Green/cyan Million Moves labels.
    mask1 = cv2.inRange(
        roi,
        np.array([45, 50, 50]),
        np.array([105, 255, 255])
    )

    kernel = np.ones(
        (3, 3),
        np.uint8
    )

    mask1 = cv2.morphologyEx(
        mask1,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=2
    )

    contours, _ = cv2.findContours(
        mask1,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    results = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        area = cv2.contourArea(
            contour
        )

        if area < 60:
            continue

        if w < 25 or w > 280:
            continue

        if h < 7 or h > 80:
            continue

        real_x = x + roi_x1

        if real_x > width * 0.96:
            continue

        crop = safe_crop(
            frame,
            real_x - 30,
            y - 18,
            real_x + w + 30