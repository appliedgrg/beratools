"""
Provide a full workflow that runs the centerline, canopy and ground footprint tools.

Usage:
    python full_workflow.py [processes=20] [steps_to_run=[check_seed_line,centerline,footprint_abs,footprint_ground]]
"""

import os
import sys
from pathlib import Path

sys.path.append(Path(__file__).resolve().parents[1].as_posix())

import hydra
from beratools.tools.canopy_footprint_absolute import canopy_footprint_abs
from beratools.tools.centerline import centerline
from beratools.tools.check_seed_line import check_seed_line
from beratools.tools.ground_footprint import ground_footprint
from omegaconf import OmegaConf


def print_message(msg):
    print("\n" + "-" * 50)
    print(msg)
    print("-" * 50)


@hydra.main(version_base=None, config_path=".", config_name="config")
def main(cfg):
    print_message("Loaded configuration")
    print(OmegaConf.to_yaml(cfg, resolve=True))

    processes = int(cfg.processes) if cfg.processes else os.cpu_count()
    print(f"Processes: {processes}")

    steps_to_run = set(cfg.steps_to_run) if "steps_to_run" in cfg else set()

    if "check_seed_line" in steps_to_run:
        print_message("Running check_seed_line")
        args = dict(cfg.args_check_seed_line)
        args["processes"] = processes
        check_seed_line(**args)

    if "centerline" in steps_to_run:
        print_message("Running centerline")
        args = dict(cfg.args_centerline)
        args["processes"] = processes
        centerline(**args)

    if "footprint_abs" in steps_to_run:
        print_message("Running footprint abs")
        args = dict(cfg.args_footprint_abs)
        args["processes"] = processes
        canopy_footprint_abs(**args)

    if "footprint_ground" in steps_to_run:
        print_message("Running ground footprint")
        args = dict(cfg.args_footprint_ground)
        args["processes"] = processes
        ground_footprint(**args)

    print_message("Workflow completed successfully!")


if __name__ == "__main__":
    main()
