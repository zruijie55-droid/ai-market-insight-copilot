"""真实浏览器端到端测试：启动 Streamlit，通过网页文件上传流程走完模块1–5，并截图。

流程：启动 app.py → 上传 CSV 产品表 → 上传 XLSX 评价表 → 依次查看
「数据上传与质量 / 竞品分析 / 用户洞察 / 机会假设与导出」页面 → 截图 → 校验关键内容。

用法：python tests/web_browser_test.py
依赖：playwright（pip install playwright），系统 Chromium（/usr/bin/chromium 或缓存浏览器）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOT_DIR = ROOT / "output" / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8517
URL = f"http://localhost:{PORT}"
CHROME = "/usr/bin/chromium"

PROD_FILE = ROOT / "tests" / "_fixtures" / "products_test.csv"
REV_FILE = ROOT / "tests" / "_fixtures" / "reviews_test.xlsx"

result = {"steps": [], "ok": False, "error": None}


def log(step: str, ok: bool, detail=""):
    result["steps"].append({"step": step, "ok": ok, "detail": detail})
    print(f"[{'OK' if ok else 'FAIL'}] {step} {detail}")


def wait_server(timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(URL, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    from playwright.sync_api import sync_playwright

    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", str(PORT), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_server():
            log("Streamlit 启动", False, "服务器未在超时内就绪")
            return
        log("Streamlit 启动", True, URL)

        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME,
                                        args=["--no-sandbox", "--disable-gpu"])
            page = browser.new_page(viewport={"width": 1400, "height": 1100})
            page.goto(URL, wait_until="networkidle")
            page.wait_for_timeout(2500)
            page.screenshot(path=str(SHOT_DIR / "00_home.png"))
            log("首页加载", True, "00_home.png")

            # 上传产品表 CSV（第一个 file input）
            inputs = page.locator('input[type="file"]')
            n = inputs.count()
            if n < 2:
                log("上传控件", False, f"仅找到 {n} 个文件上传控件")
                return
            log("上传控件", True, f"找到 {n} 个文件上传控件")

            inputs.nth(0).set_input_files(str(PROD_FILE))
            page.wait_for_timeout(3500)  # 等待上传 + 重新计算
            page.screenshot(path=str(SHOT_DIR / "01_after_product_upload.png"))

            # 上传评价表 XLSX（第二个 file input）
            inputs.nth(1).set_input_files(str(REV_FILE))
            page.wait_for_timeout(4000)
            page.screenshot(path=str(SHOT_DIR / "02_after_review_upload.png"))

            # 校验：侧边栏应显示用户上传文件名
            body_text = page.inner_text("body")
            uploaded = ("products_test.csv" in body_text) and ("reviews_test.xlsx" in body_text)
            log("文件上传被识别", uploaded,
                "侧边栏显示 products_test.csv / reviews_test.xlsx" if uploaded
                else "未检测到上传文件名")

            # 页面 1：数据上传与质量
            page.locator('label:has-text("1 数据上传与质量")').click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(SHOT_DIR / "03_page1_quality.png"))
            t1 = page.inner_text("body")
            has_quality = ("有效行" in t1) and ("排除行" in t1)
            log("模块1 数据质量展示", has_quality, "显示有效行/排除行等指标")

            # 页面 2：竞品与价格带分析
            page.locator('label:has-text("2 竞品与价格带分析")').click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(SHOT_DIR / "04_page2_competitor.png"))
            t2 = page.inner_text("body")
            has_comp = ("价格带" in t2) and ("品牌" in t2)
            log("模块2 竞品分析展示", has_comp, "显示价格带/品牌对比")

            # 页面 3：用户反馈洞察
            page.locator('label:has-text("3 用户反馈洞察")').click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(SHOT_DIR / "05_page3_insight.png"))
            t3 = page.inner_text("body")
            has_ins = ("主题" in t3) and ("情感" in t3)
            log("模块3 用户洞察展示", has_ins, "显示主题/情感分布")

            # 页面 4：机会假设与导出
            page.locator('label:has-text("4 机会假设与导出")').click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(SHOT_DIR / "06_page4_hypothesis.png"))
            t4 = page.inner_text("body")
            has_hyp = "假设" in t4
            log("模块4 机会假设展示", has_hyp, "显示机会假设区块")

            # 展开「预览 Markdown 报告」使 待验证 文案可见，校验机会标注口径
            try:
                page.get_by_text("预览 Markdown 报告").click()
                page.wait_for_timeout(1500)
            except Exception:
                pass
            page.screenshot(path=str(SHOT_DIR / "07_page4_report_preview.png"))
            t4b = page.inner_text("body")
            has_verify = "待验证" in t4b
            log("模块4/5 待验证标注", has_verify,
                "报告预览含『待验证』标注" if has_verify else "未检测到待验证标注")

            # 报告下载按钮存在性
            dl = page.locator('button:has-text("下载 Markdown 报告")')
            has_dl = dl.count() > 0
            log("报告导出按钮", has_dl, "存在 Markdown 报告下载按钮")

            # 测试真实下载（验证报告内容而非仅 HTTP 200）
            try:
                with page.expect_download(timeout=8000) as dl_info:
                    dl.first.click()
                d = dl_info.value
                save = SHOT_DIR / "downloaded_report.md"
                d.save_as(str(save))
                content = save.read_text(encoding="utf-8-sig", errors="ignore")
                has_sent = "情感分布" in content and "待验证" in content
                log("报告下载内容校验", has_sent,
                    f"下载文件 {save.name} 含情感分布/待验证（{len(content)} 字节）")
            except Exception as e:
                log("报告下载内容校验", False, f"下载失败：{e}")

            browser.close()
        result["ok"] = True
    except Exception as e:
        result["error"] = repr(e)
        log("异常", False, repr(e))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    print("\n=== 网页端真实测试结论 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
