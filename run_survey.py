"""兼容入口:`python run_survey.py` 等价于 `thermolit` CLI(需先 pip install -e .)。"""
import sys

from thermolit.cli import main

if __name__ == "__main__":
    sys.exit(main())
