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
from multiprocessing.pool import Pool

import geopandas as gpd
import pandas as pd
from tqdm.auto import tqdm

import beratools.core.constants as bt_const
from beratools.utility.tool_args import CallMode, determine_cpu_core_limit

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
        return bt_const.ParallelMode.MULTIPROCESSING, processes


def execute_multiprocessing(
    in_func,
    in_data,
    app_name,
    processes=0,
    call_mode=CallMode.CLI,
):
    out_result = []
    step = 0
    total_steps = len(in_data)
    mode, processes = parallel_mode(processes)
    verbose = True if call_mode == CallMode.GUI else False

    try:
        print("Multiprocessing mode: {}".format(mode.name), flush=True)

        if mode == bt_const.ParallelMode.MULTIPROCESSING:
            print("Multiprocessing started...", flush=True)
            print("Using {} CPU cores".format(processes), flush=True)

            with Pool(processes) as pool:
                with tqdm(total=total_steps, disable=verbose) as pbar:
                    for result in pool.imap_unordered(in_func, in_data):
                        if result_is_valid(result):
                            out_result.append(result)

                        step += 1
                        if verbose:
                            print_msg(app_name, step, total_steps)
                        else:
                            pbar.update()

            pool.close()
            pool.join()
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
            with con_futures.ProcessPoolExecutor(max_workers=processes) as executor:
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
    except Exception as e:
        print(e)
        return None

    return out_result
