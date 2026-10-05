"""大模型集成层验证（本地 OpenAI 兼容 mock 服务，非真实付费模型调用）。

目的：在没有可用 API Key 的环境下，仍能验证 src/llm.py 与 src/insights.py 的
**真实代码路径**是否正确：
- 通过**真实的 openai 客户端**（HTTP + SDK）发起 chat.completions 请求；
- 校验响应解析（情感标签、主题 JSON 数组、假设润色文本）；
- 校验模型报错（HTTP 500）时自动回退规则版、不使分析崩溃。

⚠️ 明确声明：本脚本使用**本地 mock 服务**，**不是真实大模型调用**，
因此不能据此声称「AI 增强功能已通过真实模型实测」。真实调用请见 tests/llm_real_call.py。

用法：python tests/llm_integration_local.py
"""
from __future__ import annotations

import http.server
import json
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

STATE = {"content": "positive", "status": 200}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静默
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        _ = self.rfile.read(length) if length else b""
        if STATE["status"] != 200:
            payload = b'{"error":{"message":"mock 500","type":"server_error"}}'
            self.send_response(STATE["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        body = json.dumps({
            "id": "chatcmpl-mock", "object": "chat.completion", "created": 0, "model": "mock",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": STATE["content"]}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    print("=== 大模型集成层验证（本地 OpenAI 兼容 mock，非真实模型）===")
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    os.environ["OPENAI_API_KEY"] = "mock-key-for-integration-test"
    os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
    os.environ["OPENAI_MODEL"] = "mock-model"

    from src import llm as LLM, insights as I

    failures = []
    try:
        assert LLM.is_available(), "配置 Key 后 is_available 应为 True"
        print("[OK] is_available() 在配置 Key 后返回 True")

        # 1) 情感标注：真实 SDK 请求 → 解析
        STATE["content"] = "positive"
        out = LLM.llm_sentiment("轻便小巧，续航耐用")
        ok = out == "positive"
        print(f"[{'OK' if ok else 'FAIL'}] llm_sentiment 真实请求解析 → {out!r}")
        if not ok:
            failures.append("llm_sentiment")

        # 2) 主题标注：JSON 数组解析
        STATE["content"] = '["容量/续航", "价格", "不存在的主题"]'
        themes = LLM.llm_themes("续航耐用又便宜", [t[0] for t in I.THEMES])
        ok = themes == ["容量/续航", "价格"]
        print(f"[{'OK' if ok else 'FAIL'}] llm_themes 真实请求解析（过滤非法主题）→ {themes}")
        if not ok:
            failures.append("llm_themes")

        # 3) 假设润色
        STATE["content"] = "这是一条待验证的假设描述，需要进一步验证。"
        narr = LLM.llm_opportunity_narrative("标题", "原始描述", "上下文")
        ok = "待验证" in narr
        print(f"[{'OK' if ok else 'FAIL'}] llm_opportunity_narrative 真实请求 → {narr[:40]}...")
        if not ok:
            failures.append("narrative")

        # 4) 模型报错 → 自动回退规则版，不崩溃
        STATE["status"] = 500
        df = pd.DataFrame([
            {"review_id": f"R{i}", "product_id": "P1", "rating": 5, "review_text": "轻便续航耐用",
             "review_date": "2025-01-01", "source": "s", "rating_valid": True,
             "date_valid": True, "text_valid": True}
            for i in range(1, 4)
        ])
        res = I.analyze_reviews(df, use_llm=True)
        ok = res["n_text"] == 3 and res["sentiment_summary"]["positive"] == 3
        print(f"[{'OK' if ok else 'FAIL'}] 模型 HTTP 500 时自动回退规则版，情感分布={res['sentiment_summary']}")
        if not ok:
            failures.append("fallback")

        # 5) 费用控制：上限存在且为正
        ok = LLM.MAX_LLM_REVIEWS > 0
        print(f"[{'OK' if ok else 'FAIL'}] 费用控制上限 MAX_LLM_REVIEWS={LLM.MAX_LLM_REVIEWS}")
        if not ok:
            failures.append("cap")
    finally:
        srv.shutdown()

    print("\n=== 结论 ===")
    if failures:
        print(f"失败项：{failures}")
        return 1
    print("集成层代码路径全部通过（请求/解析/回退/费用控制）。")
    print("⚠️ 注意：使用本地 mock，非真实大模型；真实调用结论见 llm_real_call.py（当前环境=未验证）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
