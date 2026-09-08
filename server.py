import os
import threading

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from storage import load_state


app = FastAPI(title="Million Moves Monitor")

DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "")


def check_token(token):
    if DASHBOARD_TOKEN and token != DASHBOARD_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid dashboard token"
        )


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Million Moves Monitor</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #111;
            color: white;
            text-align: center;
            padding: 20px;
        }

        .box {
            max-width: 500px;
            margin: auto;
            background: #222;
            padding: 25px;
            border-radius: 15px;
        }

        .status {
            font-size: 22px;
            margin: 20px;
        }

        button {
            padding: 12px 20px;
            font-size: 16px;
            border-radius: 8px;
            border: 0;
        }

        #signal {
            margin-top: 20px;
            font-size: 20px;
            line-height: 1.7;
        }
    </style>
</head>

<body>

<div class="box">

    <h1>Million Moves V5</h1>

    <div class="status">
        Monitor: <b id="status">Checking...</b>
    </div>

    <div>
        Signals sent:
        <b id="count">0</b>
    </div>

    <div id="signal">
        Waiting for signal...
    </div>

</div>

<script>

async function updateStatus() {

    try {

        const response = await fetch("/api/status");

        if (!response.ok) {
            document.getElementById("status").innerText = "OFFLINE";
            return;
        }

        const data = await response.json();

        document.getElementById("status").innerText = "ONLINE";

        document.getElementById("count").innerText =
            data.signals_sent || 0;

        if (data.last_signal) {

            document.getElementById("signal").innerText =
                "Last signal: " + data.last_signal;

        }

    } catch (error) {

        document.getElementById("status").innerText = "OFFLINE";

    }
}

updateStatus();

setInterval(updateStatus, 5000);

</script>

</body>
</html>
"""


@app.get("/api/status")
def status(x_dashboard_token: str = Header(default="")):

    check_token(x_dashboard_token)

    state = load_state()

    return {
        "monitor": "running",
        "last_signal": state.get("last_signal"),
        "signals_sent": state.get("signals_sent", 0)
    }


def start_monitor():
    try:
        from monitor import monitor

        monitor()

    except Exception as e:
        print("Monitor thread stopped:", e)


@app.on_event("startup")
def startup_event():

    thread = threading.Thread(
        target=start_monitor,
        daemon=True
    )

    thread.start()