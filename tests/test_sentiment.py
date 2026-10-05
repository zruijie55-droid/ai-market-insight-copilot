"""中文情感词典测试：正向/负向/中性判定与净分。"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import sentiment as S


class TestSentiment(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(S.label("轻便小巧，续航耐用，性价比高"), "positive")

    def test_negative(self):
        self.assertEqual(S.label("太重了，充电慢，还发烫，担心安全"), "negative")

    def test_neutral(self):
        self.assertEqual(S.label("这是一款移动电源"), "neutral")

    def test_score(self):
        self.assertGreater(S.score("轻便且续航耐用"), 0)
        self.assertLess(S.score("太重发烫"), 0)

    def test_empty(self):
        self.assertEqual(S.label(""), "neutral")
        self.assertEqual(S.label(None), "neutral")


if __name__ == "__main__":
    unittest.main(verbosity=2)
