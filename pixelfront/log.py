"""Per-run log files.

Every run writes logs/<YYYYMMDD_HHMMSS>.log (year first, so files sort chronologically)
next to the executable, or in the project root when run from source. Modules log through
logging.getLogger(__name__). Set PIXELFRONT_DEBUG=1 for DEBUG detail (individual orders).
"""
import logging
import os
import platform
import sys
import time

KEEP_LOGS = 50   # older log files are pruned on startup

log = logging.getLogger("pixelfront")


def log_dir():
    if getattr(sys, "frozen", False):          # PyInstaller build: beside Pixelfront.exe
        base = os.path.dirname(sys.executable)
    else:                                      # from source: the project root
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "logs")


def setup():
    """Start this run's log file. Returns its path (or None if logging to disk failed)."""
    level = logging.DEBUG if os.environ.get("PIXELFRONT_DEBUG") else logging.INFO
    root = logging.getLogger("pixelfront")
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    path = None
    try:
        folder = log_dir()
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, time.strftime("%Y%m%d_%H%M%S") + ".log")
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(fmt)
        root.addHandler(handler)
        _prune(folder)
    except OSError as exc:   # read-only folder etc.: carry on without a log file
        print(f"Pixelfront: could not create a log file ({exc})", file=sys.stderr)
    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(fmt)
        root.addHandler(console)
    sys.excepthook = _log_crash
    return path


def startup_info(version):
    import pygame
    log.info("Pixelfront %s starting", version)
    log.info("Python %s on %s; pygame-ce %s (SDL %s)", platform.python_version(), platform.platform(),
             pygame.version.ver, ".".join(map(str, pygame.get_sdl_version())))


def _prune(folder):
    logs = sorted(f for f in os.listdir(folder) if f.endswith(".log"))
    for old in logs[:-KEEP_LOGS]:
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass


def _log_crash(exc_type, exc, tb):
    log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)
