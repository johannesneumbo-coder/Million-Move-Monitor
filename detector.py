import re

import cv2
import numpy as np
import pytesseract


# ============================================================
# MILLION MOVES V5 DETECTOR
#
# Yellow = Entry
# Green  = Targets
# Red    = Stop Loss (optional)
#
# Reads labels from the right side of the video.
# Does not use historical BUY/SELL markers.
# ============================================================


# ============================================================
# PRICE EXTRACTION
# ============================================================

def extract_prices(text):

    if not text:
        return []

    text = text.upper()

    # Repair common OCR substitutions only inside numeric
    # candidates, not across the entire text.
    candidates = re.findall(
        r"(?<![A-Z0-9])"
        r"[0-9OILSB,.\s]{4,20}"
        r"(?![A-Z0-9])",
        text
    )

    prices = []

    for candidate in candidates:

        candidate = candidate.replace(" ", "")

        candidate = candidate.replace("O", "0")
        candidate = candidate.replace("I", "1")
        candidate = candidate.replace("L", "1")
        candidate = candidate.replace("S", "5")
        candidate = candidate.replace("B", "8")

        candidate = candidate.replace(",", "")

        matches = re.findall(
            r"(?<!\d)\d{4,5}\.\d{1,3}(?!\d)",
            candidate
        )

        for match in matches:

            try:

                price = float(match)

                if 1000 <= price <= 10000:

                    if all(
                        abs(price - existing) >= 0.001
                        for existing in prices
                    ):

                        prices.append(price)

            except ValueError:
                pass

    return prices


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

def ocr_variants(image):

    if image is None or image.size == 0:
        return []

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    ) if len(image.shape) == 3 else image.copy()

    gray = cv2.resize(
        gray,
        None,
        fx=5,
        fy=5,
        interpolation=cv2.INTER_CUBIC
    )

    gray = cv2.GaussianBlur(
        gray,
        (3, 3),
        0
    )

    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    images = [
        gray,
        binary,
        cv2.bitwise_not(binary)
    ]

    results = []

    for processed in images:

        for psm in (7, 6, 11):

            try:

                text = pytesseract.image_to_string(
                    processed,
                    config=(
                        f"--psm {psm} "
                        "-c preserve_interword_spaces=1"
                    )
                )

                text = text.upper().strip()

                if text and text not in results:
                    results.append(text)

            except Exception as error:

                print(
                    "OCR ERROR:",
                    str(error),
                    flush=True
                )

    return results


# ============================================================
# COLOUR MASK
# ============================================================

def create_color_mask(frame, color):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    if color == "yellow":

        # Include yellow and yellow-orange.
        mask = cv2.inRange(
            hsv,
            np.array([8, 55, 65]),
            np.array([48, 255, 255])
        )

    elif color == "green":

        mask = cv2.inRange(
            hsv,
            np.array([35, 40, 40]),
            np.array([105, 255, 255])
        )

    elif color == "red":

        mask1 = cv2.inRange(
            hsv,
            np.array([0, 55, 50]),
            np.array([15, 255, 255])
        )

        mask2 = cv2.inRange(
            hsv,
            np.array([160, 55, 50]),
            np.array([180, 255, 255])
        )

        mask = cv2.bitwise_or(
            mask1,
            mask2
        )

    else:

        return None

    kernel = np.ones(
        (3, 3),
        dtype=np.uint8
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=2
    )

    return mask


# ============================================================
# FIND COLOURED LABEL RECTANGLES
# ============================================================

def find_color_labels(frame, color):

    height, width = frame.shape[:2]

    # The actual video frame is 880 x 495.
    # Search the entire right-hand 45%.
    x_offset = int(width * 0.55)

    roi = safe_crop(
        frame,
        x_offset,
        0,
        width,
        height
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

    labels = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        area = w * h

        # Allow small labels at 880 x 495 resolution.
        if area < 35:
            continue

        if w < 9 or h < 4:
            continue

        if h > height * 0.20:
            continue

        real_x = x + x_offset

        labels.append(
            {
                "x": real_x,
                "y": y,
                "w": w,
                "h": h,
                "area": area
            }
        )

    labels.sort(
        key=lambda item: (
            item["y"],
            item["x"]
        )
    )

    # Merge nearby fragments belonging to one label.
    merged = []

    for item in labels:

        matched = False

        for existing in merged:

            same_line = abs(
                (item["y"] + item["h"] / 2) -
                (existing["y"] + existing["h"] / 2)
            ) <= max(
                8,
                existing["h"]
            )

            horizontal_gap = (
                item["x"] -
                (existing["x"] + existing["w"])
            )

            close = -10 <= horizontal_gap <= 35

            if same_line and close:

                x1 = min(
                    existing["x"],
                    item["x"]
                )

                y1 = min(
                    existing["y"],
                    item["y"]
                )

                x2 = max(
                    existing["x"] + existing["w"],
                    item["x"] + item["w"]
                )

                y2 = max(
                    existing["y"] + existing["h"],
                    item["y"] + item["h"]
                )

                existing.update(
                    {
                        "x": x1,
                        "y": y1,
                        "w": x2 - x1,
                        "h": y2 - y1,
                        "area": (
                            (x2 - x1) *
                            (y2 - y1)
                        )
                    }
                )

                matched = True
                break

        if not matched:

            merged.append(item.copy())

    results = []

    for label in merged:

        # Include surrounding text without searching
        # the historical markers in the chart centre.
        crop = safe_crop(
            frame,
            label["x"] - 65,
            label["y"] - 12,
            label["x"] + label["w"] + 30,
            label["y"] + label["h"] + 12
        )

        texts = ocr_variants(crop)

        price_candidates = []

        for text in texts:

            for price in extract_prices(text):

                if price not in price_candidates:
                    price_candidates.append(price)

        # A price is confirmed only if the crop gives
        # exactly one distinct price.
        if len(price_candidates) != 1:
            continue

        result = label.copy()

        result["price"] = price_candidates[0]
        result["text"] = " | ".join(texts)

        results.append(result)

    print(
        color.upper(),
        "LABELS:",
        [
            item["price"]
            for item in results
        ],
        flush=True
    )

    return results


# ============================================================
# ENTRY
# ============================================================

def find_yellow_entry(frame):

    labels = find_color_labels(
        frame,
        "yellow"
    )

    # Prefer OCR that explicitly identifies Entry.
    confirmed = [
        item
        for item in labels
        if "ENTRY" in item["text"]
    ]

    if len(confirmed) == 1:

        selected = confirmed[0]

    elif len(confirmed) > 1:

        print(
            "MULTIPLE ENTRY LABELS.",
            flush=True
        )

        return None

    elif len(labels) == 1:

        # A single yellow price label in the right-hand
        # label area can be used when ENTRY text is tiny.
        selected = labels[0]

    else:

        print(
            "ENTRY NOT CONFIRMED",
            flush=True
        )

        return None

    print(
        "ENTRY DETECTED:",
        selected["price"],
        flush=True
    )

    return selected["price"]


# ============================================================
# TARGETS
# ============================================================

def find_green_targets(frame, entry):

    labels = find_color_labels(
        frame,
        "green"
    )

    prices = []

    for item in labels:

        price = item["price"]

        if abs(price - entry) < 0.01:
            continue

        if all(
            abs(price - existing) >= 0.01
            for existing in prices
        ):

            prices.append(price)

    return prices


# ============================================================
# DIRECTION
# ============================================================

def determine_direction(entry, targets):

    above = sorted(
        price
        for price in targets
        if price > entry
    )

    below = sorted(
        (
            price
            for price in targets
            if price < entry
        ),
        reverse=True
    )

    # Require exactly three prices on one side.
    # Reject ambiguous labels.
    if len(above) == 3 and not below:

        return "BUY", above

    if len(below) == 3 and not above:

        return "SELL", below

    return None, []


# ============================================================
# OPTIONAL STOP LOSS
# ============================================================

def find_stop_loss(frame, entry, direction):

    labels = find_color_labels(
        frame,
        "red"
    )

    candidates = []

    for item in labels:

        price = item["price"]

        if direction == "BUY" and price < entry:

            candidates.append(price)

        elif direction == "SELL" and price > entry:

            candidates.append(price)

    unique = []

    for price in candidates:

        if all(
            abs(price - existing) >= 0.01
            for existing in unique
        ):

            unique.append(price)

    if len(unique) == 1:

        print(
            "STOP LOSS DETECTED:",
            unique[0],
            flush=True
        )

        return unique[0]

    print(
        "STOP LOSS NOT CONFIRMED",
        flush=True
    )

    return None


# ============================================================
# MAIN DETECTOR
# ============================================================

def detect_signal(frame):

    print(
        "RUNNING MILLION MOVES DETECTOR",
        flush=True
    )

    if frame is None:
        return None

    if not isinstance(frame, np.ndarray):
        return None

    if frame.size == 0:
        return None

    entry = find_yellow_entry(frame)

    if entry is None:
        return None

    targets = find_green_targets(
        frame,
        entry
    )

    if len(targets) < 3:

        print(
            "TARGETS NOT DETECTED:",
            targets,
            flush=True
        )

        return None

    direction, ordered_targets = determine_direction(
        entry,
        targets
    )

    if direction is None:

        print(
            "DIRECTION NOT CONFIRMED:",
            targets,
            flush=True
        )

        return None

    tp1, tp2, tp3 = ordered_targets

    sl = find_stop_loss(
        frame,
        entry,
        direction
    )

    signal = {
        "direction": direction,
        "entry": round(entry, 2),
        "sl": (
            round(sl, 2)
            if sl is not None
            else None
        ),
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
# END
# ============================================================