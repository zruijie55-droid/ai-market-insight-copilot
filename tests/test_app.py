"""Streamlit 页面状态测试：无效价格带必须阻断分析并给出明确提示。"""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parent.parent / "app.py"


class TestAppPriceBands(unittest.TestCase):
    def test_invalid_price_band_order_is_reported(self):
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        app.number_input(key="e1").set_value(250)
        app.number_input(key="e2").set_value(199)
        app.run()

        messages = [item.value for item in app.error]
        self.assertTrue(any("价格带边界必须严格递增" in value for value in messages))
        self.assertTrue(any("价格带配置无效" in value for value in messages))


if __name__ == "__main__":
    unittest.main(verbosity=2)
