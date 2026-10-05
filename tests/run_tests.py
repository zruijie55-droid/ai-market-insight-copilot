"""测试运行入口：python tests/run_tests.py

实际执行全部 test_*.py，并打印通过/失败汇总（不虚构结果）。
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

loader = unittest.TestLoader()
suite = loader.discover(str(HERE), pattern="test_*.py")
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
