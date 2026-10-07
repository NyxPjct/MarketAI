from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from backend.services.settings import logs_dir


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("marketai")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    path = logs_dir() / "marketai.log"
    handler = RotatingFileHandler(path, maxBytes=1_500_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
