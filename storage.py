import json
import os
from threading import Lock

STATE_FILE = os.getenv("STATE_FILE", "state.json")

_lock = Lock()


def load_state():
    with _lock:
        if not os.path.exists(STATE_FILE):
            return {
                "last_signal": None,
                "signals_sent": 0
            }

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "last_signal": None,
                "signals_sent": 0
            }


def save_state(state):
    with _lock:
        temp_file = STATE_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        os.replace(temp_file, STATE_FILE)


def get_last_signal():
    state = load_state()
    return state.get("last_signal")


def set_last_signal(signal_key):
    state = load_state()
    state["last_signal"] = signal_key
    state["signals_sent"] = state.get("signals_sent", 0) + 1
    save_state(state)


def signal_already_sent(signal_key):
    return get_last_signal() == signal_key