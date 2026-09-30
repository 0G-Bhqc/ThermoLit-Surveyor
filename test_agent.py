"""兼容入口:`python test_agent.py` 等价于运行 tests/ 全部测试。

推荐用法(需先 `pip install -e ".[dev]"`):
    python -m unittest discover -s tests -v
"""
import sys
import unittest

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
