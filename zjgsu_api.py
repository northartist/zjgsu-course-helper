#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""浙江工商直连 API：用 requests 复刻 lnuElytra 上游请求格式。

上游 Rust 源码 URL 写死 gnmkdm=N253512 且不带 layout=default，
浙江工商的选课索引页必须带 &layout=default 才返回完整页面（否则 22 字节空壳）。
本模块从 Edge CDP 抓 Cookie，复刻 init -> fetch_course -> select_course 全链路。
"""
from __future__ import annotations

import json
import re
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass, field

import requests
import websocket  # websocket-client
from bs4 import BeautifulSoup

BASE = "https://jwxt.zjgsu.edu.cn/jwglxt/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0")
DEBUG_PORT = 9227

INDEX_URL = "xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default"
PART_DISPLAY_URL = "xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html?gnmkdm=N253512"
QUERY_DO_URL = "xsxk/zzxkyzbjk_cxJxbWithKchZzxkYzb.html?gnmkdm=N253512"
SELECT_URL = "xsxk/zzxkyzb_xkBcZyZzxkYzb.html?gnmkdm=N253512"
SELECTED_DISPLAY_URL = "xsxk/zzxkyzb_cxZzxkYzbChoosedDisplay.html"


def normalize_base(base: str) -> str:
    """Return a trusted, normalized Zhejiang Gongshang base URL."""
    value = (base or BASE).strip()
    if not value.endswith("/"):
        value += "/"
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "jwxt.zjgsu.edu.cn":
        raise ValueError("服务器地址必须是 https://jwxt.zjgsu.edu.cn/ 下的地址")
    if not parsed.path.rstrip("/").endswith("/jwglxt"):
        raise ValueError("服务器地址必须指向 /jwglxt/")
    return value


def parse_selected_courses_html(html: str) -> dict:
    """Parse the authoritative selected-course table embedded in the index page."""
    soup = BeautifulSoup(html or "", "html.parser")
    courses = []
    for status_node in soup.select("p.sxbj"):
        tr = status_node.find_parent("tr")
        if tr is None:
            continue
        jxb_node = tr.select_one("p.jxb")
        title = (jxb_node.get("title") if jxb_node else "") or ""
        class_match = re.search(r"(\(\d{4}-\d{4}-\d+\)-[A-Za-z0-9]+-[A-Za-z0-9-]+)", title)
        teaching_class = class_match.group(1) if class_match else title.strip()
        name_match = re.match(r"【([^】]+)】", title)
        code_match = re.search(r"\)-([A-Za-z0-9]+)-", teaching_class)
        button = tr.select_one("button[onclick*='cancelCourse']")
        args = re.findall(r"'([^']*)'", button.get("onclick", "") if button else "")
        def text(selector, attr=None):
            node = tr.select_one(selector)
            if not node:
                return ""
            return (node.get(attr, "") if attr else node.get_text(" ", strip=True)).strip()
        courses.append({
            "course_name": name_match.group(1) if name_match else "",
            "course_code": code_match.group(1) if code_match else "",
            "teaching_class": teaching_class,
            "teacher": text("p.teachers", "title"),
            "time": text("p.time"), "room": text("p.addr"),
            "status": text("p.sxbj"), "source": text("p.zixf"),
            "jxb_id": args[1] if len(args) > 1 else "",
            "do_id": args[2] if len(args) > 2 else "",
            "kch_id": args[3] if len(args) > 3 else "",
            "xkkz_id": args[5] if len(args) > 5 else "",
        })
    count_node = soup.select_one("#yxkcs")
    credits_node = soup.select_one("#yxxfs")
    try:
        count = int(count_node.get_text(strip=True)) if count_node else len(courses)
    except ValueError:
        count = len(courses)
    return {"count": count,
            "credits": credits_node.get_text(strip=True) if credits_node else "",
            "courses": courses}


def parse_selected_courses_json(rows: list[dict]) -> dict:
    courses, credits = [], 0.0
    for row in rows or []:
        title = str(row.get("jxbmc") or "")
        class_match = re.search(r"(\(\d{4}-\d{4}-\d+\)-[A-Za-z0-9]+-[A-Za-z0-9-]+)", title)
        teaching_class = class_match.group(1) if class_match else title
        name_match = re.match(r"【([^】]+)】", title)
        code_match = re.search(r"\)-([A-Za-z0-9]+)-", teaching_class)
        try:
            credits += float(row.get("xf") or 0)
        except (TypeError, ValueError):
            pass
        courses.append({
            "course_name": name_match.group(1) if name_match else "",
            "course_code": code_match.group(1) if code_match else "",
            "teaching_class": teaching_class,
            "teacher": str(row.get("jsxx") or ""),
            "time": str(row.get("sksj") or ""),
            "room": str(row.get("jxdd") or ""),
            "status": "已选上" if str(row.get("sxbj")) == "1" else str(row.get("sxbj") or ""),
            "source": str(row.get("zixf") or "教务系统"),
            "jxb_id": str(row.get("jxb_id") or ""),
            "do_id": str(row.get("do_jxb_id") or ""),
            "kch_id": str(row.get("kch_id") or ""),
            "xkkz_id": str(row.get("xkkz_id") or ""),
        })
    return {"count": len(courses), "credits": f"{credits:g}", "courses": courses}


@dataclass
class Jxb:
    jxb_id: str
    do_id: str
    jxbmc: str = ""
    jsxx: str = ""
    sksj: str = ""
    yxzrs: str = ""
    jxbrl: str = ""
    # 上课校区（教务权威字段）：教工路校区的课必须能一眼认出来，否则下沙的学生
    # 会抢到一门需要跨校区通勤的课。jxbmc 前缀是第二层保险。
    xqumc: str = ""
    jxdd: str = ""


@dataclass
class Course:
    xkkz_id: str = ""
    kch_id: str = ""
    kcmc: str = ""        # 课程名（fetch 命中时回填，供 UI 显示/预设推断）
    tab_name: str = ""    # 命中轮次名（体育分项/英语分项/通识选修课…），用于 PE/EN/GE 前缀
    jxb: list = field(default_factory=list)
    kch: str = ""         # 课程号（GENNET030 这种）；用于"同一门课只押一个班"的去重


class ZjgsuClient:
    def __init__(self, cookie: str, base_url: str = BASE, log=None):
        self.cookie = cookie
        self.base = normalize_base(base_url)
        self.log = log or (lambda m: None)
        self.stores: dict = {}
        self._last_index_html = ""
        self._select_signatures: set = set()
        self.s = requests.Session()
        for kv in cookie.split(";"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                self.s.cookies.set(k.strip(), v.strip(), domain="jwxt.zjgsu.edu.cn")

    def _h(self, referer=None):
        h = {"User-Agent": UA}
        if referer:
            h["Referer"] = referer
        return h

    def check_login(self) -> bool:
        r = self.s.get(self.base + "xtgl/index_initMenu.html?jsdm=xs", headers=self._h(), timeout=15)
        ok = r.status_code == 200 and "login" not in r.url.lower() and "cas" not in r.url.lower()
        self.log(f"[直连] check_login: {r.status_code}, len={len(r.text)}, ok={ok}")
        return ok

    def init(self) -> bool:
        """GET 选课索引页，提取所有 hidden input 到 stores，并解析全部选课 Tab。"""
        r = self.s.get(self.base + INDEX_URL, headers=self._h(self.base + "xtgl/index_initMenu.html?jsdm=xs"), timeout=20)
        txt = r.text
        self._last_index_html = txt
        self.log(f"[直连] init GET: {r.status_code}, len={len(txt)}")
        if "firstXkkzId" not in txt:
            self.log("[直连] init: 页面无 firstXkkzId（未开放或入口不对）")
            return False
        for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', txt, re.I):
            tag = m.group(0)
            nm = re.search(r'name="([^"]+)"', tag)
            vl = re.search(r'value="([^"]*)"', tag)
            if nm:
                self.stores[nm.group(1)] = vl.group(1) if vl else ""
        keys = ["firstXkkzId", "xkxnm", "xkxqm", "njdm_id", "zyh_id", "xbm", "ccdm",
                "firstKklxdm", "jg_id_1", "xsbj", "mzm", "xz", "bh_id", "xqh_id",
                "zyfx_id", "xslbdm", "bklx_id"]
        got = {k: self.stores.get(k, "") for k in keys}
        self.log(f"[直连] init OK: firstXkkzId={got['firstXkkzId'][:8]}... xkxnm={got['xkxnm']} xkxqm={got['xkxqm']} "
                 f"njdm_id={got['njdm_id']} zyh_id={got['zyh_id'][:6]}...")
        # 解析全部选课 Tab：kklxdm -> (xkkz_id, 名称)。体育/英语/思政/通识等是独立轮次，
        # 只用 firstXkkzId（主修）搜不到体育分项(05)/英语分项(07)等。
        self.tabs = []
        for m in re.finditer(
            r"queryCourse\(this,'(\d+)','([0-9A-F]+)','(\d+)','(\d+)'\)[^>]*>([^<]+)</a>", txt):
            kklx, xkkz, njdm, zyh, name = m.groups()
            self.tabs.append({"kklxdm": kklx, "xkkz_id": xkkz, "njdm_id": njdm,
                              "zyh_id": zyh, "name": name})
        self.log(f"[直连] 选课 Tab: " + ", ".join(f"{t['name']}({t['kklxdm']})" for t in self.tabs))
        return True

    def fetch_selected_courses(self, enrich: bool = True) -> dict:
        """Return the authoritative selected-course table from the index page."""
        if not self.stores and not self.init():
            return {"count": 0, "credits": "", "courses": []}
        data = {
            "jg_id": self.stores.get("jg_id_1", ""),
            "zyh_id": self.stores.get("zyh_id", ""),
            "njdm_id": self.stores.get("njdm_id", ""),
            "zyfx_id": self.stores.get("zyfx_id", ""),
            "bh_id": self.stores.get("bh_id", ""),
            "xkxnm": self.stores.get("xkxnm", ""),
            "xkxqm": self.stores.get("xkxqm", ""),
            "xkly": self.stores.get("xkly", ""),
        }
        r = self.s.post(self.base + SELECTED_DISPLAY_URL, data=data,
                        headers=self._h(self.base + INDEX_URL), timeout=20)
        try:
            payload = r.json()
        except Exception:
            payload = None
        result = (parse_selected_courses_json(payload) if isinstance(payload, list)
                  else parse_selected_courses_html(r.text))
        if enrich:
            for course in result["courses"]:
                if course.get("course_name") or not course.get("course_code"):
                    continue
                rows, _tab = self._search_all_tabs(course["course_code"])
                exact = next((row for row in rows
                              if row.get("jxbmc") == course.get("teaching_class")), None)
                row = exact or (rows[0] if rows else None)
                if row:
                    course["course_name"] = row.get("kcmc", "")
        self.log(f"[已选课程] 共 {result['count']} 门，{result['credits'] or '?'} 学分")
        return result

    def _part_display(self, q: str, page: int = 1, size: int = 15, kklxdm: str = None,
                      xkkz_id: str = None) -> list:
        """POST PartDisplay -> 课程/教学班列表（裸数组）。

        上游 Rust 期望 {tmpList:[...]}，浙江工商实际返回裸数组。
        kklxdm/xkkz_id 传 None 时用 stores 里的默认值（主修课程 01）。
        """
        data = {
            "filter_list[0]": q,
            "xbm": self.stores.get("xbm", ""), "ccdm": self.stores.get("ccdm", ""),
            "kklxdm": kklxdm if kklxdm is not None else self.stores.get("firstKklxdm", ""),
            "xkkz_id": xkkz_id if xkkz_id is not None else self.stores.get("firstXkkzId", ""),
            "xkxnm": self.stores.get("xkxnm", ""), "xkxqm": self.stores.get("xkxqm", ""),
            "jg_id": self.stores.get("jg_id_1", ""), "xsbj": self.stores.get("xsbj", ""),
            "mzm": self.stores.get("mzm", ""), "xz": self.stores.get("xz", ""),
            "bh_id": self.stores.get("bh_id", ""), "xqh_id": self.stores.get("xqh_id", ""),
            "zyfx_id": self.stores.get("zyfx_id", ""), "xslbdm": self.stores.get("xslbdm", ""),
            "kspage": str(page), "jspage": str(size),
        }
        r = self.s.post(self.base + PART_DISPLAY_URL, data=data, headers=self._h(self.base + INDEX_URL), timeout=15)
        try:
            js = r.json()
            if isinstance(js, dict):
                js = js.get("tmpList") or js.get("rows") or []
            return js if isinstance(js, list) else []
        except Exception as e:
            self.log(f"[直连] PartDisplay 解析失败: {r.status_code} {r.text[:120]} ({e})")
            return []

    def _search_all_tabs(self, q: str) -> list:
        """跨全部选课 Tab 搜索：主修搜不到就试体育/英语/思政/通识等。返回 (rows, tab)。"""
        if not getattr(self, "tabs", None):
            self.init()
        for tab in self.tabs:
            rows = self._part_display(q, kklxdm=tab["kklxdm"], xkkz_id=tab["xkkz_id"])
            if rows:
                self.log(f"[直连] {q!r} 在 Tab「{tab['name']}」命中 {len(rows)} 条")
                return rows, tab
        return [], None

    def fetch_course(self, q: str) -> Course:
        if not self.stores:
            self.init()
        rows, tab = self._search_all_tabs(q)
        kch = rows[0].get("kch_id", "") if rows else ""
        kch_code = (rows[0].get("kch", "") or rows[0].get("course_code", "")) if rows else ""
        kcmc = rows[0].get("kcmc", "") if rows else ""
        tab_name = tab["name"] if tab else ""
        self.log(f"[直连] fetch {q!r} -> kch_id={kch}, 课程号={kch_code}, kcmc={kcmc}, rows={len(rows)}, tab={tab_name or '无'}")
        if not kch:
            return Course(kcmc=kcmc, tab_name=tab_name, kch=kch_code)
        # 用命中的 Tab 参数（体育/英语/通识是独立轮次，必须用各自 xkkz_id/kklxdm）
        cur_kklx = tab["kklxdm"] if tab else self.stores.get("firstKklxdm", "")
        cur_xkkz = tab["xkkz_id"] if tab else self.stores.get("firstXkkzId", "")
        data = {
            "filter_list[0]": q,
            "xkxqm": self.stores.get("xkxqm", ""), "xkxnm": self.stores.get("xkxnm", ""),
            "xkkz_id": cur_xkkz,
            "bklx_id": self.stores.get("bklx_id", ""), "kch_id": kch,
            "njdm_id": self.stores.get("njdm_id", ""), "xsbj": self.stores.get("xsbj", ""),
            "xz": self.stores.get("xz", ""), "mzm": self.stores.get("mzm", ""),
            "kklxdm": cur_kklx, "bh_id": self.stores.get("bh_id", ""),
            "xqh_id": self.stores.get("xqh_id", ""), "xslbdm": self.stores.get("xslbdm", ""),
            "zyfx_id": self.stores.get("zyfx_id", ""), "jg_id": self.stores.get("jg_id_1", ""),
            "ccdm": self.stores.get("ccdm", ""), "xbm": self.stores.get("xbm", ""),
        }
        r = self.s.post(self.base + QUERY_DO_URL, data=data, headers=self._h(self.base + INDEX_URL), timeout=15)
        try:
            lst = r.json()
        except Exception:
            self.log(f"[直连] QueryDo 非 JSON: {r.status_code} {r.text[:150]}")
            return Course()
        jxbs = []
        for item in lst or []:
            jxbs.append(Jxb(jxb_id=item.get("jxb_id", ""), do_id=item.get("do_jxb_id", ""),
                            jxbmc=item.get("jxbmc", ""),
                            jsxx=item.get("jsxx", ""), sksj=item.get("sksj", ""),
                            yxzrs=str(item.get("yxzrs", "")), jxbrl=str(item.get("jxbrl", "")),
                            xqumc=str(item.get("xqumc", "") or ""),
                            jxdd=str(item.get("jxdd", "") or "")))
        self.log(f"[直连] 查询到 {len(jxbs)} 个教学班")
        return Course(xkkz_id=cur_xkkz, kch_id=kch, kcmc=kcmc, tab_name=tab_name, jxb=jxbs,
                      kch=kch_code)

    def fetch_all_courses(self, page_size: int = 100, max_pages: int = 200, log=None) -> list:
        """跨所有选课 Tab 分页拉取全部教学班（PartDisplay 空查询）。"""
        log = log or self.log
        if not self.stores:
            self.init()
        tabs = getattr(self, "tabs", None) or [{
            "kklxdm": self.stores.get("firstKklxdm", ""),
            "xkkz_id": self.stores.get("firstXkkzId", ""),
            "name": "默认课程",
        }]
        all_rows, seen = [], set()
        for tab in tabs:
            tab_count, total = 0, None
            for page in range(1, max_pages + 1):
                rows = self._part_display("", page=page, size=page_size,
                                           kklxdm=tab.get("kklxdm"),
                                           xkkz_id=tab.get("xkkz_id"))
                if not rows:
                    break
                for row in rows:
                    row["_course_tab"] = dict(tab)
                    key = row.get("jxb_id") or (row.get("kch_id", ""),
                          row.get("jxbmc", ""), tab.get("kklxdm", ""), tab.get("xkkz_id", ""))
                    if key not in seen:
                        seen.add(key)
                        all_rows.append(row)
                        tab_count += 1
                total = total or rows[0].get("totalResult") or rows[0].get("queryModel", {}).get("totalResult")
                log(f"[全部课程] Tab「{tab.get('name','')}」第 {page} 页 {len(rows)} 条")
                if total is not None:
                    try:
                        if page * page_size >= int(total):
                            break
                    except Exception:
                        pass
                if len(rows) < page_size:
                    break
            log(f"[全部课程] Tab「{tab.get('name','')}」完成：{tab_count} 条")
        log(f"[全部课程] 跨 {len(tabs)} 个 Tab 合并完成：{len(all_rows)} 条教学班")
        return all_rows

    def _query_do_raw(self, kch_id: str, keyword: str, session=None, tab=None) -> list:
        """对单个课程调 QueryDo，返回教学班详情（含 sksj/jxdd/jsxx 等）。"""
        data = {
            "filter_list[0]": keyword,
            "xkxqm": self.stores.get("xkxqm", ""), "xkxnm": self.stores.get("xkxnm", ""),
            "xkkz_id": (tab or {}).get("xkkz_id") or self.stores.get("firstXkkzId", ""),
            "bklx_id": self.stores.get("bklx_id", ""), "kch_id": kch_id,
            "njdm_id": self.stores.get("njdm_id", ""), "xsbj": self.stores.get("xsbj", ""),
            "xz": self.stores.get("xz", ""), "mzm": self.stores.get("mzm", ""),
            "kklxdm": (tab or {}).get("kklxdm") or self.stores.get("firstKklxdm", ""), "bh_id": self.stores.get("bh_id", ""),
            "xqh_id": self.stores.get("xqh_id", ""), "xslbdm": self.stores.get("xslbdm", ""),
            "zyfx_id": self.stores.get("zyfx_id", ""), "jg_id": self.stores.get("jg_id_1", ""),
            "ccdm": self.stores.get("ccdm", ""), "xbm": self.stores.get("xbm", ""),
        }
        s = session or self.s
        r = s.post(self.base + QUERY_DO_URL, data=data, headers=self._h(self.base + INDEX_URL), timeout=15)
        try:
            lst = r.json()
            return lst if isinstance(lst, list) else []
        except Exception as e:
            self.log(f"[直连] QueryDo({kch_id[:8]}) 非 JSON: {r.status_code} {r.text[:100]} ({e})")
            return []

    def _new_session(self) -> "requests.Session":
        s = requests.Session()
        for kv in self.cookie.split(";"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                s.cookies.set(k.strip(), v.strip(), domain="jwxt.zjgsu.edu.cn")
        return s

    def fetch_all_courses_detailed(self, page_size: int = 1000, max_pages: int = 200,
                                   workers: int = 8, log=None) -> list:
        """全量拉取 + 并行补详情：时间/教室/教师/人数/学院，按 jxb_id 回填。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        log = log or self.log
        base_rows = self.fetch_all_courses(page_size=page_size, max_pages=max_pages, log=log)
        if not base_rows:
            return []

        # 按 (Tab, course) 分组；不同选课类别的参数不能混用。
        kch_map = {}
        for r in base_rows:
            kch = r.get("kch_id", "")
            tab = r.get("_course_tab", {})
            key = (tab.get("kklxdm", ""), tab.get("xkkz_id", ""), kch)
            if kch and key not in kch_map:
                kch_map[key] = (r.get("kcmc", ""), tab)
        uniq = sorted(kch_map.keys())
        log(f"[详情] {len(base_rows)} 个教学班 / {len(uniq)} 个 Tab-课程组合，开始并行补详情（{workers} 线程）…")

        results = {}
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._query_do_raw, key[2], kch_map[key][0],
                                    self._new_session(), kch_map[key][1]): key
                       for key in uniq}
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    results[key] = fut.result()
                except Exception as e:
                    log(f"[详情] {key[2][:8]} 查询异常: {e}")
                    results[key] = []
                done += 1
                if done % 100 == 0:
                    log(f"[详情] 已补 {done}/{len(uniq)}")

        # 详情按 jxb_id 索引
        detail_by_jxb = {}
        for key, lst in results.items():
            for it in lst:
                jxb = it.get("jxb_id", "")
                if jxb:
                    detail_by_jxb[(key[0], key[1], jxb)] = it

        # 回填
        filled = 0
        for r in base_rows:
            tab = r.get("_course_tab", {})
            d = detail_by_jxb.get((tab.get("kklxdm", ""), tab.get("xkkz_id", ""), r.get("jxb_id", "")))
            if d:
                for k in ("sksj", "jxdd", "jsxx", "yxzrs", "jxbrl", "kkxymc",
                          "kcxzmc", "kclbmc", "jxms", "xqumc"):
                    r[k] = d.get(k, "")
                r["do_id"] = d.get("do_jxb_id", "")
                filled += 1
        log(f"[详情] 回填完成：{filled}/{len(base_rows)} 条带详情")
        return base_rows

    def select_course(self, kch_id: str, do_id: str, xkkz_id: str = None) -> tuple:
        data = {
            "jxb_ids": do_id,
            "kch_id": kch_id,
            "qz": "0",
            "njdm_id": self.stores.get("njdm_id", ""),
            "zyh_id": self.stores.get("zyh_id", ""),
        }
        if xkkz_id:
            data["xkkz_id"] = xkkz_id
        r = self.s.post(self.base + SELECT_URL, data=data, headers=self._h(self.base + INDEX_URL), timeout=15)
        try:
            js = r.json()
            flag = js.get("flag", "")
            msg = js.get("msg")
            self.log(f"[直连] select: flag={flag}, msg={msg}")
            # 教务对不同轮次返回的格式不一致（保底志愿轮次会返回 "0,<教学班id>,<容量>"
            # 这种没有中文提示的串）。首次遇到某种返回时把完整原文落盘，
            # 方便事后判定到底是“已成功”还是“已满”，且不重复刷日志。
            signature = f"{flag}|{msg}"
            if signature not in self._select_signatures:
                self._select_signatures.add(signature)
                self.log(f"[直连] select 原始返回（首次）: HTTP {r.status_code} {r.text[:300]}")
            return flag, msg
        except Exception:
            self.log(f"[直连] select 非 JSON: {r.status_code} {r.text[:200]}")
            return "", r.text[:200]


def capture_cookie_from_edge(port: int = DEBUG_PORT, log=None) -> str:
    log = log or (lambda m: None)
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
    tab = next((t for t in tabs if t.get("type") == "page"), None)
    if not tab:
        raise RuntimeError("未找到 Edge 页面")
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=15)
    ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == 1:
            break
    ws.send(json.dumps({"id": 2, "method": "Network.getCookies", "params": {"urls": [BASE]}}))
    cookies = []
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == 2:
            cookies = r.get("result", {}).get("cookies", [])
            break
    ws.close()
    parts = []
    for c in cookies:
        if c.get("domain", "").endswith("zjgsu.edu.cn"):
            parts.append(f"{c['name']}={c['value']}")
    cookie = "; ".join(parts)
    names = [c["name"] for c in cookies if c.get("domain", "").endswith("zjgsu.edu.cn")]
    log(f"[抓取] 共 {len(names)} 条: {', '.join(names)}")
    return cookie
