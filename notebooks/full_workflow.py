"""
Provide a full workflow that runs the centerline, canopy and ground footprint tools.

usage:n
    python full_workflow.py [parallel_mode=5] [processes=20]

    PARALLEL_MODE: MULTIPROCESSING = 2
                   SLURM = 5
"""

import os
import sys
from pathlib import Path

sys.path.append(Path(__file__).resolve().parents[1].as_posix())

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from beratools.core.algo_footprint_rel import line_footprint_rel
from beratools.core.algo_split_with_lines import split_with_lines
from beratools.tools.centerline import centerline
from beratools.tools.line_footprint_absolute import line_footprint_abs
from beratools.tools.line_footprint_fixed import line_footprint_fixed


def print_message(msg):
    print("\n" + "-" * 50)
    print(msg)
    print("-" * 50)

def main():
    script_dir = Path(__file__).parent.resolve()

    # Load Hydra config from the same directory as the script
    with initialize_config_dir(config_dir=str(script_dir), job_name="full_workflow"):
        cfg = compose(config_name="config.yaml")

    print_message("Loaded configuration")
    print(OmegaConf.to_yaml(cfg, resolve=True))

    parallel_mode = int(cfg.parallel_mode)
    processes = int(cfg.processes) if cfg.processes else os.cpu_count()
    print(f"Parallel mode: {parallel_mode}, Processes: {processes}")

    steps_to_run = set(cfg.steps_to_run) if "steps_to_run" in cfg else set()

    if "centerline" in steps_to_run:
        print_message("Running centerline")
        args = dict(cfg.args_centerline)
        args["processes"] = processes
        args["parallel_mode"] = parallel_mode
        centerline(**args)

    if "footprint_abs" in steps_to_run:
        print_message("Running footprint abs")
        args = dict(cfg.args_footprint_abs)
        args["processes"] = processes
        args["parallel_mode"] = parallel_mode
        line_footprint_abs(**args)

    if "footprint_rel" in steps_to_run:
        print_message("Running footprint rel")
        args = dict(cfg.args_footprint_rel)
        args["processes"] = processes
        args["parallel_mode"] = parallel_mode
        line_footprint_rel(**args)

    if "footprint_fixed" in steps_to_run:
        print_message("Running footprint fixed")
        args = dict(cfg.args_footprint_fixed)
        args["processes"] = processes
        args["parallel_mode"] = parallel_mode
        line_footprint_fixed(**args)

    if "split_lines" in steps_to_run:
        print_message("Running split lines")
        args = dict(cfg.args_split_lines)
        split_with_lines(**args)

    if "footprint_inter" in steps_to_run:
        print_message("Running footprint intersection")
        args = dict(cfg.args_footprint_inter)
        args["processes"] = processes
        args["parallel_mode"] = parallel_mode
        line_footprint_fixed(**args)  # Assuming same function as "fixed"

    print_message("Workflow completed successfully!")

if __name__ == "__main__":
    main()
