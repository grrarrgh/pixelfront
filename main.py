import logging

from pixelfront import __version__, log as runlog

if __name__ == "__main__":
    path = runlog.setup()
    runlog.startup_info(__version__)
    log = logging.getLogger("pixelfront")
    log.info("Logging to %s", path)
    from pixelfront.app import App
    try:
        App().run()
    except Exception:
        log.exception("Crashed")
        raise
    log.info("Exited normally")
