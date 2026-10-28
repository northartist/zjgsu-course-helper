"""四川电影电视学院登录骨架；业务接口必须等待真实页面/脱敏响应验证。"""
from __future__ import annotations

from login_session import (SessionProbe, check_login_session, create_login_session,
                           login_profile, normalize_school_base)

SCHOOL_ID = "sfc"
BASE = login_profile(SCHOOL_ID).base_url
LOGIN_URL = login_profile(SCHOOL_ID).login_url


class SfcClient:
    def __init__(self, cookie: str, base_url: str = BASE, log=None, *,
                 login_probe: SessionProbe | None = None):
        self.base = normalize_school_base(base_url, SCHOOL_ID)
        self.log = log or (lambda _: None)
        self.s = create_login_session(cookie, self.base, school_id=SCHOOL_ID)
        self.login_probe = login_probe
        self.login_check = None

    def check_login(self) -> bool:
        self.login_check = check_login_session(self.s, login_profile(SCHOOL_ID), self.login_probe)
        self.log(f"[川影登录] {self.login_check.message}")
        return self.login_check.status == "authenticated"

    def _unsupported(self):
        message = "川影当前仅提供登录骨架；初始化、课程查询、提交和已选对账尚未验证"
        self.log(message)
        raise NotImplementedError(message)

    def init(self) -> bool:
        return self._unsupported()

    def fetch_course(self, q: str):
        return self._unsupported()

    def fetch_all_courses_detailed(self, page_size=1000, max_pages=200, workers=8, log=None):
        return self._unsupported()

    def fetch_selected_courses(self, enrich=True):
        return self._unsupported()

    def select_course(self, kch_id, do_id, xkkz_id=None):
        return self._unsupported()
