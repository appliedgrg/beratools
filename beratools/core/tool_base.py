"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide fundamental utilities for tools.
"""

import concurrent.futures as con_futures
import warnings
import multiprocessing
from beratools.core.logger import Logger
import logging
import logging.handlers
from multiprocessing.pool import Pool
import psutil

import geopandas as gpd
import pandas as pd
from tqdm.auto import tqdm

import beratools.core.constants as bt_const
from beratools.utility.tool_args import CallMode, determine_cpu_core_limit
from beratools.gui.bt_data import BTData

bt = BTData()
warnings.simplefilter(action="ignore", category=FutureWarning)


class ToolBase(object):
    """Base class for tools."""

    def __init__(self):
        pass

    def execute_multiprocessing(self):
        pass


def result_is_valid(result):
    if type(result) is list or type(result) is tuple:
        if len(result) > 0:
            return True
    elif (
        type(result) is pd.DataFrame
        or type(result) is gpd.GeoDataFrame
        or type(result) is pd.Series
        or type(result) is gpd.GeoSeries
    ):
        if not result.empty:
            return True
    elif result:
        return True

    return False


def print_msg(app_name, step, total_steps):
    print(f' "PROGRESS_LABEL {app_name} {step} of {total_steps}" ', flush=True)
    print(f" %{step / total_steps * 100} ", flush=True)


def parallel_mode(processes):
    if processes <= 0:
        processes = determine_cpu_core_limit()

    if processes == 1:
        return bt_const.ParallelMode.SEQUENTIAL, processes
    else:
        return bt_const.ParallelMode.MULTIPROCESSING, min(processes,determine_cpu_core_limit())

def listener_process(queue, logfile,logger_name=None):
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler = logging.handlers.RotatingFileHandler(
        logfile,
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",)

    handler.setFormatter(formatter)
    root.addHandler(handler)
    try:
        while True:
            try:
                record = queue.get()
                if record is None:
                    break
                if logger_name is not None and record.name == logger_name:
                    root.handle(record)
                elif record.levelno >= logging.WARNING:
                    root.handle(record)
                else:
                    continue
            except Exception:
                logging.exception("Listener process logging failure")
    finally:
        handler.flush()
        handler.close()

def configure_worker_logging(queue):
    """
    Configure worker process logger.
    """
    Logger.set_queue(queue)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.propagate = False
    root.addHandler(
        logging.handlers.QueueHandler(queue)
    )


def execute_multiprocessing(
    in_func,
    in_data,
    app_name,
    processes=0,
    call_mode=CallMode.CLI,
    logger_name=None,
):
    out_result = []
    step = 0
    total_steps = len(in_data)
    mode, processes = parallel_mode(processes)
    verbose = True if call_mode == CallMode.GUI else False
    TOTAL_RAM_GB = psutil.virtual_memory().total / 1024 ** 3
    MAX_Memory_used = 0.95*TOTAL_RAM_GB
    MAX_WORKERS = determine_cpu_core_limit()
    MAX_RAM_PER_WORKER_GB = MAX_Memory_used / MAX_WORKERS
    TARGET_UTILIZATION = 0.85
    workers = int(TOTAL_RAM_GB * TARGET_UTILIZATION / MAX_RAM_PER_WORKER_GB)
    processes = min(processes, workers)
    try:
        print("Multiprocessing mode: {}".format(mode.name), flush=True)

        if mode == bt_const.ParallelMode.MULTIPROCESSING:
            print("Multiprocessing started...", flush=True)
            print("Using {} CPU cores".format(processes), flush=True)
            log_file = bt.get_logger_file_name(logger_name)
            log_queue = multiprocessing.Queue(maxsize=50000)
            listener = multiprocessing.Process(target=listener_process, args=(log_queue, log_file,logger_name),daemon=False, )
            listener.start()
            try:
                with Pool(processes,maxtasksperchild=100,initializer=configure_worker_logging,
                          initargs=(log_queue,)) as pool:
                    with tqdm(total=total_steps, disable=verbose) as pbar:
                        for result in pool.imap_unordered(in_func, in_data):
                            if result_is_valid(result):
                                out_result.append(result)

                            step += 1
                            if verbose:
                                print_msg(app_name, step, total_steps)
                            else:
                                pbar.update()
            finally:
                log_queue.put(None)
                listener.join(timeout=10)
        elif mode == bt_const.ParallelMode.SEQUENTIAL:
            print("Sequential processing started...", flush=True)
            with tqdm(total=total_steps, disable=verbose) as pbar:
                for line in in_data:
                    result_item = in_func(line)
                    if result_is_valid(result_item):
                        out_result.append(result_item)

                    step += 1
                    if verbose:
                        print_msg(app_name, step, total_steps)
                    else:
                        pbar.update()
        elif mode == bt_const.ParallelMode.CONCURRENT:
            print("Concurrent processing started...", flush=True)
            print("Using {} CPU cores".format(processes), flush=True)
            log_file = bt.get_logger_file_name(logger_name)
            log_queue = multiprocessing.Queue(maxsize=50000)
            listener = multiprocessing.Process(target=listener_process, args=(log_queue, log_file,),daemon=False, )
            listener.start()
            try:
                with con_futures.ProcessPoolExecutor(
                        max_workers=processes,
                        max_tasks_per_child=100,
                        initializer=configure_worker_logging,
                        initargs=(log_queue,),
                ) as executor:
                    futures = [executor.submit(in_func, line) for line in in_data]
                    with tqdm(total=total_steps, disable=verbose) as pbar:
                        for future in con_futures.as_completed(futures):
                            result_item = future.result()
                            if result_is_valid(result_item):
                                out_result.append(result_item)

                            step += 1
                            if verbose:
                                print_msg(app_name, step, total_steps)
                            else:
                                pbar.update()
            finally:
                log_queue.put(None)
                listener.join(timeout=10)
    except Exception as e:
        print(e)
        return None

    return out_result
