import cv2
import numpy as np
import pytesseract
import re


# ============================================================
# MILLION MOVES V5 - XAUUSD SIGNAL DETECTOR
#
# Yellow = Entry
# Red = Stop Loss
# Green = Take Profit
#
# Returns:
# {
#     "direction": "BUY",
#     "entry": 4300.00,
#     "sl": 4290.00,
#     "tp1": 4310.00,
#     "tp2": 4320.00,
#     "tp3": 4330.00
# }
#
# Returns None when a complete signal cannot be confirmed.
# ============================================================


# ============================================================
# PRICE EXTRACTION
# ============================================================

def extract_prices(text):

    if not text:
        return []

    text = text.replace(" ", "")

    patterns = re.findall(
        r"\d{1,2},\d{3}\.\d{1,3}|\d{4,5}\.\d{1,3}",
        text
    )

    values = []

    for value in patterns:

        try:

            number = float(
                value.replace(",", "")
            )

            if 1000 <= number <= 10000:
                values.append(number)

        except ValueError:
            continue

    return values


# ============================================================
# SAFE CROP
# ============================================================

def safe_crop(frame, x1, y1, x2, y2):

    if frame is None:
        return None

    height, width = frame.shape[:2]

    x1 = max(0, int(x1))
    y1 = max(0, int(y1))

    x2 = min(width, int(x2))
    y2 = min(height, int(y2))

    if x2 <= x1 or y2 <= y1:
        return None

    return frame[y1:y2, x1:x2]


# ============================================================
# OCR
# ============================================================

def run_ocr(image, psm=7):

    if image is None or image.size == 0:
        return ""

    try:

        if len(image.shape) == 3:

            gray = cv2.cvtColor(
                image,
                cv2.COLOR_BGR2GRAY
            )

        else:
            gray = image.copy()

        gray = cv2.resize(
            gray,
            None,
            fx=4,
            fy=4,
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
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        results = []

        for processed in [
            gray,
            threshold,
            cv2.bitwise_not(threshold)
        ]:

            text = pytesseract.image_to_string(
                processed,
                config=(
                    f"--psm {psm} "
                    "-c tessedit_char_whitelist="
                    "0123456789.,ABCDEFGHIJKLMNOPQRSTUVWXYZ:/ "
                )
            )

            if text:
                results.append(text.upper().strip())

        return " | ".join(results)

    except Exception as error:

        print(
            "OCR ERROR:",
            str(error),
            flush=True
        )

        return ""


# ============================================================
# COLOR MASK
# ============================================================

def create_color_mask(frame, color):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    if color == "yellow":

        mask = cv2.inRange(
            hsv,
            np.array([8, 70, 70]),
            np.array([45, 255, 255])
        )

    elif color == "red":

        red1 = cv2.inRange(
            hsv,
            np.array([0, 80, 60]),
            np.array([12, 255, 255])
        )

        red2 = cv2.inRange(
            hsv,
            np.array([160, 80, 60]),
            np.array([180, 255, 255])
        )

        mask = cv2.bitwise_or(
            red1,
            red2
        )

    elif color == "green":

        mask = cv2.inRange(
            hsv,
            np.array([45, 50, 50]),
            np.array([105, 255, 255])
        )

    else:
        return None

    kernel = np.ones(
        (3, 3),
        np.uint8
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=1
    )

    return mask


# ============================================================
# FIND COLORED PRICE LABELS
# ============================================================

def find_color_labels(frame, color):

    height, width = frame.shape[:2]

    # Focus on the right-hand TradingView labels.
    x1 = int(width * 0.65)
    x2 = int(width * 0.985)

    y1 = int(height * 0.10)
    y2 = int(height * 0.96)

    roi = safe_crop(
        frame,
        x1,
        y1,
        x2,
        y2
    )

    if roi is None:
        return []

    mask = create_color_mask(
        roi,
        color
    )

    if mask is None:
        return []

    contours, _ = cv2.findContours(
        mask,
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

        if w < 20 or h < 7:
            continue

        if w > roi.shape[1] * 0.95:
            continue

        if h > 90:
            continue

        real_x = x + x1
        real_y = y + y1

        # Exclude labels entirely inside the far-right
        # TradingView price scale.
        if real_x > width * 0.96:
            continue

        crop = safe_crop(
            frame,
            real_x - 35,
            real_y - 15,
            real_x + w + 35,
            real_y + h + 15
        )

        text = run_ocr(
            crop,
            psm=7
        )

        prices = extract_prices(text)

        if not prices:
            continue

        # Avoid treating multiple OCR variants as
        # multiple separate price labels.
        unique_prices = list(dict.fromkeys(prices))

        if len(unique_prices) != 1:
            continue

        results.append(
            {
                "price": unique_prices[0],
                "text": text,
                "x": real_x,
                "y": real_y,
                "w": w,
                "h": h,
                "area": area
            }
        )

    # Remove duplicate detections of the same label.
    unique = []

    for item in sorted(
        results,
        key=lambda value: -value["area"]
    ):

        duplicate = False

        for existing in unique:

            same_price = (
                abs(
                    item["price"] -
                    existing["price"]
                ) < 0.01
            )

            same_position = (
                abs(
                    item["y"] -
                    existing["y"]
                ) < 20
            )

            if same_price and same_position:
                duplicate = True
                break

        if not duplicate:
            unique.append(item)

    return unique


# ============================================================
# ENTRY DETECTION
# ============================================================

def find_yellow_entry(frame):

    labels = find_color_labels(
        frame,
        "yellow"
    )

    if not labels:

        print(
            "ENTRY NOT DETECTED",
            flush=True
        )

        return None

    # Require an explicit entry label to avoid
    # selecting unrelated yellow chart elements.
    candidates = [
        item
        for item in labels
        if "ENTRY" in item["text"]
    ]

    if not candidates:

        print(
            "YELLOW LABEL FOUND BUT ENTRY NOT CONFIRMED",
            flush=True
        )

        return None

    candidates.sort(
        key=lambda item: -item["area"]
    )

    selected = candidates[0]

    print(
        "ENTRY:",
        selected["price"],
        flush=True
    )

    return {
        **selected,
        "entry": selected["price"]
    }


# ============================================================
# STOP LOSS DETECTION
# ============================================================

def find_red_stop_loss(frame):

    labels = find_color_labels(
        frame,
        "red"
    )

    candidates = [
        item
        for item in labels
        if (
            "SL" in item["text"]
            or "S/L" in item["text"]
            or "STOP" in item["text"]
            or "LOSS" in item["text"]
        )
    ]

    if not candidates:

        print(
            "STOP LOSS NOT DETECTED",
            flush=True
        )

        return None

    candidates.sort(
        key=lambda item: -item["area"]
    )

    selected = candidates[0]

    print(
        "STOP LOSS:",
        selected["price"],
        flush=True
    )

    return {
        **selected,
        "sl": selected["price"]
    }


# ============================================================
# TAKE PROFIT DETECTION
# ============================================================

def find_green_targets(frame, entry):

    labels = find_color_labels(
        frame,
        "green"
    )

    targets = []

    for item in labels:

        price = item["price"]

        if abs(price - entry) < 0.01:
            continue

        # Require a TP label rather than any green price.
        if not re.search(
            r"\bT/?P\s*[123]?\b|TAKE\s*PROFIT",
            item["text"]
        ):
            continue

        targets.append(item)

    return targets


# ============================================================
# DIRECTION
# ============================================================

def determine_direction(entry, sl, targets):

    if sl < entry:

        direction = "BUY"

        valid = [
            item
            for item in targets
            if item["price"] > entry
        ]

        valid.sort(
            key=lambda item: item["price"]
        )

    elif sl > entry:

        direction = "SELL"

        valid = [
            item
            for item in targets
            if item["price"] < entry
        ]

        valid.sort(
            key=lambda item: -item["price"]
        )

    else:

        return None, []

    return direction, valid


# ============================================================
# MAIN DETECTOR
# ============================================================

def detect_signal(frame):

    print(
        "RUNNING MILLION MOVES DETECTOR",
        flush=True
    )

    if frame is None:

        print(
            "EMPTY FRAME",
            flush=True
        )

        return None

    if not isinstance(frame, np.ndarray):

        print(
            "INVALID FRAME",
            flush=True
        )

        return None

    if frame.size == 0:
        return None

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    entry_data = find_yellow_entry(frame)

    if entry_data is None:
        return None

    entry = entry_data["entry"]

    # --------------------------------------------------------
    # STOP LOSS
    # --------------------------------------------------------

    sl_data = find_red_stop_loss(frame)

    if sl_data is None:
        return None

    sl = sl_data["sl"]

    # --------------------------------------------------------
    # TARGETS
    # --------------------------------------------------------

    targets = find_green_targets(
        frame,
        entry
    )

    if not targets:

        print(
            "NO TARGETS DETECTED",
            flush=True
        )

        return None

    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------

    direction, valid_targets = determine_direction(
        entry,
        sl,
        targets
    )

    if direction is None:

        print(
            "DIRECTION NOT CONFIRMED",
            flush=True
        )

        return None

    # --------------------------------------------------------
    # REMOVE DUPLICATE TARGET PRICES
    # --------------------------------------------------------

    unique_targets = []

    for item in valid_targets:

        price = item["price"]

        if all(
            abs(price - existing) >= 0.01
            for existing in unique_targets
        ):

            unique_targets.append(price)

    # Require all three targets.
    if len(unique_targets) < 3:

        print(
            "INCOMPLETE TARGETS:",
            unique_targets,
            flush=True
        )

        return None

    tp1 = unique_targets[0]
    tp2 = unique_targets[1]
    tp3 = unique_targets[2]

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    if direction == "BUY":

        valid = (
            sl < entry < tp1 < tp2 < tp3
        )

    else:

        valid = (
            tp3 < tp2 < tp1 < entry < sl
        )

    if not valid:

        print(
            "INVALID SIGNAL PRICE ORDER",
            flush=True
        )

        return None

    # --------------------------------------------------------
    # FINAL SIGNAL
    # --------------------------------------------------------

    signal = {
        "direction": direction,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "tp3": round(tp3, 2)
    }

    print(
        "SIGNAL DETECTED:",
        signal,
        flush=True
    )

    return signal


# ============================================================
# END OF DETECTOR
# ============================================================