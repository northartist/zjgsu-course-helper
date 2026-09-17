# 第三方开源组件与参考来源标注

本文件列出「工商大学选课助手」开发与运行过程中用到的第三方开源组件、接口参考来源及其协议，
以及本项目的合规处理方式。

**免责说明**：本项目是独立作品，仅以下述方式使用第三方组件 —— 运行时依赖（需使用者自行安装，
本项目不分发其代码）、接口协议参考（不复制源码）、事实性接口信息（URL 路径与参数名）。

---

## 一、运行时依赖（Python 包，不随本项目分发）

| 组件 | 协议 | 用途 | 使用方式 |
|---|---|---|---|
| [requests](https://github.com/psf/requests) | Apache-2.0 | HTTP 会话、POST 表单提交教务接口 | `pip install`，运行时 import |
| [beautifulsoup4](https://github.com/wention/BeautifulSoup4) | MIT | 解析教务返回的 HTML（教学班列表、已选列表） | `pip install`，运行时 import |
| [openpyxl](https://foss.heptapod.net/openpyxl/openpyxl) | MIT | 导出志愿列表 / 课程列表为 .xlsx | `pip install`，运行时 import |
| [websocket-client](https://github.com/websocket-client/websocket-client) | Apache-2.0 | 连接 Edge 的 CDP WebSocket，读取 Cookie | `pip install`，运行时 import |

> 以上均为**运行时依赖**：本项目源码中只有 `import` 语句，未复制任何代码，因此不构成衍生作品。

## 二、标准库与运行时

| 组件 | 协议 | 用途 |
|---|---|---|
| [Python](https://www.python.org/)（含 `tkinter` / `ttk` / `sqlite3` 等标准库） | PSF License | 语言运行时与 GUI 框架 |
| [Tcl/Tk](https://www.tcl.tk/) | Tcl/Tk License（BSD 风格） | tkinter 底层 GUI 库，随 Python 分发 |
| [Microsoft Edge](https://www.microsoft.com/edge) | 专有软件（免费使用） | 提供独立调试实例与 CDP 接口以抓取 Cookie；仅作为外部进程调用 |

## 三、接口实现参考来源

| 项目 | 协议 | 与本项目的关系 | 合规处理 |
|---|---|---|---|
| [lnuElytra](https://github.com/mcitem/lnuElytra)（岭南师范学院正方教务选课工具，Rust 实现；GUI 版 [lnu_elytra](https://github.com/mcitem/lnu_elytra)） | **AGPL-3.0** | 参考其「正方教务直连请求格式」的**接口调用顺序与字段命名**（`init` → 查询教学班 → 提交志愿），用于验证本项目 Python 实现的请求格式。**未复制其任何源代码**。 | 本项目同样采用 **AGPL-3.0** 开源（协议一致，无兼容风险）；参考事实性接口信息（URL 路径、参数名、返回结构）不构成代码复制。 |

> 说明：岭南师范学院教务系统与浙江工商大学的部署细节不同（例如本项目必须带
> `&layout=default` 才能拿到完整索引页，否则返回 22 字节空壳），因此接口层为本项目独立实现。

## 四、教学班详情缓存数据

`course_preset_details.json` 中的课程名称、教学班号、时间、教室、教师、学分等字段，
来自**公开查询得到的教务课程目录**（学生登录后可见的选课列表数据），用于离线查看与预设详情。
不含任何个人身份信息（无学号、姓名、成绩）。各校课程目录版权归学校所有，此处仅作**功能演示与本地缓存**用途。

## 五、合规结论

- 本项目**本体协议**：AGPL-3.0（见 `LICENSE`）。
- 无 GPL/AGPL 专有代码复制；无协议冲突。
- 未分发任何第三方二进制文件、字体或素材。
- README、LICENSE、本文件三处署名一致：`北面艺术家 (North Artist / @northartist)`。

如你认为本项目某处标注不当或遗漏了应标注的组件，请开 Issue 指出，我会立即更正。
