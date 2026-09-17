import os
import time
import threading

import uvicorn


def keep_alive_monitor():

    # Run the YouTube diagnostic once at startup.
    try:
        from youtube_source import test_youtube_access

        print(
            "Running YouTube access diagnostic...",
            flush=True
        )

        test_youtube_access()

    except Exception as e:

        print(
            "YouTube diagnostic crashed:",
            type(e).__name__,
            str(e),
            flush=True
        )

    # Continue running the existing monitor.
    while True:

        try:
            from monitor import monitor

            print(
                "Starting Million Moves monitor...",
                flush=True
            )

            monitor()

            print(
                "Monitor stopped. Restarting in 5 seconds...",
                flush=True
            )

        except Exception as e:

            print(
                "Monitor crashed:",
                type(e).__name__,
                str(e),
                flush=True
            )

        time.sleep(5)


if __name__ == "__main__":

    monitor_thread = threading.Thread(
        target=keep_alive_monitor,
        daemon=True
    )

    monitor_thread.start()

    port = int(
        os.getenv("PORT", "8000")
    )

    print(
        "Starting web server on port",
        port,
        flush=True
    )

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
