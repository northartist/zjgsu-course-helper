# 部署与环境说明（Deployment Guide）

本文件回答一件事：**在什么环境上、用哪几种方式能把这个程序跑起来**。
面向「自己装来用」和「拷给别人用」两种场景。

---

## 1. 环境要求

| 项目 | 要求 | 说明 |
|---|---|---|
| **操作系统** | **Windows 10 / 11 (x64)** | 程序依赖 `msedge.exe` 与 Windows DPI API。其他系统理论能启动界面，但「抓 Cookie」环节不可用（找不到 Edge） |
| **Python** | **3.10 及以上**（开发与实测：3.11 / 3.12） | 必须带 **tkinter**。Windows 官方安装包默认包含；用官方安装包时**务必勾选** `tcl/tk and IDLE` 与 `Add python.exe to PATH` |
| **第三方包** | 见 `requirements.txt`（4 个，纯 Python） | `requests` / `beautifulsoup4` / `openpyxl` / `websocket-client` |
| **Microsoft Edge** | 任意近期版本（Windows 自带） | 程序只启动一个**独立实例**（独立用户目录 + 调试端口）用来登录教务、读取 Cookie；**不影响你日常在用的浏览器窗口** |
| **网络** | 能访问 `https://jwxt.zjgsu.edu.cn/` | 校园网或校外 VPN 均可；程序直连教务，不经过任何第三方服务器 |
| **本机端口** | `127.0.0.1:9227` | 程序与它自己启动的 Edge 通过 CDP 通信；被占用时会在日志里报错（见第 8 节） |
| **磁盘** | 程序本体约 0.5 MB + 缓存约 10 MB | 首次使用后会生成独立 Edge 配置目录（几十 MB 量级） |
| **权限** | **普通用户即可**，不需要管理员 | 用户数据写在 `%LOCALAPPDATA%` 下，不写注册表、不改系统设置 |

**不需要**：Node.js、Docker、云服务、浏览器扩展、任何 API Key。程序没有服务端，也不会上传你的任何数据。

---

## 2. 依赖清单

```bash
pip install -r requirements.txt
```

| 包 | 最低版本 | 用途 | 缺失后果 |
|---|---|---|---|
| `requests` | 2.28 | 与教务建立会话、提交表单 | 启动即报 `ModuleNotFoundError` |
| `beautifulsoup4` | 4.11 | 解析教务返回的 HTML（教学班列表、已选列表） | 查询/刷新已选失败 |
| `openpyxl` | 3.1 | 导出 Excel | 「导出 Excel」不可用 |
| `websocket-client` | 1.6 | 连接 Edge 的 CDP WebSocket 取 Cookie | 「自动抓取 Cookie」不可用 |

> 只用到 Python 标准库的 `tkinter` / `threading` / `concurrent.futures` / `urllib` / `json` / `ctypes`，无需额外系统依赖。

---

## 3. 三种部署方式

### 方式 A：源码运行（推荐）

```bat
git clone https://github.com/northartist/zjgsu-course-helper.git
cd zjgsu-course-helper

:: 可选但推荐：独立虚拟环境，避免污染系统 Python
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
python zjgsu_launcher.py
```

日常使用不想看到黑色控制台窗口，就双击 **`启动工商大学选课助手.vbs`**（内部用 `pythonw.exe` 启动）。

**vbs 启动器的解释器查找顺序**：

1. 环境变量 `ZJGSU_PYTHONW`（写全路径，优先级最高）
2. PATH 上的 `pythonw.exe`
3. PATH 上的 `pyw.exe`（Windows 的 Python 启动器）
4. 兜底直接调 `pythonw.exe`

如果你的 Python 装在非标准位置、双击没反应，先设一次环境变量：

```bat
setx ZJGSU_PYTHONW "D:\Python311\pythonw.exe"
```

（`setx` 之后要**重新登录或重开资源管理器**才生效。）

### 方式 B：便携部署（拷目录）

把整个仓库目录复制到任意位置（U 盘、`D:\Tools\` 都行），目标机满足第 1 节的环境要求即可：

- **不要**连 `.venv` 一起拷（虚拟环境不可跨机器/跨路径复制），目标机重新 `pip install -r requirements.txt`
- 程序本体与用户数据是**分离**的：配置、缓存、日志都在 `%LOCALAPPDATA%\工商大学选课助手\`，
  所以直接覆盖程序目录即可升级，配置不丢
- 每台机器的 Cookie / 缓存各自独立，互不影响

### 方式 C：打包成 exe（免装 Python，可选）

需要目标机仍装有 **Edge**（抓 Cookie 用），但不再需要 Python 环境：

```bat
pip install pyinstaller
pyinstaller --noconfirm --clean --onedir --windowed --name "工商大学选课助手" ^
  --icon zjgsu_launcher.ico ^
  --add-data "course_preset_details.json;." ^
  --add-data "zjgsu_launcher.ico;." ^
  zjgsu_launcher.py
```

产物在 `dist\工商大学选课助手\`，双击其中的 exe 即可。

- **`course_preset_details.json` 必须一起打包**（第 1 个 `--add-data`）——程序从「程序自己所在目录」读它
- **`zjgsu_launcher.ico` 也一起打包**（第 2 个 `--add-data`）——窗口图标靠它。缺了不会崩，
  但窗口会退回 Python 默认的羽毛图标（`docs/CHANGELOG.md` v0.1.10 记了这个坑）
- 加 `--onefile` 可打成单文件（启动稍慢，首次解包要几秒）
- 本仓库**不附带**打包产物；exe 未签名，部分杀软可能误报，自行判断
- 数据目录不变（仍是 `%LOCALAPPDATA%\工商大学选课助手\`）

---

## 4. 首次配置（5 步）

1. **启动程序** → 「登录」Tab
2. 点 **「打开登录窗口」** → 会弹出一个独立的 Edge 窗口（与你的日常浏览器隔离）
3. 在该窗口里登录教务系统（学号 + 密码），**等页面完全加载**
4. 回到程序点 **「自动抓取 Cookie」** → 成功后点 **「验证 Cookie」**（显示已登录即 OK）
   - 提示：**每次重启软件都要重新抓一次 Cookie**（教务 Cookie 不落盘），这是设计如此
   - 抓完可以点「关闭登录窗口 / 调试端口」把那个 Edge 关掉，不影响已抓到的 Cookie
5. 进入 **「全部课程」** Tab → **「拉取全部课程」**（首次约 13 秒，约 2700 门，之后走本地缓存）

之后按 `README.md` 的「快速上手」或 `docs/USAGE.md` 走搜索 → 加志愿 → 监控抢课。

---

## 5. 文件落点

### 程序目录（本仓库，只读资源）

| 文件 | 作用 |
|---|---|
| `zjgsu_launcher.py` | 主程序（GUI + 抢课循环） |
| `zjgsu_api.py` | 教务接口层（含 Cookie 抓取） |
| `course_state.py` | 状态与规则（去重、课表、进度） |
| `course_preset_details.json` | 教学班详情预设表（程序运行时读取） |
| `backfill_catalog.py` | 一次性维护脚本（不需要日常运行） |
| `zjgsu_launcher.ico` | 图标 |
| `启动工商大学选课助手.vbs` | 无控制台启动器 |

### 用户数据目录：`%LOCALAPPDATA%\工商大学选课助手\`

| 文件 / 目录 | 内容 |
|---|---|
| `settings.json` | 所有界面设置（筛选条件、旋钮、开关状态） |
| `course_presets.txt` | 待选（志愿）列表 |
| `selected_courses.json` | 本程序抢到的课程记录 |
| `system_selected_courses.json` | 从教务读回的「已选课程」快照 |
| `course_catalog.json` | 「拉取全部课程」的本地缓存（离线搜索用） |
| `all_courses_detailed.json` | 拉取时存下的教学班明细 |
| `logs\app.log` | 运行日志（超过约 1 MB 自动轮转，保留最近的） |
| `edge_profile_zjgsu\` | **独立 Edge 的用户数据目录**（只给本程序用；想彻底清干净删这个目录） |

> 升级程序（覆盖程序目录）不会动这些文件；想彻底重置就删整个数据目录。

---

## 6. 网络与代理注意事项

- 程序**直连** `jwxt.zjgsu.edu.cn`，不经过任何中间服务器。
- `requests` 默认会读取系统环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`。
  如果你本机装了代理软件并设置了这些变量（或设置了系统代理），可能**连不上校园站点**。
  处理办法二选一：
  - 在代理软件的绕过列表里加入 `jwxt.zjgsu.edu.cn`、`*.edu.cn`
  - 或给本程序单独设置绕过：命令行启动前 `set NO_PROXY=jwxt.zjgsu.edu.cn` 再 `python zjgsu_launcher.py`
- 程序**不修改**你的系统代理设置，也不接管浏览器（用的是独立实例）。

---

## 7. 卸载 / 清理

1. 关闭程序（有独立 Edge 窗口的话一并关闭）
2. 删除程序目录
3. 删除 `%LOCALAPPDATA%\工商大学选课助手\`（含设置、缓存、日志、独立 Edge 配置）

程序没有服务、没有计划任务、没有注册表项，删完即净。

---

## 8. 部署问题排查

| 症状 | 原因 | 处理 |
|---|---|---|
| 双击 vbs 没反应（无窗口无提示） | `pythonw` 不在 PATH，或依赖没装（pythonw 模式看不到报错） | 用 `python zjgsu_launcher.py` 在控制台启动，看真实报错；或设 `ZJGSU_PYTHONW` |
| `ModuleNotFoundError: No module named 'requests'` | 依赖未安装 / 装到了别的 Python | `pip install -r requirements.txt`，确认 `python -c "import sys; print(sys.executable)"` 与启动用的是同一个解释器 |
| 界面能开，字体/控件巨大或很小 | 系统缩放 ≠ 程序 DPI 适配 | 程序已做 DPI 感知；若仍异常，检查系统缩放设置，或重启程序 |
| 「找不到 Microsoft Edge」 | Edge 被卸载 / 装在非默认路径 | 装回 Edge；或把 `msedge.exe` 所在目录加进 PATH |
| 点「自动抓取 Cookie」报「没有找到独立 Edge 调试窗口」 | 登录窗口被关了 / 还没启动 / 页面没加载完 | 重新点「打开登录窗口」，等教务页面出来再抓 |
| 报端口/连接错误（9227） | 上次的独立 Edge 没关干净，或端口被别的程序占用 | 点「关闭登录窗口 / 调试端口」；仍不行就注销/重启后重试，或改 `zjgsu_api.py` 里的 `DEBUG_PORT` |
| 抓到了 Cookie 但查询/提交失败 | Cookie 过期（关了浏览器、登录超时） | 重新走第 4 节的第 2–4 步 |
| 提交返回「频率过高」 | 请求过于密集 | 把「满课节流(秒)」调大（如 4–6 秒），别用 0.5 |
| 控制台中文乱码 | 传统 cmd 编码 | 用 vbs 启动（无控制台），或在控制台先执行 `chcp 65001` |
| 杀软/Defender 报警 | 未签名脚本 + 自动化行为 | 自行判断；介意就不要用，或把目录加入白名单 |
