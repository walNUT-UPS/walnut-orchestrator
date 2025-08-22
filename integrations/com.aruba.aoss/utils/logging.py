import logging
import os

INTEGRATION_PREFIX = "com.aruba.aoss"


def get_logger(name: str) -> logging.Logger:
    """
    Create a logger with integration-prefixed name and level from env LOG_LEVEL.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(f"{INTEGRATION_PREFIX}.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter(
            fmt=f"{INTEGRATION_PREFIX} %(levelname)s %(name)s: %(message)s"
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

