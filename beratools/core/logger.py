"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    This module provides logger configuration and convenience functions
    for BERA Tools.

    Each named logger can write to:

    1. A log file using a detailed timestamped format.
    2. The console using a concise message-only format.

    The module also adds two convenience methods to each configured logger:

        logger.file_only(...)
        logger.debug_file_only(...)

    These methods bypass console handlers and write directly to the
    logger's file handler.
"""

import logging
import logging.handlers
import sys
from typing import Optional

from beratools.gui.bt_data import BTData

bt = BTData()


class NoParsingFilter(logging.Filter):
    """
    Exclude messages beginning with the word ``parsing``.

    This reduces console and file noise from repetitive parsing messages.
    The comparison is case-sensitive to retain the behavior of the
    original implementation.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Return False for messages beginning with ``parsing``.

        Parameters
        ----------
        record : logging.LogRecord
            Logging record being evaluated.

        Returns
        -------
        bool
            True when the record should be logged.
            False when the record should be discarded.
        """
        return not record.getMessage().startswith("parsing")


class Logger:
    """
    Configure a named BERA Tools logger.

    The logger uses two handlers:

    * File handler:
      Stores timestamped messages at ``file_level`` or higher.

    * Console handler:
      Displays concise messages at ``console_level`` or higher.

    Each logger is configured only once. Creating another ``Logger``
    instance with the same name reuses the existing handlers.

    Parameters
    ----------
    logger_name : str
        Name of the logger.

    file_level : int, default logging.INFO
        Minimum logging level written to the log file.

    console_level : int, default logging.INFO
        Minimum logging level written to the console.
    """

    def __init__(
        self,
        logger_name: str,
        file_level: int = logging.INFO,
        console_level: int = logging.INFO,

    ) -> None:
        if not logger_name:
            raise ValueError("logger_name must be a non-empty string")

        self.logger_name = logger_name
        self.file_level = file_level
        self.console_level = console_level

        self.logger = logging.getLogger(logger_name)

        # The logger must allow records required by either handler.
        # Each handler then applies its own threshold.
        self.logger.setLevel(
            min(file_level, console_level)
        )

        # Prevent messages from being repeated by root logger handlers.
        self.logger.propagate = False

        self._configure_logger()

    def _configure_logger(self) -> None:
        """
        Add file and console handlers when the logger has not yet
        been configured.

        This prevents duplicate messages when the same logger is requested
        multiple times within one process.
        """
        if self.logger.handlers:
            return

        detailed_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        console_formatter = logging.Formatter(
            "%(message)s"
        )

        log_file = bt.get_logger_file_name(
            self.logger_name
        )

        # Use a rotating log file to prevent an unrestricted file-size
        # increase during large multiprocessing jobs.
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )

        file_handler.setLevel(self.file_level)
        file_handler.setFormatter(detailed_formatter)

        console_handler = logging.StreamHandler(
            sys.stdout
        )

        console_handler.setLevel(self.console_level)
        console_handler.setFormatter(console_formatter)

        # Apply the filter at logger level so it affects every handler.
        self.logger.addFilter(NoParsingFilter())

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def get_logger(self) -> logging.Logger:
        """
        Return the configured logger.

        Two convenience methods are attached to the logger:

        ``logger.file_only(message, *args, level=logging.INFO)``
            Write only to file handlers.

        ``logger.debug_file_only(message, *args)``
            Write a DEBUG message only to file handlers.

        Returns
        -------
        logging.Logger
            Configured logger instance.
        """
        logger_name = self.logger.name

        def file_only_bound(
            message,
            *args,
            level=logging.INFO,
        ) -> None:
            Logger.file_only(
                message,
                *args,
                level=level,
                logger_name=logger_name,
            )

        def debug_file_only_bound(
            message,
            *args,
        ) -> None:
            Logger.debug_file_only(
                message,
                *args,
                logger_name=logger_name,
            )

        # Retain the existing interface used throughout BERA Tools.
        self.logger.file_only = file_only_bound
        self.logger.debug_file_only = debug_file_only_bound

        return self.logger

    def print(
        self,
        message,
        flush: bool = True,
    ) -> None:
        """
        Log a message at INFO level.

        This method provides compatibility with code that previously
        used ``print()`` for progress or status messages.

        Parameters
        ----------
        message : object
            Message or object to log.

        flush : bool, default True
            Flush all configured handlers after logging.
        """
        self.logger.info(message)

        if flush:
            self.flush()

    def flush(self) -> None:
        """
        Flush all handlers associated with this logger.

        Flushing should normally be used only for important progress
        messages, shutdown handling, or debugging. Flushing every log
        record can significantly reduce performance.
        """
        for handler in self.logger.handlers:
            try:
                handler.flush()
            except Exception:
                continue

        try:
            sys.stdout.flush()
        except Exception:
            pass

    @staticmethod
    def debug_file_only(
        message,
        *args,
        logger_name: Optional[str] = None,
    ) -> None:
        """
        Write a DEBUG message only to file handlers.

        The message is not sent to console handlers.

        Parameters
        ----------
        message : object
            Log message or formatting template.

        *args
            Values used with standard logging percent formatting.

        logger_name : str
            Name of an existing configured logger.
        """
        Logger.file_only(
            message,
            *args,
            level=logging.DEBUG,
            logger_name=logger_name,
        )

    @staticmethod
    def file_only(
        message,
        *args,
        level: int = logging.INFO,
        logger_name: Optional[str] = None,
    ) -> None:
        """
        Write a message directly to the logger's file handlers.

        Console handlers are intentionally bypassed.

        Unlike a regular logger call, this method sends the record directly
        to each file handler. This allows a DEBUG file-only record to be
        written even when the logger's effective level is INFO or WARNING,
        provided the file handler accepts that level.

        Parameters
        ----------
        message : object
            Log message or formatting template.

        *args
            Values used with standard logging percent formatting.

        level : int, default logging.INFO
            Logging level associated with the record.

        logger_name : str
            Name of an existing configured logger.

        Notes
        -----
        This method does not flush the file handler after every message.
        Operating-system and Python buffering improve performance during
        large multiprocessing jobs. Use ``Logger.flush()`` when an
        immediate flush is required.
        """
        if not logger_name:
            raise ValueError(
                "logger_name must be provided for file-only logging"
            )

        target_logger = logging.getLogger(
            logger_name
        )

        if not target_logger.handlers:
            # The target logger has not been configured. Use the regular
            # logging mechanism as a fallback.
            target_logger.log(
                level,
                message,
                *args,
            )
            return

        record = target_logger.makeRecord(
            name=target_logger.name,
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=args,
            exc_info=None,
        )

        # Apply logger-level filters because directly invoking handlers
        # bypasses Logger.handle(), where those filters normally run.
        if not target_logger.filter(record):
            return

        file_handler_found = False

        for handler in target_logger.handlers:
            if not isinstance(
                handler,
                logging.FileHandler,
            ):
                continue

            file_handler_found = True

            # Calling handler.handle() directly bypasses the handler's
            # normal level check, so apply that check explicitly.
            if level < handler.level:
                continue

            handler.handle(record)

        if not file_handler_found:
            # No file handler exists. Fall back to normal logging rather
            # than silently dropping the message.
            target_logger.log(
                level,
                message,
                *args,
            )