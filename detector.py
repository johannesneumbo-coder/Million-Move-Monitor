import cv2
import numpy as np
import pytesseract
import re
from collections import Counter


# ============================================================
# MILLION MOVES V5 - LIVE XAUUSD DETECTOR
#
# YELLOW = ENTRY
# GREEN / TURQUOISE = TP1, TP2, TP3
# RED = STOP LOSS (OPTIONAL)
#
# Only reads colored labels on the right of the chart.
# Does not use historical Smart Buy / Smart Sell markers.
# Does not invent prices.
# ============================================================


MIN_PRICE = 1000.0
MAX_PRICE = 10000.0

RIGHT_START = 0.77
RIGHT_END = 0.97

TOP_LIMIT = 0.08
BOTTOM_LIMIT = 0.92


# ============================================================
# EXTRACT PRICES
# ============================================================

def extract_prices(text):

    if not text:
        return []

    text = text.upper()

    text = re.sub(
        r"(?<=\d)\s+(?=\d)",
        "",
        text
    )

    text = text.replace(",", "")

    matches = re.findall(
        r"(?<!\d)\d{4,5}\.\d{1,3}(?!\d)",
        text
    )

    prices = []

    for value in matches:

        try:

            price = float(value)

            if MIN_PRICE <= price <= MAX_PRICE:

                prices.append(
                    round(price, 2)
                )

        except ValueError:

            continue

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

            for psm in (7, 6):

                text = pytesseract.image_to_string(
                    processed,
                    config=(
                        f"--psm {psm} "
                        "-c preserve_interword_spaces=1"
                    )
                )

                text = text.upper().strip()

                if text:
                    results.append(text)

        return results

    except Exception as error:

        print(
            "OCR ERROR:",
            type(error).__name__,
            str(error),
            flush=True
        )

        return []


# ============================================================
# READ CONFIRMED PRICE
# ============================================================

def read_label_price(image):

    texts = ocr_variants(image)

    votes = []

    for text in texts:

        prices = list(
            dict.fromkeys(
                extract_prices(text)
            )
        )

        if len(prices) == 1:
            votes.append(prices[0])

    if not votes:
        return None, ""

    counts = Counter(votes)

    price, count = counts.most_common(1)[0]

    # Require two OCR passes to agree.
    if count < 2:

        return (
            None,
            " | ".join(texts[:3])
        )

    return (
        price,
        " | ".join(texts[:3])
    )


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
            np.array([15, 65, 65]),
            np.array([45, 255, 255])
        )

    elif color == "green":

        # Includes green and turquoise TP labels.

        mask = cv2.inRange(
            hsv,
            np.array([40, 55, 55]),
            np.array([105, 255, 255])
        )

    elif color == "red":

        lower = cv2.inRange(
            hsv,
            np.array([0, 75, 60]),
            np.array([12, 255, 255])
        )

        upper = cv2.inRange(
            hsv,
            np.array([160, 75, 60]),
            np.array([180, 255, 255])
        )

        mask = cv2.bitwise_or(
            lower,
            upper
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

    x1 = int(width * RIGHT_START)
    x2 = int(width * RIGHT_END)

    y1 = int(height * TOP_LIMIT)
    y2 = int(height * BOTTOM_LIMIT)

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

    candidates = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        area = cv2.contourArea(
            contour
        )

        if area < 35:
            continue

        if w < 18 or h < 6:
            continue

        if w > width * 0.20:
            continue

        if h > height * 0.075:
            continue

        if w / max(h, 1) < 1.8:
            continue

        real_x = x + x1
        real_y = y + y1

        candidates.append(
            {
                "x": real_x,
                "y": real_y,
                "w": w,
                "h": h,
                "area": area
            }
        )

    candidates.sort(
        key=lambda item: -item["area"]
    )

    results = []

    for item in candidates:

        x = item["x"]
        y = item["y"]
        w = item["w"]
        h = item["h"]

        crop = safe_crop(
            frame,
            x - 3,
            y - 3,
            x + w + 3,
            y + h + 3
        )

        price, text = read_label_price(
            crop
        )

        if price is None:

            crop = safe_crop(
                frame,
                x - 8,
                y - 4,
                x + w + 8,
                y + h + 4
            )

            price, text = read_label_price(
                crop
            )

        if price is None:
            continue

        duplicate = False

        for existing in results:

            if (
                abs(
                    existing["price"] - price
                ) < 0.01
                and
                abs(
                    existing["y"] - y
                ) < 15
            ):

                duplicate = True
                break

        if duplicate:
            continue

        results.append(
            {
                **item,
                "price": price,
                "text": text
            }
        )

    results.sort(
        key=lambda item: item["y"]
    )

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

    if not labels:

        print(
            "ENTRY NOT CONFIRMED",
            flush=True
        )

        return None

    unique_prices = sorted(
        set(
            item["price"]
            for item in labels
        )
    )

    if len(unique_prices) != 1:

        print(
            "AMBIGUOUS ENTRY:",
            unique_prices,
            flush=True
        )

        return None

    selected = max(
        labels,
        key=lambda item: item["area"]
    )

    print(
        "ENTRY DETECTED:",
        selected["price"],
        flush=True
    )

    return {
        **selected,
        "entry": selected["price"]
    }


# ============================================================
# TARGETS
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

        if any(
            abs(
                price - existing["price"]
            ) < 0.01
            for existing in targets
        ):
            continue

        targets.append(item)

    print(
        "TARGET CANDIDATES:",
        [
            item["price"]
            for item in targets
        ],
        flush=True
    )

    return targets


# ============================================================
# DETERMINE DIRECTION
# ============================================================

def determine_direction(entry, targets):

    above = [
        item
        for item in targets
        if item["price"] > entry
    ]

    below = [
        item
        for item in targets
        if item["price"] < entry
    ]

    # Require exactly three targets.
    # Extra colored prices make the setup ambiguous.

    if len(above) == 3 and len(below) == 0:

        above.sort(
            key=lambda item: item["price"]
        )

        return "BUY", above

    if len(below) == 3 and len(above) == 0:

        below.sort(
            key=lambda item: -item["price"]
        )

        return "SELL", below

    return None, []


# ============================================================
# OPTIONAL STOP LOSS
# ============================================================

def find_red_stop_loss(frame, entry, direction):

    labels = find_color_labels(
        frame,
        "red"
    )

    valid = []

    for item in labels:

        price = item["price"]

        if direction == "BUY" and price < entry:

            valid.append(item)

        elif direction == "SELL" and price > entry:

            valid.append(item)

    # Do not guess if more than one red price exists.
    if len(valid) != 1:

        print(
            "STOP LOSS NOT CONFIRMED",
            flush=True
        )

        return None

    sl = valid[0]["price"]

    print(
        "STOP LOSS DETECTED:",
        sl,
        flush=True
    )

    return sl


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

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    entry_data = find_yellow_entry(
        frame
    )

    if entry_data is None:

        return None

    entry = entry_data["entry"]

    # --------------------------------------------------------
    # TARGETS
    # --------------------------------------------------------

    targets = find_green_targets(
        frame,
        entry
    )

    if len(targets) < 3:

        print(
            "TARGETS NOT DETECTED:",
            len(targets),
            "of 3",
            flush=True
        )

        return None

    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------

    direction, ordered_targets = determine_direction(
        entry,
        targets
    )

    if direction is None:

        print(
            "DIRECTION NOT CONFIRMED",
            flush=True
        )

        return None

    # --------------------------------------------------------
    # ASSIGN TARGETS
    # --------------------------------------------------------

    tp1 = ordered_targets[0]["price"]
    tp2 = ordered_targets[1]["price"]
    tp3 = ordered_targets[2]["price"]

    # --------------------------------------------------------
    # VERIFY TARGET ORDER
    # --------------------------------------------------------

    if direction == "BUY":

        valid = (
            entry < tp1 < tp2 < tp3
        )

    else:

        valid = (
            tp3 < tp2 < tp1 < entry
        )

    if not valid:

        print(
            "TARGET ORDER INVALID",
            flush=True
        )

        return None

    # --------------------------------------------------------
    # OPTIONAL STOP LOSS
    # --------------------------------------------------------

    sl = find_red_stop_loss(
        frame,
        entry,
        direction
    )

    # --------------------------------------------------------
    # FINAL SIGNAL
    # --------------------------------------------------------

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