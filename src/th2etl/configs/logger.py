from __future__ import annotations

import logging
import sys
from pathlib import Path

from th2etl.configs.settings import get_settings

# A list of the main modules to create separate log files for
LOGGING_MODULES = [
    "th2etl.scheduler",
    "th2etl.api",
    "th2etl.pipelines",
    "th2etl.storage",
]

def setup_logging():
    """Configures logging to separate files for each main module."""
    settings = get_settings()
    log_format = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # --- Root logger for console output ---
    root_logger = logging.getLogger()
    # Clear any existing handlers to avoid duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    
    # --- File-based logging ---
    if settings.log_dir:
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"Logging to directory: {log_dir}")

        # General log file for all messages
        main_log_file = log_dir / "th2etl.log"
        main_file_handler = logging.FileHandler(main_log_file)
        main_file_handler.setFormatter(formatter)
        root_logger.addHandler(main_file_handler)

        # Create separate log files for each main module
        for module_name in LOGGING_MODULES:
            module_logger = logging.getLogger(module_name)
            log_file = log_dir / f"{module_name.split('.')[-1]}.log"
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            module_logger.addHandler(file_handler)
            module_logger.propagate = False # Prevents messages from going to the root logger's file handler

    # --- Set log levels ---
    default_level = settings.log_level.upper()
    root_logger.setLevel(default_level)

    log_levels_str = settings.log_levels
    if log_levels_str:
        for logger_config in log_levels_str.split(","):
            if ":" in logger_config:
                logger_name, level_name = logger_config.split(":", 1)
                level = logging.getLevelName(level_name.upper())
                if isinstance(level, int):
                    logging.getLogger(logger_name.strip()).setLevel(level)
                else:
                    logging.warning(f"Invalid log level '{level_name}' for logger '{logger_name.strip()}'")
