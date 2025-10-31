"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide logger functions.
"""

import logging
import logging.handlers
import sys

from beratools.gui.bt_data import BTData

bt = BTData()


class NoParsingFilter(logging.Filter):
    """
    Filter to exclude log messages that start with "parsing".

    This is useful to avoid cluttering the log with parsing-related messages.
    """

    def filter(self, record):
        return not record.getMessage().startswith("parsing")


class Logger(object):
    """
    Logger class to handle logging in the BERA Tools application.

    This class sets up a logger that outputs to both the console and a file.
    It allows for different logging levels for console and file outputs.
    It also provides a method to print messages directly to the logger.
    """

    def __init__(self, name, console_level=logging.INFO, file_level=logging.INFO):
        self.logger = logging.getLogger(name)
        self.name = name
        self.console_level = console_level
        self.file_level = file_level

        self.setup_logger()

    def get_logger(self):
        return self.logger

    def print(self, msg, flush=True):
        """
        Re-define print in logging.

        Args:
        msg :
        flush :

        """
        self.logger.info(msg)
        if flush:
            for handler in self.logger.handlers:
                handler.flush()

    def setup_logger(self):
        # Change root logger level from WARNING (default) to NOTSET
        # in order for all messages to be delegated.
        logging.getLogger().setLevel(logging.NOTSET)
        log_file = bt.get_logger_file_name(self.name)

        # Add stdout handler, with level INFO
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.console_level)
        formatter = logging.Formatter("%(message)s")
        console_handler.setFormatter(formatter)
        logging.getLogger().addHandler(console_handler)

        # Add file rotating handler, 5MB size limit, 5 backups
        rotating_handler = logging.handlers.RotatingFileHandler(
            filename=log_file, maxBytes=5 * 1000 * 1000, backupCount=5
        )

        rotating_handler.setLevel(self.file_level)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        rotating_handler.setFormatter(formatter)
        logging.getLogger().addHandler(rotating_handler)
        logging.getLogger().addFilter(NoParsingFilter())
