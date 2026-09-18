#!/usr/bin/env python3
"""Synchronizes BigQuery SQL from demo/sql/*.sql into the main HTML presentation deck (index.html)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD_DECK = os.path.join(ROOT, "build_deck.py")

if __name__ == "__main__":
  sys.exit(subprocess.call([sys.executable, BUILD_DECK]))
