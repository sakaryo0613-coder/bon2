"""PyInstaller の入口（clipper.exe）。中身は clipper.launcher.main。"""
import multiprocessing
import sys

from clipper.launcher import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
