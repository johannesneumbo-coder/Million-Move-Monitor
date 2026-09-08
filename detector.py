import cv2
import numpy as np
import pytesseract
import re


def extract_prices(text):

    values = []

    patterns = re.findall(
        r"\d{1,2},\d{3}\.\d{1,3}|\d{4,5}\.\d{1,3}",
        text
    )

    for value in patterns:

        try:

            number = float(
                value.replace(",", "")
            )

            if 1000 <= number <= 10000:

                values.append(number)

        except ValueError:

            pass

    return values


def crop_with_padding(
    frame,
    x,
    y,
    w,
    h,
    padding=3
):

    height, width = frame.shape[:2]

    x1 = max(
        0,
        x - padding
    )

    y1 = max(
        0,
        y - padding
    )

    x2 = min(
        width,
        x + w + padding
    )

    y2 = min(
        height,
        y + h + padding
    )

    return frame[
        y1:y2,
        x1:x2
    ]


def ocr_label(
    crop,
    psm=6
):

    try:

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

        text = pytesseract.image_to_string(
            gray,
            config=f"--psm {psm}"
        )

        return text.upper().strip()

    except Exception as e:

        print(
            "Label OCR error:",
            type(e).__name__,
            str(e),
            flush=True
        )

        return ""


def find_yellow_entry(frame):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    yellow_lower = np.array(
        [15, 80, 80]
    )

    yellow_upper = np.array(
        [45, 255, 255]
    )

    mask = cv2.inRange(
        hsv,
        yellow_lower,
        yellow_upper
    )

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    height, width = frame.shape[:2]

    candidates = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        area = cv2.contourArea(
            contour
        )

        if x < width * 0.75:
            continue

        if w < 60 or w > 220:
            continue

        if h < 12 or h > 60:
            continue

        if area < 500:
            continue

        candidates.append(
            (
                x,
                y,
                w,
                h,
                area
            )
        )

    if not candidates:

        return None

    candidates.sort(
        key=lambda item: item[4],
        reverse=True
    )

    x, y, w, h, area = (
        candidates[0]
    )

    crop = crop_with_padding(
        frame,
        x,
        y,
        w,
        h,
        padding=3
    )

    text = ocr_label(
        crop,
        psm=6
    )

    prices = extract_prices(
        text
    )

    if not prices:

        return None

    entry = prices[0]

    return {
        "entry": entry,
        "text": text,
        "x": x,
        "y": y,
        "w": w,
        "h": h
    }


def find_red_stop_loss(frame):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    red1 = cv2.inRange(
        hsv,
        np.array([0, 100, 80]),
        np.array([10, 255, 255])
    )

    red2 = cv2.inRange(
        hsv,
        np.array([160, 100, 80]),
        np.array([180, 255, 255])
    )

    mask = cv2.bitwise_or(
        red1,
        red2
    )

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    height, width = frame.shape[:2]

    candidates = []

    for contour in contours:

        x, y, w, h = cv2.boundingRect(
            contour
        )

        area = cv2.contourArea(
            contour
        )

        if x < width * 0.75:
            continue

        if w < 60 or w > 240:
            continue

        if h < 12 or h > 60:
            continue

        if area < 500:
            continue

        candidates.append(
            (
                x,
                y,
                w,
                h,
                area
            )
        )

    if not candidates:

        return None

    candidates.sort(
        key=lambda item: item[4],
        reverse=True
    )

    x, y, w, h, area = (
        candidates[0]
    )

    crop = crop_with_padding(
        frame,
        x,
        y,
        w,
        h,
        padding=3
    )

    text = ocr_label(
        crop,
        psm=7
    )

    prices = extract_prices(
        text
    )

    if not prices:

        return None

    sl = prices[0]

    return {
        "sl": sl,
        "text": text,
        "x": x,
        "y": y,
        "w": w,
        "h": h
    }


def find_green_targets(
    frame,
    entry,
    entry_y
):

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    green_lower = np.array(
        [70, 80, 60]
    )

    green_upper = np.array(
        [105, 255, 255]
    )

    mask = cv2.inRange(
        hsv,
        green_lower,
        green_upper
    )

    height, width = frame.shape[:2]

    x1 = int(
        width * 0.80
    )

    x2 = int(
        width * 0.93
    )

    row_counts = (
        mask[:, x1:x2].sum(
            axis=1
        ) / 255
    )

    rows = np.where(
        row_counts > 40
    )[0]

    groups = []

    if len(rows):

        start = rows[0]
        previous = rows[0]

        for row in rows[1:]:

            if row > previous + 1:

                if (
                    8
                    <= previous - start + 1
                    <= 70
                ):

                    groups.append(
                        (
                            start,
                            previous
                        )
                    )

                start = row

            previous = row

        if (
            8
            <= previous - start + 1
            <= 70
        ):

            groups.append(
                (
                    start,
                    previous
                )
            )

    targets = []

    for y1, y2 in groups:

        crop = frame[
            max(0, y1 - 4):
            min(height, y2 + 5),
            x1:x2
        ]

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

        best_prices = []

        for block_size in [
            21,
            31,
            41
        ]:

            threshold = (
                cv2.adaptiveThreshold(
                    gray,
                    255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY,
                    block_size,
                    5
                )
            )

            for psm in [
                6,
                7,
                13
            ]:

                try:

                    text = (
                        pytesseract.image_to_string(
                            threshold,
                            config=f"--psm {psm}"
                        )
                        .upper()
                        .strip()
                    )

                    prices = (
                        extract_prices(
                            text
                        )
                    )

                    for price in prices:

                        best_prices.append(
                            (
                                price,
                                y1,
                                y2,
                                text
                            )
                        )

                except Exception:
                    pass

        for price, y1, y2, text in best_prices:

            # BUY:
            # TP must be above entry on chart.
            #
            # SELL:
            # TP must be below entry.
            #
            # We don't know direction yet,
            # so keep all valid targets here.

            targets.append(
                {
                    "price": price,
                    "y": (y1 + y2) / 2,
                    "text": text
                }
            )

    # Remove duplicate OCR results.
    unique = []

    for target in targets:

        duplicate = False

        for existing in unique:

            if (
                abs(
                    target["price"]
                    -
                    existing["price"]
                )
                < 0.05
                and
                abs(
                    target["y"]
                    -
                    existing["y"]
                )
                < 15
            ):

                duplicate = True
                break

        if not duplicate:

            unique.append(
                target
            )

    return unique


def choose_tp(
    targets,
    entry,
    sl,
    entry_y
):

    if not targets:

        return None

    # BUY:
    # SL below entry price.
    if sl < entry:

        valid = [
            target
            for target in targets
            if target["price"] > entry
            and target["y"] < entry_y
        ]

        if not valid:

            return None

        valid.sort(
            key=lambda target:
                target["price"] - entry
        )

        return valid[0]["price"]

    # SELL:
    # SL above entry price.
    if sl > entry:

        valid = [
            target
            for target in targets
            if target["price"] < entry
            and target["y"] > entry_y
        ]

        if not valid:

            return None

        valid.sort(
            key=lambda target:
                entry - target["price"]
        )

        return valid[0]["price"]

    return None


def detect_signal(frame):

    entry_data = (
        find_yellow_entry(
            frame
        )
    )

    if not entry_data:

        return None

    entry = entry_data[
        "entry"
    ]

    entry_y = (
        entry_data["y"]
        +
        entry_data["h"] / 2
    )

    print(
        "Yellow ENTRY found:",
        entry,
        flush=True
    )

    sl_data = (
        find_red_stop_loss(
            frame
        )
    )

    if not sl_data:

        print(
            "Yellow ENTRY found but S/L not found.",
            flush=True
        )

        return None

    sl = sl_data[
        "sl"
    ]

    print(
        "Red S/L found:",
        sl,
        flush=True
    )

    if sl < entry:

        direction = "BUY"

    elif sl > entry:

        direction = "SELL"

    else:

        return None

    print(
        "Direction:",
        direction,
        flush=True
    )

    targets = (
        find_green_targets(
            frame,
            entry,
            entry_y
        )
    )

    tp = choose_tp(
        targets,
        entry,
        sl,
        entry_y
    )

    if tp is not None:

        print(
            "TP1 found:",
            tp,
            flush=True
        )

    else:

        print(
            "TP1 not detected.",
            flush=True
        )

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "ocr_text": (
            entry_data["text"]
            + " | "
            + sl_data["text"]
        )
    }