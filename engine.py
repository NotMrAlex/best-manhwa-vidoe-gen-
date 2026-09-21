#!/usr/bin/env python3
"""Dank Engine Studio - backward-compatible entry point.

`python engine.py` behaves exactly like the legacy monolith; all logic now
lives in the engine/ package (see engine/cli.py).
"""

from engine.cli import main

if __name__ == "__main__":
    main()
