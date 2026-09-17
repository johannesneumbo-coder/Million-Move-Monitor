import re
from collections import Counter

import cv2
import numpy as np
import pytesseract


# ============================================================
# MILLION MOVES DETECTOR
#
# Yellow = Entry
# Green  = TP1 / TP2 / TP3
# Red    = Stop loss
#
# Only inspect coloured price labels on the right.
# Never invent a missing price.
# ============================================================


def extract_prices(text):
    text = text.replace(",", "")

    matches = re.findall(
        r"(?<!\d)\d{4,5}\.\d{1,3}(?!\d)",
        text
    )

    prices = []

    for match in matches:
        try:
            value = round(float(match), 2)

            if 1000 <= value <= 10000:
                prices.append(value)

        except ValueError:
            pass

    return prices


def colour_mask(hsv, colour):

    if colour == "yellow":
        return cv2.inRange(
            hsv,
            np.array([15, 85, 95]),
            np.array([43, 255, 255])
        )

    if colour == "green":
        return cv2.inRange(
            hsv,
            np.array([35, 75, 85]),
            np.array([105, 255, 255])
        )

    if colour == "red":
        first = cv2.inRange(
            hsv,
            np.array([0, 75, 75]),
            np.array([13, 255, 255])
        )

        second = cv2.inRange(
            hsv,
            np.array([165, 75, 75]),
            np.array([179, 255, 255])
        )

        return cv2.bitwise_or(first, second)

    return np.zeros(
        hsv.shape[:2],
        dtype=np.uint8
    )


def find_labels(frame, colour):

    height, width = frame.shape[:2]

    # The active price labels are on the far right.
    left = int(width * 0.75)

    right = frame[:, left:]

    hsv = cv2.cvtColor(
        right,
        cv2.COLOR_BGR2HSV
    )

    mask = colour_mask(hsv, colour)

    # Connect characters and background within a label.
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (7, 3)
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel
    )

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    regions = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(contour)

        # Reject tiny coloured chart details.
        if w < 20 or h < 6:
            continue

        # Reject large chart regions.
        if h > max(35, int(height * 0.08)):
            continue

        if w > int(width * 0.24):
            continue

        area = cv2.contourArea(contour)

        if area / max(w * h, 1) < 0.35:
            continue

        x += left

        regions.append({
            "x1": max(left, x - 4),
            "y1": max(0, y - 3),
            "x2": min(width, x + w + 4),
            "y2": min(height, y + h + 3),
            "y": y + h / 2
        })

    regions.sort(key=lambda item: item["y"])

    # Combine overlapping pieces of the same label.
    merged = []

    for region in regions:

        if (
            merged
            and abs(region["y"] - merged[-1]["y"]) < 9
        ):

            previous = merged[-1]

            previous["x1"] = min(
                previous["x1"],
                region["x1"]
            )

            previous["x2"] = max(
                previous["x2"],
                region["x2"]
            )

            previous["y1"] = min(
                previous["y1"],
                region["y1"]
            )

            previous["y2"] = max(
                previous["y2"],
                region["y2"]
            )

        else:
            merged.append(region.copy())

    return merged


def ocr_candidates(crop):

    if crop is None or crop.size == 0:
        return []

    gray = cv2.cvtColor(
        crop,
        cv2.COLOR_BGR2GRAY
    )

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

    variants = [
        gray,
        binary,
        255 - binary
    ]

    results = []

    for image in variants:

        for psm in (7, 13):

            try:
                text = pytesseract.image_to_string(
                    image,
                    config=(
                        f"--psm {psm} "
                        "-c tessedit_char_whitelist="
                        "0123456789.,"
                    )
                )

                prices = extract_prices(text)

                if len(prices) == 1:
                    results.append(prices[0])

            except Exception as exc:
                print(
                    "OCR ERROR:",
                    exc,
                    flush=True
                )

    return results


def read_label(frame, region):

    crop = frame[
        region["y1"]:region["y2"],
        region["x1"]:region["x2"]
    ]

    candidates = ocr_candidates(crop)

    if not candidates:
        return None

    counts = Counter(candidates)

    price, votes = counts.most_common(1)[0]

    # Require two independent OCR attempts to agree.
    if votes < 2:
        print(
            "REJECTED UNCERTAIN PRICE:",
            candidates,
            flush=True
        )
        return None

    # Reject competing readings with equal support.
    if len(counts) > 1:
        second_votes = counts.most_common(2)[1][1]

        if second_votes == votes:
            print(
                "REJECTED CONFLICTING PRICES:",
                candidates,
                flush=True
            )
            return None

    return {
        "price": price,
        "y": region["y"]
    }


def get_labels(frame, colour):

    regions = find_labels(frame, colour)

    labels = []

    for region in regions:

        label = read_label(frame, region)

        if label is not None:
            labels.append(label)

    labels.sort(key=lambda item: item["y"])

    print(
        colour.upper() + " LABELS:",
        labels,
        flush=True
    )

    return labels


def detect_signal(frame):

    if frame is None or frame.size == 0:
        print("EMPTY FRAME", flush=True)
        return None

    print(
        "DETECTOR FRAME:",
        frame.shape,
        flush=True
    )

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    yellow = get_labels(frame, "yellow")

    if len(yellow) != 1:
        print("ENTRY NOT CONFIRMED", flush=True)
        return None

    entry = yellow[0]["price"]

    print("ENTRY:", entry, flush=True)

    # --------------------------------------------------------
    # TARGETS
    # --------------------------------------------------------

    green = get_labels(frame, "green")

    # Three separate green labels are required.
    if len(green) != 3:
        print(
            "TARGETS NOT CONFIRMED: expected 3, found",
            len(green),
            flush=True
        )
        return None

    prices = [label["price"] for label in green]

    if len(set(prices)) != 3:
        print(
            "DUPLICATE TP PRICES REJECTED:",
            prices,
            flush=True
        )
        return None

    # Preserve the labels' vertical order:
    # TP1 at the top, then TP2, then TP3.
    tp1, tp2, tp3 = prices

    if tp1 > entry and tp2 > tp1 and tp3 > tp2:

        direction = "BUY"

    elif tp1 < entry and tp2 < tp1 and tp3 < tp2:

        direction = "SELL"

    else:

        print(
            "TARGET PRICES INCONSISTENT:",
            prices,
            "ENTRY:",
            entry,
            flush=True
        )

        return None

    # --------------------------------------------------------
    # STOP LOSS
    # --------------------------------------------------------

    red = get_labels(frame, "red")

    sl = None

    valid_stops = []

    for label in red:

        price = label["price"]

        if direction == "BUY" and price < entry:
            valid_stops.append(price)

        elif direction == "SELL" and price > entry:
            valid_stops.append(price)

    if len(valid_stops) == 1:
        sl = valid_stops[0]

    # --------------------------------------------------------
    # FINAL SIGNAL
    # --------------------------------------------------------

    signal = {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3
    }

    print(
        "SIGNAL DETECTED:",
        signal,
        flush=True
    )

    return signal