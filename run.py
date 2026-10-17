#!/usr/bin/python3
"""Launch File Collector from its source directory."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from file_collector.app import main

main()
