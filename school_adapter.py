"""学校接口扩展入口；浙工商完整实现与川影登录骨架。

保留现有课程字段，便于逐步迁移 GUI。各适配器负责解释自己的接口参数、
凭据作用域及返回值；注册接口本身不会启用其他学校的登录或业务规则。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol


Log = Callable[[str], None]
DEFAULT_SCHOOL_ID = "zjgsu"


@dataclass
class Jxb:
    jxb_id: str
    do_id: str
    jxbmc: str = ""
    jsxx: str = ""
    sksj: str = ""
    yxzrs: str = ""
    jxbrl: str = ""
    xqumc: str = ""
    jxdd: str = ""


@dataclass
class Course:
    xkkz_id: str = ""
    kch_id: str = ""
    kcmc: str = ""
    tab_name: str = ""
    jxb: list[Jxb] = field(default_factory=list)
    kch: str = ""


class SchoolAdapter(Protocol):
    """GUI 使用的接口契约，查询数据须符合现有缓存/已选记录字段。

    kch_id、do_id、xkkz_id 是适配器的提交上下文，调用方原样传回。
    select_course 返回兼容 GUI 的 (flag, msg)：flag=1 代表提交成功，
    最终已选状态仍由 fetch_selected_courses 对账；各校原始状态须自行转换。
    """

    def check_login(self) -> bool: ...

    def init(self) -> bool: ...

    def fetch_course(self, q: str) -> Course: ...

    def fetch_all_courses_detailed(self, page_size: int = 1000,
                                   max_pages: int = 200, workers: int = 8,
                                   log: Log | None = None) -> list[dict]: ...

    def fetch_selected_courses(self, enrich: bool = True) -> dict: ...

    def select_course(self, kch_id: str, do_id: str,
                      xkkz_id: str | None = None) -> tuple[str | int, str | None]: ...


class AdapterFactory(Protocol):
    def __call__(self, cookie: str, base_url: str | None,
                 log: Log | None) -> SchoolAdapter: ...


def _create_zjgsu(cookie: str, base_url: str | None,
                  log: Log | None) -> SchoolAdapter:
    # 延迟导入保持接口契约独立；静态 import 也便于 PyInstaller 收集依赖。
    from zjgsu_api import BASE, ZjgsuClient
    return ZjgsuClient(cookie, base_url=base_url or BASE, log=log)


def _create_sfc(cookie: str, base_url: str | None,
                log: Log | None) -> SchoolAdapter:
    from sfc_api import BASE, SfcClient
    return SfcClient(cookie, base_url=base_url or BASE, log=log)


_FACTORIES: dict[str, AdapterFactory] = {DEFAULT_SCHOOL_ID: _create_zjgsu, "sfc": _create_sfc}


def register_adapter(school_id: str, factory: AdapterFactory) -> None:
    """注册开发者提供的工厂，不允许覆盖已有学校或自动按域名猜测适配器。"""
    if not school_id or school_id != school_id.strip():
        raise ValueError("学校标识不能为空或包含首尾空白")
    if school_id in _FACTORIES:
        raise ValueError(f"学校适配器已注册：{school_id}")
    if not callable(factory):
        raise TypeError("学校适配器工厂必须可调用")
    _FACTORIES[school_id] = factory


def create_adapter(cookie: str, base_url: str | None = None,
                   log: Log | None = None, *,
                   school_id: str = DEFAULT_SCHOOL_ID) -> SchoolAdapter:
    """显式选择已注册实现；默认继续使用浙工商的域名校验与请求链路。"""
    factory = _FACTORIES.get(school_id)
    if factory is None:
        raise ValueError(f"尚未适配学校：{school_id}；已注册：{', '.join(sorted(_FACTORIES))}")
    return factory(cookie=cookie, base_url=base_url, log=log)
