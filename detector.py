import re

import cv2
import numpy as np
import pytesseract


PRICE_PATTERN = re.compile(
    r"(?<!\d)(\d{4,5}[.,]\d{1,3})(?!\d)"
)


def log(message):
    print(message, flush=True)


def extract_price(text):
    if not text:
        return None

    cleaned = text.replace(" ", "")

    matches = PRICE_PATTERN.findall(
        cleaned
    )

    for match in matches:
        try:
            value = float(
                match.replace(",", ".")
            )

            if 1000 <= value <= 10000:
                return round(value, 2)

        except ValueError:
            pass

    return None


def preprocess(image):
    if image is None or image.size == 0:
        return None

    enlarged = cv2.resize(
        image,
        None,
        fx=3,
        fy=3,
        interpolation=cv2.INTER_CUBIC
    )

    gray = cv2.cvtColor(
        enlarged,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.GaussianBlur(
        gray,
        (3, 3),
        0
    )

    return cv2.convertScaleAbs(
        gray,
        alpha=1.7,
        beta=10
    )


def read_text(image, config=None):
    processed = preprocess(
        image
    )

    if processed is None:
        return ""

    if config is None:
        config = (
            "--oem 3 --psm 11"
        )

    try:
        return pytesseract.image_to_string(
            processed,
            config=config
        )

    except Exception as error:
        log(
            "OCR ERROR: "
            f"{type(error).__name__}: {error}"
        )

        return ""


def normalize_line(line):
    line = line.upper()

    line = line.replace(
        "TAKE PROFIT",
        "TP"
    )

    line = line.replace(
        "STOP LOSS",
        "SL"
    )

    line = line.replace(
        "S/L",
        "SL"
    )

    line = line.replace(
        "T/P",
        "TP"
    )

    return line.strip()


def find_labeled_price(lines, labels):
    for index, original in enumerate(lines):

        line = normalize_line(
            original
        )

        if not any(
            re.search(label, line)
            for label in labels
        ):
            continue

        price = extract_price(
            line
        )

        if price is not None:
            return price

        # OCR sometimes separates a label and
        # its price onto consecutive lines.
        if index + 1 < len(lines):

            next_line = normalize_line(
                lines[index + 1]
            )

            price = extract_price(
                next_line
            )

            if price is not None:
                return price

    return None


def detect_direction(lines):
    for line in lines:

        normalized = normalize_line(
            line
        )

        if re.search(
            r"\bBUY\b",
            normalized
        ):
            return "BUY"

        if re.search(
            r"\bSELL\b",
            normalized
        ):
            return "SELL"

    return None


def read_signal_text(text):
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    direction = detect_direction(
        lines
    )

    entry = find_labeled_price(
        lines,
        [
            r"\bENTRY\b",
            r"\bENT\b"
        ]
    )

    sl = find_labeled_price(
        lines,
        [
            r"\bSL\b"
        ]
    )

    tp1 = find_labeled_price(
        lines,
        [
            r"\bTP\s*1\b",
            r"\bTP1\b"
        ]
    )

    tp2 = find_labeled_price(
        lines,
        [
            r"\bTP\s*2\b",
            r"\bTP2\b"
        ]
    )

    tp3 = find_labeled_price(
        lines,
        [
            r"\bTP\s*3\b",
            r"\bTP3\b"
        ]
    )

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3
    }


def validate_signal(signal):
    required = (
        "direction",
        "entry",
        "sl",
        "tp1",
        "tp2",
        "tp3"
    )

    if any(
        signal.get(key) is None
        for key in required
    ):
        return False

    direction = signal["direction"]

    entry = signal["entry"]
    sl = signal["sl"]

    tp1 = signal["tp1"]
    tp2 = signal["tp2"]
    tp3 = signal["tp3"]

    if direction == "BUY":
        return (
            sl < entry
            and entry < tp1
            and tp1 < tp2
            and tp2 < tp3
        )

    if direction == "SELL":
        return (
            sl > entry
            and entry > tp1
            and tp1 > tp2
            and tp2 > tp3
        )

    return False


def get_right_side(frame):
    height, width = frame.shape[:2]

    # Exclude the historical signals
    # displayed in the chart's center.
    x1 = int(
        width * 0.65
    )

    return frame[
        0:height,
        x1:width
    ]


def detect_signal(frame):
    if frame is None:
        log("DETECTOR: EMPTY FRAME")
        return None

    if not isinstance(
        frame,
        np.ndarray
    ):
        log("DETECTOR: INVALID FRAME")
        return None

    if frame.size == 0:
        log("DETECTOR: ZERO-SIZE FRAME")
        return None

    log(
        f"DETECTOR FRAME: {frame.shape}"
    )

    right_side = get_right_side(
        frame
    )

    # First OCR pass: automatic sparse text.
    text = read_text(
        right_side,
        "--oem 3 --psm 11"
    )

    signal = read_signal_text(
        text
    )

    if validate_signal(signal):
        log(
            f"COMPLETE SIGNAL: {signal}"
        )

        return signal

    # Second OCR pass: alternative segmentation.
    alternate_text = read_text(
        right_side,
        "--oem 3 --psm 6"
    )

    alternate_signal = read_signal_text(
        alternate_text
    )

    if validate_signal(
        alternate_signal
    ):
        log(
            "COMPLETE SIGNAL FROM "
            "ALTERNATIVE OCR"
        )

        return alternate_signal

    # Combine only matching values.
    # Never replace one conflicting price
    # with another guessed price.
    combined = {}

    for key in (
        "direction",
        "entry",
        "sl",
        "tp1",
        "tp2",
        "tp3"
    ):
        first = signal.get(key)

        second = alternate_signal.get(key)

        if first is None:
            combined[key] = second

        elif second is None:
            combined[key] = first

        elif first == second:
            combined[key] = first

        else:
            log(
                f"CONFLICTING OCR FOR {key}: "
                f"{first} / {second}"
            )

            combined[key] = None

    if validate_signal(
        combined
    ):
        log(
            f"COMPLETE SIGNAL: {combined}"
        )

        return combined

    missing = [
        key
        for key in (
            "direction",
            "entry",
            "sl",
            "tp1",
            "tp2",
            "tp3"
        )
        if combined.get(key) is None
    ]

    log(
        f"INCOMPLETE SIGNAL. "
        f"MISSING OR UNCERTAIN: {missing}"
    )

    log(
        f"OCR VALUES: {combined}"
    )

    return None