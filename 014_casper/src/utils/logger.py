"""Logging configuration for Casper Trading Bot."""

import logging
import os
from datetime import datetime


def setup_logger(name: str = "casper", level: str = "INFO") -> logging.Logger:
    """Configure and return a logger with console + file handlers."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)-12s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler (daily rotation by name)
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "app")
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(
        os.path.join(log_dir, f"casper_{today}.log"), encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
