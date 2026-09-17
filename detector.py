import re
from collections import defaultdict

import cv2
import pytesseract


# ============================================================
# MILLION MOVES DETECTOR
# TEXT ONLY - NO COLOUR DETECTION
# ============================================================

PRICE_RE = re.compile(
    r"(?<!\d)(\d{4,5}[.,]\d{2})(?!\d)"
)


def extract_price(text):
    matches = PRICE_RE.findall(text)

    values = []

    for match in matches:
        try:
            value = round(
                float(match.replace(",", ".")),
                2
            )

            if 1000 <= value <= 10000:
                values.append(value)

        except ValueError:
            pass

    values = list(dict.fromkeys(values))

    if len(values) == 1:
        return values[0]

    return None


def identify_label(text):
    text = text.upper()

    text = text.replace("|", "1")

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    if re.search(
        r"\bENTRY\b",
        text
    ):
        return "entry"

    if re.search(
        r"\bSTOP\s*LOSS\b|\bSTOP\b|\bSL\b",
        text
    ):
        return "sl"

    for number in (1, 2, 3):
        pattern = (
            r"\bT\s*P\s*"
            + str(number)
            + r"\b"
        )

        if re.search(pattern, text):
            return "tp" + str(number)

    return None


def prepare_images(frame):
    height, width = frame.shape[:2]

    # Only the right-hand label area.
    x1 = int(width * 0.70)
    x2 = int(width * 0.95)

    crop = frame[:, x1:x2]

    if crop.size == 0:
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

    return [
        gray,
        binary,
        cv2.bitwise_not(binary)
    ]


def read_ocr_lines(image):
    try:
        data = pytesseract.image_to_data(
            image,
            config="--psm 11",
            output_type=pytesseract.Output.DICT
        )

    except Exception as error:
        print(
            "OCR ERROR:",
            error,
            flush=True
        )

        return []

    groups = defaultdict(list)

    for index, word in enumerate(data["text"]):
        word = word.strip()

        if not word:
            continue

        key = (
            data["block_num"][index],
            data["par_num"][index],
            data["line_num"][index]
        )

        groups[key].append(
            (
                data["left"][index],
                data["top"][index],
                word
            )
        )

    lines = []

    for words in groups.values():
        words.sort(key=lambda item: item[0])

        text = " ".join(
            item[2]
            for item in words
        )

        y = min(
            item[1]
            for item in words
        )

        lines.append((y, text))

    lines.sort(key=lambda item: item[0])

    return lines


def read_labels(frame):
    images = prepare_images(frame)

    observations = defaultdict(list)

    for image in images:
        lines = read_ocr_lines(image)

        for _, text in lines:
            label = identify_label(text)

            if label is None:
                continue

            price = extract_price(text)

            if price is None:
                continue

            observations[label].append(price)

    confirmed = {}

    for label, prices in observations.items():
        unique = set(prices)

        if len(unique) == 1:
            confirmed[label] = prices[0]

        else:
            print(
                "CONFLICTING OCR:",
                label,
                prices,
                flush=True
            )

    print(
        "TEXT LABELS:",
        confirmed,
        flush=True
    )

    return confirmed


def detect_signal(frame):
    if frame is None:
        print(
            "EMPTY FRAME",
            flush=True
        )
        return None

    if frame.size == 0:
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

    labels = read_labels(frame)

    required = [
        "entry",
        "tp1",
        "tp2",
        "tp3"
    ]

    missing = [
        name
        for name in required
        if name not in labels
    ]

    if missing:
        print(
            "MISSING LABELS:",
            missing,
            flush=True
        )
        return None

    entry = labels["entry"]
    tp1 = labels["tp1"]
    tp2 = labels["tp2"]
    tp3 = labels["tp3"]

    if entry < tp1 < tp2 < tp3:
        direction = "BUY"

    elif entry > tp1 > tp2 > tp3:
        direction = "SELL"

    else:
        print(
            "INVALID TARGET ORDER:",
            labels,
            flush=True
        )
        return None

    sl = labels.get("sl")

    if sl is not None:
        if direction == "BUY" and sl >= entry:
            print(
                "INVALID BUY STOP LOSS",
                flush=True
            )
            return None

        if direction == "SELL" and sl <= entry:
            print(
                "INVALID SELL STOP LOSS",
                flush=True
            )
            return None

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