"""School-scoped browser login and HTTP sessions; no course endpoints live here."""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
import urllib.request
from urllib.parse import urlparse
from typing import Callable

import requests
import websocket
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class LoginProfile:
    school_id: str
    name: str
    base_url: str
    login_path: str
    debug_port: int

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname

    @property
    def login_url(self) -> str:
        return self.base_url + self.login_path


LOGIN_PROFILES = {
    "zjgsu": LoginProfile("zjgsu", "浙江工商大学", "https://jwxt.zjgsu.edu.cn/jwglxt/", "", 9227),
    "sfc": LoginProfile("sfc", "四川电影电视学院（仅登录骨架）",
                        "https://jwgl.sfc.edu.cn/jwglxt/", "xtgl/login_slogin.html", 9228),
}


def login_profile(school_id: str = "zjgsu") -> LoginProfile:
    try:
        return LOGIN_PROFILES[school_id]
    except KeyError:
        raise ValueError(f"尚未适配学校：{school_id}") from None


def require_school_url(url: str, profile: LoginProfile) -> str:
    """Validate before sending credentials, including every redirect hop."""
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname != profile.host or p.port not in (None, 443)
            or p.username is not None or p.password is not None
            or not p.path.startswith("/jwglxt/") or p.fragment
            or "\\" in url or any(c in url for c in "\r\n\t")):
        raise ValueError(f"地址必须位于 {profile.base_url}")
    return url


def normalize_school_base(base: str | None, school_id: str = "zjgsu") -> str:
    profile = login_profile(school_id)
    value = (base or profile.base_url).strip().rstrip("/") + "/"
    require_school_url(value, profile)
    p = urlparse(value)
    if p.path != "/jwglxt/" or p.query:
        raise ValueError("服务器地址必须指向 /jwglxt/")
    return profile.base_url


def parse_cookie_pairs(cookie: str) -> dict[str, str]:
    if any(c in cookie for c in "\r\n"):
        raise ValueError("Cookie 不得包含换行")
    pairs = {}
    for part in cookie.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip():
                pairs[key.strip()] = value.strip()
    return pairs


class SchoolSession(requests.Session):
    def __init__(self, profile: LoginProfile):
        super().__init__()
        self.profile = profile

    def send(self, request, **kwargs):
        require_school_url(request.url, self.profile)
        return super().send(request, **kwargs)


def create_login_session(cookie: str, base_url: str | None = None, *,
                         school_id: str = "zjgsu") -> requests.Session:
    normalize_school_base(base_url, school_id)
    pairs = parse_cookie_pairs(cookie)
    profile = login_profile(school_id)
    session = SchoolSession(profile)
    for name, value in pairs.items():
        session.cookies.set(name, value, domain=profile.host, path="/", secure=True)
    return session


@dataclass(frozen=True)
class SessionProbe:
    """Read-only probe and positive predicate verified for this school.

    SFC has no default until a sanitized authenticated page is available.
    Fixture predicates prove plumbing only, not the real response schema.
    """
    url: str
    authenticated: Callable[[requests.Response], bool]


@dataclass(frozen=True)
class LoginCheck:
    status: str  # authenticated / unauthenticated / unavailable / unverified
    message: str


def check_login_session(session: requests.Session, profile: LoginProfile,
                        probe: SessionProbe | None, *, headers=None,
                        follow_redirects: bool = False) -> LoginCheck:
    if probe is None:
        return LoginCheck("unverified", "登录后验证地址和成功标记尚待脱敏页面确认")
    require_school_url(probe.url, profile)
    try:
        response = session.get(probe.url, headers=headers, timeout=15, allow_redirects=follow_redirects)
    except (requests.RequestException, ValueError):
        return LoginCheck("unavailable", "登录验证请求失败，无法确认会话")
    require_school_url(response.url, profile)
    if response.status_code in (401, 403):
        return LoginCheck("unauthenticated", "登录会话未通过验证")
    if 300 <= response.status_code < 400:
        return LoginCheck("unverified", "登录验证发生重定向，需核对登录或入口状态")
    if response.status_code != 200:
        return LoginCheck("unavailable", f"教务入口暂不可用（HTTP {response.status_code}）")
    body = response.text or ""
    password_fields = BeautifulSoup(body, "html.parser").find_all("input")
    if ("login" in urlparse(response.url).path.lower() or "cas" in urlparse(response.url).path.lower()
            or any(str(node.get("type", "")).strip().lower() == "password" for node in password_fields)):
        return LoginCheck("unauthenticated", "返回了登录页面，Cookie 无效或已过期")
    if not body.strip():
        return LoginCheck("unverified", "登录验证返回空页面")
    try:
        confirmed = probe.authenticated(response) is True
    except Exception:
        confirmed = False
    if confirmed:
        return LoginCheck("authenticated", "登录会话已通过验证")
    return LoginCheck("unverified", "未匹配已核实的登录成功标记；不能判定选课是否开放")


def capture_browser_cookie(log=None, *, school_id: str = "zjgsu",
                           port: int | None = None, timeout: int = 5) -> str:
    profile = login_profile(school_id)
    port = profile.debug_port if port is None else port
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=timeout) as response:
        tabs = json.loads(response.read().decode("utf-8"))
    candidates = []
    for tab in tabs:
        try:
            require_school_url(tab.get("url", ""), profile)
        except ValueError:
            continue
        if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl"):
            candidates.append(tab)
    target = max(candidates, key=lambda tab: ("/xsxk/" in tab["url"], "ticket=" in tab["url"]), default=None)
    if target is None:
        raise RuntimeError(f"没有找到 {profile.name} 的教务标签页，请先打开对应登录窗口")
    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=timeout)
    try:
        ws.send(json.dumps({"id": 2, "method": "Network.getCookies", "params": {"urls": [target["url"]]}}))
        deadline = time.monotonic() + timeout
        cookies = []
        while time.monotonic() < deadline:
            result = json.loads(ws.recv())
            if result.get("id") == 2:
                cookies = result.get("result", {}).get("cookies", [])
                break
    finally:
        ws.close()
    pairs = []
    for cookie in cookies:
        domain = cookie.get("domain", "").lstrip(".").lower()
        # CDP filters by URL. Re-scope applicable parent-domain cookies on HTTP import.
        if (domain in {profile.host, profile.host.split(".", 1)[1]}
                and cookie.get("name")):
            pairs.append(f"{cookie['name']}={cookie.get('value', '')}")
    if not pairs:
        raise RuntimeError(f"没有抓到 {profile.name} 的 Cookie，请先完成账号密码登录")
    if log:
        log(f"已抓取 {profile.name} Cookie（{len(pairs)} 项；尚需验证登录会话）")
    return "; ".join(pairs)
