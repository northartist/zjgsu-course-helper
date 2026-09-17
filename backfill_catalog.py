# -*- coding: utf-8 -*-
"""回填 course_catalog.json 缺失的分类字段（kklxdm/course_tab/kclbmc 等）。
数据源：legacy_exports/浙江工商全部课程-全类别.xlsx（同批 2761 门教学班，100% 键匹配）。
"""
import json
import os
import pathlib
import shutil

import openpyxl

# 数据目录与主程序保持一致：默认 %LOCALAPPDATA%\工商大学选课助手，
# 可用环境变量 ZJGSU_HELPER_DATA 指向自定义目录（在别的机器上跑维护脚本时用）。
_data_root = os.environ.get("ZJGSU_HELPER_DATA")
if not _data_root:
    _local = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData" / "Local")
    _data_root = str(pathlib.Path(_local) / "工商大学选课助手")
DATA_DIR = pathlib.Path(_data_root)
CATALOG = DATA_DIR / "course_catalog.json"
XLSX = DATA_DIR / "legacy_exports" / "浙江工商全部课程-全类别.xlsx"

# ---- 1. 备份 ----
bak = CATALOG.with_suffix(".json.bak_20260909")
if not bak.exists():
    shutil.copy2(CATALOG, bak)
    print("备份 ->", bak)

# ---- 2. 读 catalog ----
cat = json.loads(CATALOG.read_text(encoding="utf-8"))
print("catalog 条目:", len(cat))

# ---- 3. 读 xlsx 建立 教学班->行 索引 ----
wb = openpyxl.load_workbook(XLSX, read_only=True)
ws = wb.active
rows = ws.iter_rows(values_only=True)
header = list(next(rows))
idx = {name: i for i, name in enumerate(header)}
print("xlsx 列:", header)
xl = {}
for r in rows:
    if r[idx["教学班名称"]]:
        xl[str(r[idx["教学班名称"]])] = r
wb.close()
print("xlsx 教学班数:", len(xl))

# ---- 4. 回填 ----
updated = 0
for key, value in cat.items():
    r = xl.get(key)
    if not r:
        continue
    dirty = False
    code = str(r[idx["选课类别代码"]] or "").strip()
    tab_name = str(r[idx["选课类别"]] or "").strip()
    if code and not value.get("kklxdm"):
        value["kklxdm"] = code
        dirty = True
    if tab_name:
        if not value.get("course_tab"):
            value["course_tab"] = tab_name
            dirty = True
        # course_group 以 kclbmc/course_group 为准；旧缓存两者皆空，用类别名兜底
        if not (value.get("course_group") or value.get("kclbmc")):
            value["course_group"] = tab_name
            value["kclbmc"] = tab_name
            dirty = True
    # 已选/容量 "32/32" -> yixuan/rongliang（旧缓存缺）
    selcap = str(r[idx["已选/容量"]] or "").strip()
    if selcap and "/" in selcap:
        yx, cap = selcap.split("/", 1)
        if not value.get("yixuan") and yx.isdigit():
            value["yixuan"] = yx
            dirty = True
        if not value.get("rongliang") and cap.isdigit():
            value["rongliang"] = cap
            dirty = True
    # 教学班 ID（旧缓存缺 jxb_id，提交时要用）
    if not value.get("jxb_id") and r[idx["教学班ID"]]:
        value["jxb_id"] = str(r[idx["教学班ID"]]).strip()
        dirty = True
    if dirty:
        updated += 1

tmp = CATALOG.with_suffix(".json.tmp")
tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
import os
os.replace(tmp, CATALOG)
print(f"回填完成：{updated}/{len(cat)} 条被补齐")

# ---- 5. 校验 ----
cat2 = json.loads(CATALOG.read_text(encoding="utf-8"))
from collections import Counter
c = Counter()
for v in cat2.values():
    c[v.get("kklxdm", "(空)")] += 1
print("kklxdm 分布:", dict(c))
no_tab = sum(1 for v in cat2.values() if not v.get("course_tab"))
print("仍缺 course_tab:", no_tab)
