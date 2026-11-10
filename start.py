#!/usr/bin/env python3
"""DTE recorder entry point.

    ./start.py          run on the Raspberry Pi
    ./start.py --sim    run the simulator in a terminal (or DTE_SIM=1)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dte.main import main  # noqa: E402

if __name__ == "__main__":
    main()
