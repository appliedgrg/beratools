"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    Main entry point of BERA Tools.
"""

import sys
from pathlib import Path

if __name__ == "__main__":
    current_file = Path(__file__).resolve()
    btool_dir = current_file.parents[2]
    sys.path.insert(0, btool_dir.as_posix())

from beratools.gui.bt_gui_main import runner

if __name__ == "__main__":
    runner()
