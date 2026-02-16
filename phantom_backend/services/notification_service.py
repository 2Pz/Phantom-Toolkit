import contextlib
import winsound
from pathlib import Path

# Map abstract event names to filenames
_SOUND_MAP = {
    "save": "save_notification.wav",
    "load": "load_notification.wav",
    "auto_start": "start_auto_save_notification.wav",
    "auto_stop": "stop_auto_save_notification.wav",
}

_ASSETS_DIR = Path(__file__).parent.parent / "assets" / "notifications"


def play(event_name: str):
    """Play a notification sound by event name asynchronously."""
    filename = _SOUND_MAP.get(event_name)
    if not filename:
        return

    filepath = _ASSETS_DIR / filename
    if not filepath.exists():
        return

    def _worker():
        with contextlib.suppress(Exception):
            # SND_FILENAME | SND_ASYNC
            winsound.PlaySound(
                str(filepath), winsound.SND_FILENAME | winsound.SND_ASYNC
            )

    # winsound.PlaySound with SND_ASYNC returns immediately, so we don't strictly need a thread,
    # but wrapping in a thread is safer to avoid blocking the main thread if disk I/O hangs slightly.
    # Actually SND_ASYNC is fire-and-forget.
    with contextlib.suppress(Exception):
        winsound.PlaySound(str(filepath), winsound.SND_FILENAME | winsound.SND_ASYNC)
