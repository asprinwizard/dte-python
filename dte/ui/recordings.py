"""Recorded files: listing and short labels for the LCD.

dvgrab-dte names files ``<prefix>-DD-MM-YYYY_HH-MM-SS[-N].<ext>``. Seconds
don't fit in the normal labels, so files that share a minute with another
file are shown with seconds instead.
"""

import datetime
import re
from pathlib import Path

EXTENSIONS = (".dv", ".m2t", ".avi")
_STAMP_RE = re.compile(
    r"(\d{2})-(\d{2})-(\d{4})_(\d{2})-(\d{2})-(\d{2})(?:-(\d+))?\.(?:dv|m2t|avi)$", re.IGNORECASE)


class Recording(object):
    def __init__(self, path):
        self.path = Path(path)
        self.stamp = None
        self.copy = 1
        match = _STAMP_RE.search(self.path.name)
        if match:
            day, month, year, hour, minute, second, copy = match.groups()
            try:
                self.stamp = datetime.datetime(int(year), int(month), int(day),
                                               int(hour), int(minute), int(second))
                self.copy = int(copy) if copy else 1
            except ValueError:
                self.stamp = None

    @property
    def name(self):
        return self.path.name

    def sort_key(self):
        if self.stamp is not None:
            return (self.stamp, self.copy)
        try:
            return (datetime.datetime.fromtimestamp(self.path.stat().st_mtime), 0)
        except OSError:
            return (datetime.datetime.min, 0)


def list_recordings(videos_dir):
    """Recordings in ``videos_dir``, newest first."""
    directory = Path(videos_dir)
    if not directory.is_dir():
        return []
    files = [Recording(p) for p in directory.iterdir()
             if p.is_file() and p.suffix.lower() in EXTENSIONS]
    files.sort(key=lambda r: r.sort_key(), reverse=True)
    return files


def _minute(rec):
    return rec.stamp.replace(second=0) if rec.stamp else None


def labels(recordings, width):
    """Return one label per recording, fitted to ``width`` characters.

    Normal:          list ``DD-MM-YYYY HH:MM`` (16), playback ``DD-MM HH:MM`` (11)
    Shared minute:   ``DD-MM HH:MM:SS`` (+ `` N`` for a same-second copy)
    No timestamp:    the end of the file name
    """
    counts = {}
    for rec in recordings:
        key = _minute(rec)
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
    result = []
    for rec in recordings:
        if rec.stamp is None:
            result.append(rec.name[-width:])
            continue
        if counts.get(_minute(rec), 0) > 1:
            text = rec.stamp.strftime("%d-%m %H:%M:%S")
            if rec.copy > 1:
                text += " {}".format(rec.copy)
        elif width >= 16:
            text = rec.stamp.strftime("%d-%m-%Y %H:%M")
        else:
            text = rec.stamp.strftime("%d-%m %H:%M")
        result.append(text[:width])
    return result
