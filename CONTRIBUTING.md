# 贡献指南（Contributing）

感谢你愿意帮忙！这个项目是浙江工商大学正方教务系统的桌面选课助手，最需要的贡献有三类：

1. **Bug 报告** —— 尤其是教务接口变更导致的失效（这是最要命的）
2. **使用反馈** —— 哪个按钮难用、哪句日志看不懂、哪种筛选条件不符合直觉
3. **代码贡献** —— 修 bug、加功能、改文档

---

## 报告 Bug 前请先确认

- 你已经**重启过程序**（改动只在重启后生效）
- 你已经**重新抓过 Cookie**（每次重启都要重抓一次，这是设计如此）
- 你翻过 [`docs/CHANGELOG.md`](docs/CHANGELOG.md)，看是不是已知问题的表现
- 你试过 [`docs/DEPLOY.md`](docs/DEPLOY.md) 第 8 节的「部署问题排查表」

## 报告 Bug 时需要提供

| 信息 | 说明 |
|---|---|
| 程序版本 | 标题栏 / 日志开头都会写（如 `v0.1.10`） |
| 复现步骤 | 你点了什么、按什么顺序、期望看到什么、实际看到什么 |
| **日志片段** | `%LOCALAPPDATA%\工商大学选课助手\logs\app.log` 里相关的那几行（点界面上的「打开日志文件夹」） |
| 截图 | 界面截图很有帮助（Tkinter 的界面截图请包含整个窗口） |
| 教务返回 | 若日志里有「教务原始返回」留档，一并附上（已自动脱敏为接口返回内容） |

> ⚠️ **贴日志前请自己检查一遍**：删掉 Cookie、学号、姓名、成绩等个人信息。
> 仓库 Issue 是**公开**的，任何人可见。日志本身不含 Cookie（Cookie 不落盘），但你自己粘贴的内容要留意。

## 开发环境

```bash
git clone https://github.com/northartist/zjgsu-course-helper.git
cd zjgsu-course-helper
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python zjgsu_launcher.py          # 带控制台，方便看报错
```

- Python **3.10+**（Windows），需要 Microsoft Edge
- 环境与部署细节见 [`docs/DEPLOY.md`](docs/DEPLOY.md)
- 代码结构与接口链路见 [`docs/TECH.md`](docs/TECH.md)

## 代码约定（改之前请读）

1. **界面逻辑不进接口层**：`zjgsu_api.py` 不该 import tkinter；工作线程不能直接读 Tk 控件
   （历史 bug：会抛 `main thread is not in main loop`），base_url / Cookie 都要在主线程取好再传进线程。
2. **提交必须串行**：正方选课接口是会话绑定的写操作，并发提交会撞「频率过高」且判不准结果归属。
   只有只读查询（拉取全部课程）才用线程池。
3. **判重按核心教学班号**（`teaching_class_core()`），不要比整串教学班名 —— 教务会加校区 / 网课平台 / 课程别名前缀。
4. **改动小步、留痕**：每个失败路径都要写日志（含「为什么没做」），首次出现的异常教务返回落盘留档。
5. **同步更新文档**：行为变了就更新 `docs/CHANGELOG.md`；用户可见的操作变了就更新 `README.md` / `docs/USAGE.md` / `docs/DEPLOY.md`。
6. **不要硬编码本机路径**（`C:\Users\<某人>\...`）——用 `%LOCALAPPDATA%` / 环境变量 / 相对路径。

## 提交 Pull Request

```bash
git checkout -b fix/简短描述
# 改代码 + 自测（至少：程序能启动、涉及的功能能跑通）
git commit -m "fix: 一句话说明（现象 → 原因 → 修法）"
git push origin fix/简短描述
```

PR 描述里请写清：**现象 / 根因 / 修法 / 怎么验证的**。
如果改动涉及提交口径（什么时候发选课请求），请特别说明并给出理由。

## 协议

本项目以 **AGPL-3.0** 开源（见 [`LICENSE`](LICENSE)）。
提交贡献即表示你同意你的贡献以同一协议分发，且你有权这样做。

---

有任何不确定的地方，直接在 Issue 里问，不用客气。
