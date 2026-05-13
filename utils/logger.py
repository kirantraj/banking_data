"""
Structured console logger shared across all modules.
Uses a single handler per logger to avoid duplicate lines on re-import.
"""
import logging
import sys


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        # stderr keeps logs out of the MCP stdio channel (stdout is reserved
        # for JSON-RPC in the server subprocess)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger
