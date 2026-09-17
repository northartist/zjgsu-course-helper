from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path

DEFAULT_TARGETS = {"EN": 1, "PE": 1, "GE": 2}


# 教学班名可能带前缀：校区（教工路(...)）、网课平台（智慧树网络课(...)）、课程别名（国情课(...)、
# 影视鉴赏(...)…）。同一个班，教务有时带前缀、有时不带 —— 所以"是不是同一个班"必须按
# **核心教学班号**（学期 + 课程号 + 班号）比，不能比整串字符串。
# 2026-09-17 用户实测：已选列表里"中国城市经济与发展"出现了两次
# （国情课(2026-2027-1)-GENEML053-01 与 (2026-2027-1)-GENEML053-01 被当成两门课）。
TEACHING_CLASS_CORE_RE = re.compile(r"\((\d{4})-(\d{4})-(\d)\)-([A-Za-z0-9]+)-([A-Za-z0-9]+)")


def teaching_class_core(value: str) -> str:
    """教学班名的核心部分（学期+课程号+班号）；不是标准教学班名就返回去空白后的原串。"""
    text = str(value or "").strip()
    match = TEACHING_CLASS_CORE_RE.search(text)
    return match.group(0) if match else text


def timetable_slots(courses: list[dict]) -> list[dict]:
    day_numbers = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
    slots = []
    pattern = re.compile(r"星期([一二三四五六日天])第(\d+)(?:-(\d+))?节\{([^}]*)\}")
    for course in courses:
        for match in pattern.finditer(str(course.get("time") or "")):
            start = int(match.group(2))
            slots.append({
                "course_name": course.get("course_name") or course.get("teaching_class") or "未命名课程",
                "day": day_numbers[match.group(1)],
                "start": start,
                "end": int(match.group(3) or start),
                "weeks": match.group(4),
            })
    return slots


def layout_timetable_slots(slots: list[dict]) -> list[dict]:
    """Assign visual lanes per connected overlap group so blocks never cover each other."""
    result = []
    for day in range(1, 6):
        day_slots = [dict(slot) for slot in slots if slot.get("day") == day]
        day_slots.sort(key=lambda item: (item.get("start", 0), item.get("end", 0)))
        index = 0
        while index < len(day_slots):
            component = [day_slots[index]]
            max_end = day_slots[index].get("end", 0)
            index += 1
            while index < len(day_slots) and day_slots[index].get("start", 0) <= max_end:
                component.append(day_slots[index])
                max_end = max(max_end, day_slots[index].get("end", 0))
                index += 1
            lanes_end = []
            for slot in component:
                lane = next((i for i, end in enumerate(lanes_end)
                              if end < slot.get("start", 0)), len(lanes_end))
                if lane == len(lanes_end):
                    lanes_end.append(slot.get("end", 0))
                else:
                    lanes_end[lane] = slot.get("end", 0)
                slot["lane"] = lane
                slot["lanes"] = len(lanes_end)
            # 统一该重叠组的列数；不会影响后续不相交的组。
            for slot in component:
                slot["lanes"] = len(lanes_end)
                result.append(slot)
    return result


def parse_target(raw: str) -> tuple[str, str]:
    value = (raw or "").strip()
    for prefix in ("GE", "EN", "PE"):
        if value.startswith(prefix + ":"):
            return value[len(prefix) + 1:].strip(), prefix
    return value, "OTHER"


def completion_snapshot(selected: list[dict], targets: dict | None = None) -> dict:
    targets = dict(targets or DEFAULT_TARGETS)
    counts = {category: 0 for category in targets}
    seen = set()
    for item in selected:
        category = item.get("category")
        keyword = item.get("keyword") or item.get("teaching_class")
        key = (category, keyword)
        if category in counts and key not in seen:
            seen.add(key)
            counts[category] += 1
    progress = {category: (min(counts[category], target), target)
                for category, target in targets.items()}
    return {
        "completed": all(done >= target for done, target in progress.values()),
        "progress": progress,
        "selected_count": len(selected),
    }


class CourseStateStore:
    def __init__(self, pending_path: Path | str, selected_path: Path | str,
                 targets: dict | None = None):
        self.pending_path = Path(pending_path)
        self.selected_path = Path(selected_path)
        self.targets = dict(targets or DEFAULT_TARGETS)
        self._lock = threading.RLock()

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)

    def pending(self) -> list[str]:
        with self._lock:
            if not self.pending_path.exists():
                return []
            return [line.strip() for line in self.pending_path.read_text(encoding="utf-8-sig").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]

    def selected(self) -> list[dict]:
        with self._lock:
            if not self.selected_path.exists():
                return []
            try:
                data = json.loads(self.selected_path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except (json.JSONDecodeError, OSError, UnicodeError):
                return []

    def replace_pending(self, raws: list[str]) -> None:
        with self._lock:
            comments = []
            if self.pending_path.exists():
                comments = [line for line in self.pending_path.read_text(encoding="utf-8-sig").splitlines()
                            if line.lstrip().startswith("#")]
            lines = comments + [raw.strip() for raw in raws if raw and raw.strip()]
            self._atomic_write(self.pending_path, "\n".join(lines).rstrip() + "\n")

    def _remove_pending(self, raw: str) -> None:
        if not self.pending_path.exists():
            return
        wanted_keyword, wanted_category = parse_target(raw)
        kept = []
        for line in self.pending_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                keyword, category = parse_target(stripped)
                if keyword == wanted_keyword and category == wanted_category:
                    continue
            kept.append(line)
        self._atomic_write(self.pending_path, "\n".join(kept).rstrip() + "\n")

    def _remove_category_pending(self, wanted_category: str) -> None:
        if not self.pending_path.exists():
            return
        kept = []
        for line in self.pending_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                _keyword, category = parse_target(stripped)
                if category == wanted_category:
                    continue
            kept.append(line)
        self._atomic_write(self.pending_path, "\n".join(kept).rstrip() + "\n")

    def mark_completed(self, raw: str, course_info: dict | None = None,
                       source: str = "assistant") -> dict:
        with self._lock:
            keyword, category = parse_target(raw)
            records = self.selected()
            record = dict(course_info or {})
            record.update({"keyword": keyword, "category": category, "source": source})
            identity = record.get("teaching_class") or keyword
            records = [item for item in records
                       if (item.get("category"), item.get("teaching_class") or item.get("keyword"))
                       != (category, identity)]
            records.append(record)
            self._atomic_write(self.selected_path, json.dumps(records, ensure_ascii=False, indent=2) + "\n")
            self._remove_pending(raw)
            snapshot = completion_snapshot(records, self.targets)
            done, target = snapshot["progress"].get(category, (0, 0))
            if target and done >= target:
                self._remove_category_pending(category)
            return snapshot

    def reconcile_system_selected(self, courses: list[dict]) -> list[str]:
        with self._lock:
            by_class = {item.get("teaching_class"): item for item in courses if item.get("teaching_class")}
            # 前缀变体（国情课(...) / 智慧树网络课(...) / 教工路(...)）也算同一个班：
            # 只比整串的话，教务已选里的课会一直挂在待选列表里。
            by_core = {teaching_class_core(item.get("teaching_class")): item
                       for item in courses if item.get("teaching_class")}
            # 名称类待选（GE:加工食品与健康生活）没有教学班号，只按教学班对账会永远匹配不上，
            # 于是教务那边已经选上的课会一直挂在待选列表里；这里补一条按课程名的对账。
            by_name = {}
            for item in courses:
                name = str(item.get("course_name") or "").strip()
                if name:
                    by_name.setdefault(name, item)
            moved = []
            for raw in list(self.pending()):
                keyword, _category = parse_target(raw)
                hit = (by_class.get(keyword) or by_core.get(teaching_class_core(keyword))
                       or by_name.get(keyword))
                if hit:
                    self.mark_completed(raw, hit, source="system")
                    moved.append(keyword)
            return moved

    def reconcile_completed_pending(self) -> list[str]:
        """把"本程序已经抢到（selected 里有记录）"却还留在待选列表里的条目清掉。

        历史版本把整行展示文字当关键字落盘，mark_completed 的 _remove_pending 对不上号，
        于是抢到的课一直挂在待选列表里；这里按教学班号/关键字做一次自愈。
        """
        with self._lock:
            done_classes, done_keywords = set(), set()
            for record in self.selected():
                if record.get("teaching_class"):
                    done_classes.add(str(record["teaching_class"]).strip())
                keyword = str(record.get("keyword") or "").strip()
                if keyword:
                    done_keywords.add(keyword)
            if not done_classes and not done_keywords:
                return []
            # 前缀变体也算同一个班（国情课(...)/(...) 是同一门课）
            done_cores = {teaching_class_core(item) for item in done_classes if item}
            kept, removed = [], []
            for raw in self.pending():
                keyword, _category = parse_target(raw)
                if keyword and (keyword in done_classes or keyword in done_keywords
                                or teaching_class_core(keyword) in done_cores):
                    removed.append(keyword)
                    continue
                kept.append(raw)
            if removed:
                self.replace_pending(kept)
            return removed

    def demote_to_pending(self, entries: list[dict]) -> list[str]:
        """把"本地记为已选、但教务已选里已经不存在"的课程放回待选列表。

        典型场景：志愿没抽中、被退课、教务那边把它退了。
        同时把这条"已选中"记录撤销（进度条也要退回），返回被放回的课程名。
        """
        with self._lock:
            if not entries:
                return []
            raws = list(self.pending())
            existing = {parse_target(raw) for raw in raws}
            restored, drop = [], set()
            for record in entries:
                category = str(record.get("category") or "OTHER").upper()
                identity = str(record.get("teaching_class") or "").strip()
                keyword = str(record.get("keyword") or "").strip()
                if not identity and not keyword:
                    continue          # 没有可识别的身份，不敢乱放
                drop.add((record.get("category"), identity or keyword))
                raw = (f"{category}:{identity}" if category in {"GE", "EN", "PE"} and identity
                       else (identity or keyword))
                key = parse_target(raw)
                if key in existing:
                    continue
                raws.append(raw)
                existing.add(key)
                restored.append(record.get("course_name") or identity or keyword)
            if drop:
                kept = [item for item in self.selected()
                        if (item.get("category"),
                            str(item.get("teaching_class") or item.get("keyword") or "").strip()) not in drop]
                self._atomic_write(self.selected_path,
                                   json.dumps(kept, ensure_ascii=False, indent=2) + "\n")
            if restored:
                self.replace_pending(raws)
            return restored

    def snapshot(self) -> dict:
        result = completion_snapshot(self.selected(), self.targets)
        result["pending"] = self.pending()
        return result
