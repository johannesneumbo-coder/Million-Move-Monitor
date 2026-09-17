import re

import cv2
import numpy as np
import pytesseract


# ============================================================
# MILLION MOVES XAUUSD SIGNAL DETECTOR
#
# Yellow = Entry
# Green  = TP1, TP2, TP3
# Red    = Stop Loss
#
# Detect labels on the right side of the video.
# Never guess missing prices.
# ============================================================


def extract_prices(text):
    text = text.replace(",", "")

    matches = re.findall(
        r"(?<!\d)\d{4,5}[.,]\d{1,3}(?!\d)",
        text
    )

    prices = []

    for match in matches:
        try:
            price = float(match.replace(",", "."))

            if 1000 <= price <= 10000:
                prices.append(round(price, 2))

        except ValueError:
            continue

    return prices


def clean_text(text):
    return " ".join(text.upper().split())


def read_text(image, psm=7):
    if image is None or image.size == 0:
        return ""

    if len(image.shape) == 3:
        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )
    else:
        gray = image

    gray = cv2.resize(
        gray,
        None,
        fx=3,
        fy=3,
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

    for candidate in (
        gray,
        threshold,
        255 - threshold
    ):
        try:
            text = pytesseract.image_to_string(
                candidate,
                config=(
                    f"--psm {psm} "
                    "-c tessedit_char_whitelist="
                    "0123456789.,ABCDEFGHIJKLMNOPQRSTUVWXYZ:/- "
                )
            )

            if text.strip():
                results.append(text.strip())

        except Exception as exc:
            print(
                "OCR ERROR:",
                exc,
                flush=True
            )

    return "\n".join(results)


def make_colour_mask(hsv, colour):

    if colour == "yellow":

        lower = np.array([15, 75, 75])
        upper = np.array([42, 255, 255])

        return cv2.inRange(
            hsv,
            lower,
            upper
        )

    if colour == "green":

        lower = np.array([35, 45, 40])
        upper = np.array([100, 255, 255])

        return cv2.inRange(
            hsv,
            lower,
            upper
        )

    if colour == "red":

        lower1 = np.array([0, 65, 55])
        upper1 = np.array([12, 255, 255])

        lower2 = np.array([168, 65, 55])
        upper2 = np.array([179, 255, 255])

        return cv2.bitwise_or(
            cv2.inRange(
                hsv,
                lower1,
                upper1
            ),
            cv2.inRange(
                hsv,
                lower2,
                upper2
            )
        )

    return np.zeros(
        hsv.shape[:2],
        dtype=np.uint8
    )


def find_label_regions(frame, colour):

    height, width = frame.shape[:2]

    left = int(width * 0.58)

    right_frame = frame[:, left:width]

    hsv = cv2.cvtColor(
        right_frame,
        cv2.COLOR_BGR2HSV
    )

    mask = make_colour_mask(
        hsv,
        colour
    )

    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (13, 3)
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel
    )

    mask = cv2.dilate(
        mask,
        np.ones((3, 5), np.uint8),
        iterations=1
    )

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    regions = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        if w < 12 or h < 5:
            continue

        if w * h < 90:
            continue

        x += left

        pad_x = max(
            12,
            int(width * 0.025)
        )

        pad_y = 7

        x1 = max(
            left,
            x - pad_x
        )

        y1 = max(
            0,
            y - pad_y
        )

        x2 = min(
            width,
            x + w + pad_x
        )

        y2 = min(
            height,
            y + h + pad_y
        )

        regions.append({
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "centre_y": (y1 + y2) / 2
        })

    regions.sort(
        key=lambda item: item["centre_y"]
    )

    merged = []

    for region in regions:

        if (
            merged
            and region["y1"] <= merged[-1]["y2"]
            and abs(
                region["centre_y"]
                - merged[-1]["centre_y"]
            ) < max(
                12,
                height * 0.025
            )
        ):

            previous = merged[-1]

            previous["x1"] = min(
                previous["x1"],
                region["x1"]
            )

            previous["y1"] = min(
                previous["y1"],
                region["y1"]
            )

            previous["x2"] = max(
                previous["x2"],
                region["x2"]
            )

            previous["y2"] = max(
                previous["y2"],
                region["y2"]
            )

            previous["centre_y"] = (
                previous["y1"]
                + previous["y2"]
            ) / 2

        else:

            merged.append(
                region.copy()
            )

    return merged


# ============================================================
# FIXED LABEL READING
#
# Crop each detected label separately.
# Do not extend the crop to the right edge.
# Try OCR methods independently.
# ============================================================

def read_label(frame, region):

    height, width = frame.shape[:2]

    x1 = max(
        0,
        region["x1"] - 5
    )

    x2 = min(
        width,
        region["x2"] + 5
    )

    y1 = max(
        0,
        region["y1"] - 2
    )

    y2 = min(
        height,
        region["y2"] + 2
    )

    crop = frame[
        y1:y2,
        x1:x2
    ]

    if crop.size == 0:
        return None

    for psm in (7, 6):

        text = read_text(
            crop,
            psm=psm
        )

        prices = extract_prices(
            text
        )

        unique_prices = list(
            dict.fromkeys(prices)
        )

        if len(unique_prices) == 1:

            return {
                "price": unique_prices[0],
                "text": clean_text(text),
                "y": region["centre_y"]
            }

    return None


def get_colour_labels(frame, colour):

    regions = find_label_regions(
        frame,
        colour
    )

    labels = []

    for region in regions:

        result = read_label(
            frame,
            region
        )

        if result is not None:
            labels.append(result)

    labels.sort(
        key=lambda item: item["y"]
    )

    unique = []

    for label in labels:

        duplicate = False

        for previous in unique:

            if (
                label["price"] == previous["price"]
                and abs(
                    label["y"] - previous["y"]
                ) < 18
            ):

                duplicate = True
                break

        if not duplicate:
            unique.append(label)

    print(
        colour.upper() + " LABELS:",
        unique,
        flush=True
    )

    return unique


def choose_entry(labels):

    if not labels:
        return None

    explicit = [
        label
        for label in labels
        if "ENTRY" in label["text"]
    ]

    if len(explicit) == 1:
        return explicit[0]["price"]

    if len(labels) == 1:
        return labels[0]["price"]

    return None


def choose_stop_loss(
    labels,
    entry,
    direction
):

    candidates = []

    for label in labels:

        price = label["price"]

        if (
            direction == "BUY"
            and price < entry
        ):
            candidates.append(price)

        elif (
            direction == "SELL"
            and price > entry
        ):
            candidates.append(price)

    if len(candidates) == 1:
        return candidates[0]

    return None


def choose_targets(labels, entry):

    prices = []

    for label in labels:

        price = label["price"]

        if price == entry:
            continue

        if price not in prices:
            prices.append(price)

    if len(prices) != 3:

        print(
            "TARGETS NOT CONFIRMED: expected 3, found",
            len(prices),
            flush=True
        )

        return None

    below = all(
        price < entry
        for price in prices
    )

    above = all(
        price > entry
        for price in prices
    )

    if below:

        direction = "SELL"

        prices.sort(
            reverse=True
        )

    elif above:

        direction = "BUY"

        prices.sort()

    else:

        print(
            "TARGETS REJECTED: inconsistent direction",
            prices,
            flush=True
        )

        return None

    return {
        "direction": direction,
        "tp1": prices[0],
        "tp2": prices[1],
        "tp3": prices[2]
    }


def detect_signal(frame):

    if frame is None or frame.size == 0:

        print(
            "EMPTY FRAME",
            flush=True
        )

        return None

    print(
        "DETECTOR FRAME:",
        frame.shape,
        flush=True
    )

    yellow_labels = get_colour_labels(
        frame,
        "yellow"
    )

    entry = choose_entry(
        yellow_labels
    )

    if entry is None:

        print(
            "ENTRY NOT CONFIRMED",
            flush=True
        )

        return None

    print(
        "ENTRY:",
        entry,
        flush=True
    )

    green_labels = get_colour_labels(
        frame,
        "green"
    )

    targets = choose_targets(
        green_labels,
        entry
    )

    if targets is None:
        return None

    direction = targets["direction"]

    red_labels = get_colour_labels(
        frame,
        "red"
    )

    sl = choose_stop_loss(
        red_labels,
        entry,
        direction
    )

    signal = {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp1": targets["tp1"],
        "tp2": targets["tp2"],
        "tp3": targets["tp3"]
    }

    print(
        "SIGNAL DETECTED:",
        signal,
        flush=True
    )

    return signal