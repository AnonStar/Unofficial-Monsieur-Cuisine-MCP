import logging

from .config import LOG_LEVEL


def setup_logging(level: int | str | None = None) -> None:
    """Configure root logging for the whole application.

    Called once from each entry point (server, interactive login). `level`
    overrides the MC_LOG_LEVEL env var / config.LOG_LEVEL default - pass
    logging.DEBUG (or --debug on the CLIs) to log individual events and the
    values passed/received at each step, not just high-level progress.
    """
    logging.basicConfig(
        level=level if level is not None else LOG_LEVEL,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
