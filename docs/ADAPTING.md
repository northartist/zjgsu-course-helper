# 学校适配开发入口

当前只支持浙江工商大学。`school_adapter.py` 提供最小扩展入口，GUI 的
`make_client()` 已使用这个入口，默认仍创建 `ZjgsuClient`。
注册接口供开发者使用，界面尚无学校选择，当前 Cookie 登录流程也仍绑定浙工商。

## 接口契约

适配器实现 `SchoolAdapter` 的六个方法：

| 方法 | 约定 |
|---|---|
| `check_login()` | 验证目标教务会话，返回布尔值 |
| `init()` | 获取当前用户、学期、选课轮次等动态参数，返回是否可用 |
| `fetch_course(q)` | 返回共享 `Course`，其 `jxb` 为 `Jxb` 列表 |
| `fetch_all_courses_detailed(...)` | 返回课程明细列表，字段沿用 `zjgsu_launcher.pull_all_courses()` 的输入契约 |
| `fetch_selected_courses(enrich=True)` | 返回 `{count, credits, courses}`；课程含 `course_name`、`course_code`、`teaching_class`、`time` 等现有已选记录字段 |
| `select_course(kch_id, do_id, xkkz_id=None)` | 返回 `(flag, msg)`，`flag` 为整数或字符串 `1` 表示提交成功，最终选中情况由已选查询对账 |

共享模型为兼容现有 GUI 暂时保留原字段名。`kch_id` / `do_id` / `xkkz_id` 是
适配器的提交上下文，须原样传回；其他系统可以在适配器内部映射其原始 ID 和状态。
轮次参数应从目标学校页面或接口动态读取，不应抄用浙工商的运行时值。

目前调度器仍按既有 `flag/msg` 处理成功、满课、限流和未开放；新实现需要显式转换
对应语义（包括 `容量已满`、`频率过高`、`未开放` 等重试提示），不能把未知返回当成功。

## 注册示例

下面的 `YourSchoolClient` 是待开发的示例名称，必须先实现对应学校的接口：

```python
from school_adapter import register_adapter
from your_school_api import YourSchoolClient
from zjgsu_launcher import make_client

def create_example(cookie, base_url, log):
    return YourSchoolClient(cookie=cookie, base_url=base_url, log=log)

register_adapter("example", create_example)
client = make_client("https://your-school.example/jwglxt/", cookie, print,
                     school_id="example")
```

工厂只接受已注册的学校标识；重复注册会报错，不自动按任意域名猜测实现。
浙工商适配器继续拒绝其他域名，凭据不可因增加扩展入口而被发送到其他站点。

## 接入界面前还需要做什么

- 明确学校选择，并在主线程取得学校及设置快照后传给工作线程；现有调用默认仍为 `zjgsu`。
- 适配登录入口、CDP 目标页、Cookie 作用域及登录验证；界面层和 API 层都有相关逻辑。
- 核对初始化、分页、教学班查询、提交和已选对账；保留提交串行及按学校确认的节流规则。
- 配置课程类别、校区和个人选课目标；同步状态层、监控循环与进度界面的目标值。
- 核对教学班身份、时间/周次解析、冲突规则及课表显示范围。
- 将课程缓存、志愿、已选和浏览器配置按学校、账号、学期隔离，避免混入浙工商预设。

先用脱敏样本做离线回归，再在目标学校验证登录、查询、提交和已选对账，之后才能声明支持。
当前离线测试可运行 `python -m unittest discover -s tests -v`；测试不会访问教务或发起真实选课。
