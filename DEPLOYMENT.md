# 发布到 GitHub 与 Streamlit Community Cloud

这个项目需要两个链接：

- **GitHub 仓库链接**：供面试官阅读源码、测试和文档。
- **Streamlit 在线演示链接**：供面试官直接在浏览器操作应用。

GitHub Pages 只能托管静态网页，不能直接运行本项目的 Python / Streamlit 后端。

## 1. 创建 GitHub 仓库

在 GitHub 新建一个公开仓库，建议配置：

- Repository name：`ai-market-insight-copilot`
- Description：`可追溯的竞品分析、用户反馈洞察与产品机会发现 Streamlit 应用`
- Visibility：`Public`
- 不要勾选自动创建 README、`.gitignore` 或 License，本地项目已经包含这些文件。

创建后，在项目根目录执行：

```powershell
git remote add origin https://github.com/zruijie55-droid/ai-market-insight-copilot.git
git push -u origin main
```

## 2. 部署在线演示

1. 打开 [Streamlit Community Cloud](https://share.streamlit.io/)，使用 GitHub 登录。
2. 选择 `Create app`，再选择已有应用仓库。
3. Repository：`zruijie55-droid/ai-market-insight-copilot`。
4. Branch：`main`。
5. Main file path：`app.py`。
6. 在 Advanced settings 中选择 Python `3.12`。
7. 当前规则版无需填写任何 Secrets，直接部署。

部署完成后会获得类似下面的公开链接：

```text
https://ai-market-insight-copilot.streamlit.app/
```

子域名是否可用以 Streamlit 页面实际检查结果为准。之后每次向 `main` 分支推送，在线应用会自动重新部署。

## 3. 未来安全启用大模型

默认云端部署不安装或启用大模型依赖。如需启用：

1. 将部署依赖切换为包含 `openai` 的配置，或把 `openai==2.48.0` 加入 `requirements.txt`。
2. 在 Streamlit Cloud 的应用设置中打开 Secrets。
3. 使用平台 Secrets 保存 `OPENAI_API_KEY`、`OPENAI_MODEL` 和可选的 `OPENAI_BASE_URL`。

不要把真实密钥写入源码、`.env.example`、Git 提交或聊天记录。

## 4. 发布后的检查清单

- 首页能加载内置模拟数据。
- 五个模块都能打开。
- CSV / Excel 上传正常。
- Markdown / HTML 报告可以下载。
- GitHub Actions 显示测试通过。
- README 顶部补上最终在线演示链接。
