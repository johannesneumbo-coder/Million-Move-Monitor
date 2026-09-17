import os
import json
import subprocess
import shutil


YOUTUBE_URL = os.getenv(
    "YOUTUBE_URL",
    "https://www.youtube.com/watch?v=-ps7V40GrA4"
)


def test_youtube_access():

    print(
        "========== YOUTUBE ACCESS TEST ==========",
        flush=True
    )

    print(
        "Video URL:",
        YOUTUBE_URL,
        flush=True
    )

    if shutil.which("yt-dlp") is None:

        print(
            "RESULT: yt-dlp is not installed.",
            flush=True
        )

        print(
            "Install yt-dlp before running this test.",
            flush=True
        )

        return False

    command = [
        "yt-dlp",
        "--no-playlist",
        "--no-download",
        "--dump-single-json",
        "--socket-timeout",
        "15",
        "--retries",
        "1",
        YOUTUBE_URL
    ]

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=90
        )

        if result.returncode != 0:

            error = result.stderr.strip()

            print(
                "RESULT: ACCESS FAILED",
                flush=True
            )

            if (
                "sign in to confirm" in error.lower()
                or "not a bot" in error.lower()
            ):

                print(
                    "REASON: YouTube bot verification.",
                    flush=True
                )

            else:

                print(
                    "ERROR:",
                    error[-1500:],
                    flush=True
                )

            return False

        data = json.loads(result.stdout)

        formats = data.get("formats") or []

        video_formats = [
            item
            for item in formats
            if item.get("vcodec") not in (None, "none")
            and item.get("url")
        ]

        print(
            "VIDEO TITLE:",
            data.get("title"),
            flush=True
        )

        print(
            "LIVE STATUS:",
            data.get("live_status"),
            flush=True
        )

        print(
            "VIDEO FORMATS:",
            len(video_formats),
            flush=True
        )

        if not video_formats:

            print(
                "RESULT: No accessible video formats.",
                flush=True
            )

            return False

        print(
            "RESULT: Video metadata and stream URLs accessible.",
            flush=True
        )

        print(
            "NOTE: Actual video-frame playback has not been tested.",
            flush=True
        )

        return True

    except subprocess.TimeoutExpired:

        print(
            "RESULT: Test timed out.",
            flush=True
        )

        return False

    except Exception as error:

        print(
            "RESULT: Diagnostic error:",
            type(error).__name__,
            str(error),
            flush=True
        )

        return False


if __name__ == "__main__":
    test_youtube_access()
