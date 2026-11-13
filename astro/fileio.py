"""Small file helpers shared by the NASA caches, archives and datasets."""
import datetime as dt
import os
import time
from pathlib import Path
from typing import Optional

STALE_TEMP_SECONDS = 60                    # leftovers of a killed process older than this are removed after a good write


# ---------------------------------------------------------------------------------------------- time
def local_now() -> dt.datetime:
    """The current local time WITH its UTC offset, so a stored time stays correct if the computer's timezone changes."""
    return dt.datetime.now().astimezone()


def as_aware(value: dt.datetime) -> dt.datetime:
    """A datetime that knows its offset. A naive one (older files, simple callers) is taken to be local time."""
    return value if value.tzinfo is not None else value.astimezone()


def parse_time(text) -> Optional[dt.datetime]:
    """Parse a stored ISO time (naive or with an offset) into an aware datetime; None if it is not a valid time."""
    try:
        return as_aware(dt.datetime.fromisoformat(text))
    except (TypeError, ValueError):
        return None


def local_date(value: dt.datetime) -> dt.date:
    """The calendar date of a moment in the computer's LOCAL timezone (not the timezone the moment was stored in)."""
    return as_aware(value).astimezone().date()


def local_text(value, tz: Optional[dt.tzinfo] = None) -> Optional[str]:
    """'YYYY-MM-DD HH:MM' in local time (or in ``tz``) for a stored ISO time or a datetime; None if unusable."""
    when = parse_time(value) if isinstance(value, str) else (as_aware(value) if isinstance(value, dt.datetime) else None)
    return when.astimezone(tz).strftime("%Y-%m-%d %H:%M") if when else None


def atomic_write_text(path, text: str, encoding: str = "utf-8") -> None:
    """Write a text file so that an interruption can never leave it half-written.

    The text goes to a temporary file in the same folder, is flushed to disk, and then replaces the target in a single
    step (``os.replace``, atomic on Windows and POSIX). Until that last step the previous file is untouched, so a crash,
    a power cut or a killed process leaves either the old valid file or the new valid file, never a truncated one. If
    anything fails, the temporary file is removed and the exception propagates. A process killed mid-write can leave its
    temporary file behind: it is never read as data, and a later successful write removes such leftovers."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    _remove_stale_temp_files(target)


def _remove_stale_temp_files(target: Path) -> None:
    now = time.time()
    for leftover in target.parent.glob(f".{target.name}.*.tmp"):
        try:
            if now - leftover.stat().st_mtime > STALE_TEMP_SECONDS:
                leftover.unlink()
        except OSError:
            pass
