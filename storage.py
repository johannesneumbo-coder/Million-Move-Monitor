import json
import os
from pathlib import Path
from threading import RLock


# ============================================================
# MILLION MOVES - SIGNAL STORAGE
#
# Remembers:
# 1. Every entry successfully sent.
# 2. The last SL successfully sent for each entry.
# 3. Total successful WhatsApp messages.
#
# Existing function names are preserved.
# ============================================================


STATE_FILE = os.getenv(
    "STATE_FILE",
    "state.json"
)

_lock = RLock()


# ============================================================
# DEFAULT STATE
# ============================================================

def default_state():

    return {
        "last_signal": None,
        "signals_sent": 0,
        "sent_entries": {},
        "stop_losses": {}
    }


# ============================================================
# READ STATE - INTERNAL
# ============================================================

def _read_state():

    path = Path(STATE_FILE)

    if not path.exists():
        return default_state()

    try:

        with path.open(
            "r",
            encoding="utf-8"
        ) as file:

            state = json.load(file)

        if not isinstance(state, dict):
            return default_state()

        defaults = default_state()

        for key, value in defaults.items():

            if key not in state:
                state[key] = value

        if not isinstance(
            state.get("sent_entries"),
            dict
        ):

            state["sent_entries"] = {}

        if not isinstance(
            state.get("stop_losses"),
            dict
        ):

            state["stop_losses"] = {}

        return state

    except Exception as error:

        print(
            "STORAGE READ ERROR:",
            type(error).__name__,
            str(error),
            flush=True
        )

        return default_state()


# ============================================================
# WRITE STATE - INTERNAL
# ============================================================

def _write_state(state):

    path = Path(STATE_FILE)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_path = Path(
        str(path) + ".tmp"
    )

    with temp_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            state,
            file,
            indent=2
        )

        file.flush()

        os.fsync(
            file.fileno()
        )

    os.replace(
        str(temp_path),
        str(path)
    )


# ============================================================
# EXISTING PUBLIC FUNCTIONS
# ============================================================

def load_state():

    with _lock:

        return _read_state()


def save_state(state):

    with _lock:

        _write_state(state)


def get_last_signal():

    with _lock:

        state = _read_state()

        return state.get(
            "last_signal"
        )


def signal_already_sent(signal_key):

    if not signal_key:
        return False

    with _lock:

        state = _read_state()

        if signal_key in state["sent_entries"]:
            return True

        # Compatibility with the old state.json.
        return (
            state.get("last_signal")
            == signal_key
        )


def set_last_signal(signal_key):

    if not signal_key:
        return

    with _lock:

        state = _read_state()

        if signal_key in state["sent_entries"]:
            return

        state["last_signal"] = signal_key

        state["sent_entries"][signal_key] = True

        state["signals_sent"] = (
            state.get("signals_sent", 0) + 1
        )

        _write_state(state)


# ============================================================
# STOP LOSS PRICE NORMALIZATION
# ============================================================

def normalize_sl(sl):

    if sl is None:
        return None

    try:

        return f"{float(sl):.2f}"

    except (TypeError, ValueError):

        return None


# ============================================================
# GET LAST SENT STOP LOSS
# ============================================================

def get_last_sent_sl(signal_key):

    if not signal_key:
        return None

    with _lock:

        state = _read_state()

        return state["stop_losses"].get(
            signal_key
        )


# ============================================================
# CHECK IF STOP LOSS UPDATE IS NEEDED
# ============================================================

def sl_update_needed(signal_key, sl):

    if not signal_key:
        return False

    normalized_sl = normalize_sl(sl)

    if normalized_sl is None:
        return False

    with _lock:

        state = _read_state()

        # Never send an SL update for an entry
        # that has not been recorded as sent.

        entry_sent = (
            signal_key in state["sent_entries"]
            or state.get("last_signal") == signal_key
        )

        if not entry_sent:
            return False

        previous_sl = state["stop_losses"].get(
            signal_key
        )

        return previous_sl != normalized_sl


# ============================================================
# RECORD SUCCESSFULLY SENT STOP LOSS
# ============================================================

def set_last_sent_sl(signal_key, sl):

    if not signal_key:
        return False

    normalized_sl = normalize_sl(sl)

    if normalized_sl is None:
        return False

    with _lock:

        state = _read_state()

        entry_sent = (
            signal_key in state["sent_entries"]
            or state.get("last_signal") == signal_key
        )

        if not entry_sent:
            return False

        previous_sl = state["stop_losses"].get(
            signal_key
        )

        if previous_sl == normalized_sl:
            return False

        state["stop_losses"][
            signal_key
        ] = normalized_sl

        state["signals_sent"] = (
            state.get("signals_sent", 0) + 1
        )

        _write_state(state)

        return True


# ============================================================
# END
# ============================================================