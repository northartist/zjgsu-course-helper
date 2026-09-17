# 技术说明（Architecture & Internals）

> 写给想改代码 / 想知道「它到底怎么做到的」的人。所有描述以 **v0.1.9 源码** 为准。

## 1. 三层结构

```
zjgsu_launcher.py   (GUI + 调度层，约 3800 行)
   ├─ Tkinter 界面：5 个 Tab、日志框、状态行
   ├─ 任务调度：工作线程 + queue 事件回传 + 看门狗
   └─ 抢课循环 monitor_rush()：串行提交、节流、收工判定
        ↓ 调用
zjgsu_api.py        (接口层，约 500 行)
   ├─ capture_cookie_from_edge()：CDP 读 Cookie
   ├─ ZjgsuClient：init / fetch_course / fetch_all_courses(_detailed) /
   │              fetch_selected_courses / select_course
   └─ HTML/JSON 解析：parse_selected_courses_html / _json
        ↓ 依赖
course_state.py     (状态与规则层，约 290 行)
   ├─ teaching_class_core()：核心教学班号（判重）
   ├─ timetable_slots() / layout_timetable_slots()：课表时段
   ├─ completion_snapshot()：进度口径
   └─ CourseStateStore：持久化（设置/待选/已选/课程库）
```

**设计取向**：界面逻辑不进接口层；接口层不碰 Tk 控件（历史 bug：工作线程读 Tk 变量会抛
`main thread is not in main loop`，现在所有 base_url / Cookie 都先在主线程取好再传给线程）。

## 2. Cookie 获取（CDP，不走浏览器自动化点按）

```python
EDGE_EXE      = find_edge_exe()                       # 环境变量候选 + PATH，跨机器不写死路径
EDGE_PROFILE  = DATA_DIR / "edge_profile_zjgsu"       # 独立用户目录，不动你的日常浏览器
DEBUG_PORT    = 9227                                  # 只绑 127.0.0.1
```

1. 以 `--user-data-dir=<独立目录> --remote-debugging-address=127.0.0.1 --remote-debugging-port=9227
   --remote-allow-origins=http://127.0.0.1:9227` 启动 Edge，打开教务首页
2. 你在那个窗口登录教务
3. 程序 `GET http://127.0.0.1:9227/json` 列出标签页 → 找到教务页 → 连它的 WebSocket，
   调 `Network.getCookies` 取回 Cookie 串
4. Cookie 只保存在本进程内存里（**不落盘**），所以每次重启都要重新抓

好处：不需要在页面里做脆弱的 DOM 点击；登录交给真人（含验证码、动态码），程序只取凭据。

## 3. 教务接口链路

基址 `https://jwxt.zjgsu.edu.cn/jwglxt/`，实测必需 `&layout=default`，否则索引页只返回 22 字节空壳。

| 环节 | 路径（节选） | 说明 |
|---|---|---|
| 索引 | `xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default` | `init`，建立选课会话态 |
| 教学班列表 | `xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html` | 分页查询（页大小、`kklxdm` 类别） |
| 关键字查询 | `xsxk/zzxkyzbjk_cxJxbWithKchZzxkYzb.html?gnmkdm=N253512` | 按课程号/教学班查 `jxb_id`、容量 |
| **提交志愿** | `xsxk/zzxkyzb_xkBcZyZzxkYzb.html?gnmkdm=N253512` | POST `kch_id` / `jxb_id`，返回 `flag` |
| 已选查询 | `xsxk/zzxkyzb_cxZzxkYzbChoosedDisplay.html` | 对账用（教务视角的已选） |

- `normalize_base()` 只接受 `https://jwxt.zjgsu.edu.cn/` 下的地址 —— 防止把 Cookie 发到别的域
- 提交是**会话绑定的写操作**，因此严格**串行**；只有只读查询（拉取全部课程）走 8 线程
- 返回 `flag` 语义：成功 / 满课（`flag=-1` + `0,<教学班id>,<容量>` 这类无中文提示的串 → 识别为「满课蹲守」，
  保留 `do_id` 缓存做节流盲提交）/ 时间冲突 / 频率过高

## 4. 并发与线程模型

- 主线程只管 UI；长任务（抓 Cookie、拉课程、提交、刷新已选）丢进工作线程
- 线程 → UI 通过 `queue.Queue` 投递事件，主线程 `after()` 轮询消费
- **每个任务结束都切换状态**（任务名 + 结果），另有一个兜底看门狗，避免进度条永远转
- 退出时取消所有 `after` 回调（否则会报 `invalid command name ...poll`）

## 5. 数据与持久化

| 文件（`%LOCALAPPDATA%\工商大学选课助手\`） | 写入方式 | 内容 |
|---|---|---|
| `settings.json` | 原子替换（写 `.tmp` → `os.replace`） | 界面设置：筛选条件、旋钮、开关 |
| `course_presets.txt` | 带时间戳备份 | 待选（志愿）列表 |
| `selected_courses.json` | 原子替换 | 本程序抢到的记录 |
| `system_selected_courses.json` | 原子替换 | 教务已选快照 |
| `course_catalog.json` | 原子替换 | 「拉取全部课程」缓存（离线搜索的数据源） |
| `all_courses_detailed.json` | 原子替换 | 教学班明细 |
| `logs\app.log` | 追加 + 轮转 | 运行日志（预算 ~1 MB，单片 ~256 KB） |
| `course_preset_details.json` | 原子替换 | **在程序目录**：教学班详情预设表（课程名/时间/教室/教师/学分…） |

**资源与数据分离**：程序目录可整体替换升级，用户配置不丢（`PROJECT_DIR` vs `DATA_DIR`）。

## 6. 核心业务规则（这些是踩坑换来的）

### 6.1 判重：按核心教学班号，不比整串

教务的教学班名前缀有三类：**校区**（`教工路(...)`）、**网课平台**（`智慧树网络课(...)`）、
**课程别名**（`国情课(...)`、`影视鉴赏(...)`）。
同一个班教务有时带前缀、有时不带 → 用整串比较会把一个班当成两门课（实测：已选列表里
「中国城市经济与发展」出现两条，通识进度多算一门）。

```python
TEACHING_CLASS_CORE_RE = re.compile(r"\((\d{4})-(\d{4})-(\d)\)-([A-Za-z0-9]+)-([A-Za-z0-9]+)")
# 例：国情课(2026-2027-1)-GENEML053-01 与 (2026-2027-1)-GENEML053-01 → 同一个班
# 班号不同仍是两个班（不会误合并）
```

### 6.2 同一门课只押一个班

按**课程号**去重：同一课程号只允许第一条「已分配」，其余降为「备用」；
开抢时把「教务已选 + 已抢到」的课程号一起计入 —— 教务对同一课程选两个班通常是**替换**先选上的那个。

### 6.3 进度口径：教务真值 ∪ 本程序记录

进度卡（英语/体育/待抢通识）以前只统计本程序抢到的（于是显示 0/1、0/2），
现在以「教务已选 + 本程序抢到」并集统计，并把真值作为开抢时的名额上限。

### 6.4 校区识别

来源优先级：教务返回的 `xqumc` > 教学班名前缀 > 教室名中的校区字样；
**任何来源说"不是本校"就按非本校处理**（宁可多标一个 ⚠，也不要抢到要跨校区通勤的课）。
网课平台前缀一律按本校处理，显示为「网课」，不算异地。
`教工路美术鉴赏(...)` 这种**校区名与课程别名连写**的前缀也要能认出校区。

### 6.5 时间冲突与周数

课表时段由 `timetable_slots()` 解析（`星期X第A-B节{周次}`，支持 `(单)`/`(双)`）。
「自动分配时间段」用已选课程的时段做硬约束挑教学班。
⚠ 周数筛选只是**筛选视图**：教务的冲突判定按节次、不看周次。

## 7. 容错与留痕

- 关键失败都会写日志，并把**首次出现的异常教务返回原始文本落盘**，方便反馈问题
- 满课（`flag=-1`）、频率过高、时间冲突分开处理：满课继续蹲守，冲突重试，频率过高提示调节流
- 「刷新人数」结果写回列表行；抢到的课立刻记账并从待选移除；掉课自动放回
- 启动时**自愈**：历史遗留的"抢到了却还挂在待选里"的条目会被清理

## 8. 工程约定（给改代码的人）

- 运行版目录只放运行所需文件；源码工程、离线回归测试（`test_*.py` / `harness.py` / `verify_*.py`）
  与改动前备份**不随发行目录分发**
- 改动只在**重启软件后**生效（正在跑的窗口是旧代码）
- 预设详情表 `course_preset_details.json` 与「全部课程」缓存同构，可互相回填
- 提交路径不要引入并发 —— 会话绑定 + 结果归属会乱

## 9. 已知限制

- 只支持**浙江工商大学**的正方教务部署（域名与 `layout=default` 参数写死在接口层，是刻意的安全约束）
- 依赖 Edge 的 CDP 抓 Cookie；Edge 被卸载/不可用则登录流程不可用
- 教务接口随时可能变更，届时需要按上面的链路表重新对照抓包结果调整
- 只做「查询 + 提交志愿 + 对账」，不实现退课、换班等写操作

## 10. 依赖与协议

第三方组件、接口参考来源与协议标注见 [`../THIRD-PARTY.md`](../THIRD-PARTY.md)；
本项目本体协议为 **AGPL-3.0**（见 [`../LICENSE`](../LICENSE)）。
