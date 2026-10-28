# 四川电影电视学院：登录骨架与验证边界

本改动基于 PR #2 的当前代码 **b6b928ad7f7281b126f19c9220a0cf401b849837**。
已知信息来自 [Issue #1 的公开入口检查及 2026-10-27 回复](https://github.com/northartist/zjgsu-course-helper/issues/1#issuecomment-6441250302)。
账号密码入口可用的确认不等于本项目已通过真实账号登录或完成业务适配。

| 项目 | 当前约定 |
|---|---|
| 学校标识 | `sfc`；默认仍为 `zjgsu` |
| 独立 `base_url` | `https://jwgl.sfc.edu.cn/jwglxt/` |
| 已确认登录入口 | `https://jwgl.sfc.edu.cn/jwglxt/xtgl/login_slogin.html` |
| 登录方式 | 用户在独立 Edge 的用户登录页签填写账号密码 |
| 浏览器隔离 | `edge_profile_sfc`，CDP 端口 9228；浙工商继续使用原目录及 9227 |
| HTTP Cookie | 导入时绑定所选教务主机、HTTPS；所有请求与重定向逐次检查精确主机和教务路径 |
| 登录判断 | 必须有核实过的只读验证地址与正向成功规则；川影当前默认未配置，返回 `unverified` |
| 业务方法 | `init`、课程查询、提交、已选对账均在网络请求前抛出 `NotImplementedError` |
| GUI | 学校选择、清空旧 Cookie、仅登录 Tab、禁止业务任务和后台已选刷新 |
| 数据 | 川影不创建/展示课程缓存，不覆盖浙工商设置；重启仍默认浙工商 |

软件不收集、提交或保存账号密码，没有猜测川影表单 POST 地址、字段、RSA 参数、令牌或验证码规则。
独立 Edge 自身会持有浏览器站点数据；“Cookie 不落盘”指应用不把抓到的 Cookie 写入配置或日志。

## 最小调用

```python
from school_adapter import create_adapter
from sfc_api import BASE
from zjgsu_launcher import make_client

client = make_client(BASE, cookie, print, school_id="sfc")
# 等价：create_adapter(cookie, school_id="sfc")
try:
    assert not client.check_login()  # 当前没有核实过的登录后探针
    print(client.login_check.status)  # unverified
finally:
    client.s.close()
```

`login_session.SessionProbe(url, authenticated)` 是明确的注入点。
只有拿到该校脱敏登录后页面、验证只读 URL 和正向成功证据后才能设置 `SfcClient(..., login_probe=...)`；
也可在工厂创建后设置 `client.login_probe`。
测试中的 `/fixture/authenticated`、`fixture_session`、`data-fixture-session` 全是**合成夹具**，不能用于生产配置。

检查每次重新进行，不缓存“已登录”。空页面、未知页面、重定向、非 200 或登录表单均不会成功；
HTTP 200 和页面标题“教学管理”也不能单独证明登录。
当前无法凭未知页面区分“入口已关闭”和“选课未开放”；未核实的响应统一保持未确认，
不能推断已登录，更不能触发课程业务探测。登录错误、入口状态和选课开放状态需要各自的证据。

## 仍待真实页面或脱敏响应核实的字段

| 范围 | 必须核实的内容 |
|---|---|
| 账号密码表单 | 表单 action、HTTP 方法、用户名/密码字段名、隐藏字段、CSRF token；是否加密及公钥/算法、是否有验证码。当前全部由浏览器原站处理 |
| 登录成功证据 | 密码提交后的实际跳转链、最终 URL、适合重放的只读验证 URL、响应类型、必须存在的用户/菜单/会话标记及其脱敏结构 |
| 登录失败/过期 | 错误提示字段和状态码、同 URL 返回登录表单的特征、失效重定向、会话续期或轮换方式 |
| Cookie | 实际名称、Domain、Path、Secure、过期/续期规则；是否存在同名不同路径 Cookie、是否依赖其他本校站点。当前只接受已确认教务主机，不自动放宽域名 |
| 入口关闭/维护 | HTTP 状态、重定向及页面中的稳定标记；不能仅依据空白或 HTTP 200 判定 |
| 选课未开放 | 独立于登录状态的真实页面/响应证据；目前不发送探测请求 |
| 课程初始化 | 用户、学年、学期及选课轮次字段和来源；不复用浙工商运行时值 |
| 课程查询 | URL、方法、分类、分页、ID 含义、校区、周次/节次、容量字段及共享 Course/Jxb 的映射 |
| 提交与对账 | 提交请求契约、成功/失败/限流/未知状态、幂等语义、已选权威数据及最终对账规则 |
| 数据隔离 | 启用业务前还需学校/账号/学期维度的缓存、志愿、已选和课程规则隔离；当前川影业务整体禁用 |

提供样本前去除姓名、学号、Cookie、令牌等信息，不需要提供账号密码。

## 离线验证

在仓库根目录执行：

```bash
python -m unittest discover -s tests -v
```

覆盖未知学校拒绝、川影地址边界、Cookie 域和跨域跳转、浏览器标签精确筛选、
模拟账号密码登录后 Cookie 捕获与会话验证、失效/空白/关闭样本、未验证业务拒绝、
GUI 参数快照和后台任务阻止，以及原浙工商的模型兼容、跨 Tab 查询、串行提交和已选对账。
HTTP 传输被离线夹具替换；没有真实登录、课程查询或选课请求。
