"""离线验证扩展入口、凭据域限制及浙工商查询/提交/对账链路。"""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import school_adapter
from school_adapter import Course, Jxb, create_adapter, register_adapter
import zjgsu_api
import zjgsu_launcher as launcher


class SchoolAdapterTests(unittest.TestCase):
    def setUp(self):
        registry = patch.dict(school_adapter._FACTORIES)
        registry.start()
        self.addCleanup(registry.stop)

    def test_existing_imports_and_default_client_keep_cookie_scope(self):
        self.assertIs(zjgsu_api.Course, Course)
        self.assertIs(zjgsu_api.Jxb, Jxb)
        client = launcher.make_client(zjgsu_api.BASE, "JSESSIONID=fixture", lambda _: None)
        self.addCleanup(client.s.close)
        self.assertIsInstance(client, zjgsu_api.ZjgsuClient)
        self.assertEqual(client.base, zjgsu_api.BASE)
        self.assertEqual([(c.name, c.domain) for c in client.s.cookies],
                         [("JSESSIONID", "jwxt.zjgsu.edu.cn")])
        session = client._new_session()
        self.addCleanup(session.close)
        self.assertEqual([(c.name, c.domain) for c in session.cookies],
                         [("JSESSIONID", "jwxt.zjgsu.edu.cn")])

    def test_unknown_school_does_not_fall_back_to_zjgsu(self):
        with patch("zjgsu_api.requests.Session") as session:
            with self.assertRaisesRegex(ValueError, "尚未适配学校"):
                create_adapter("fixture", school_id="unsupported")
        session.assert_not_called()

    def test_default_adapter_rejects_other_hosts_before_session_creation(self):
        with patch("zjgsu_api.requests.Session") as session:
            for base in ("https://other.example/jwglxt/",
                         "http://jwxt.zjgsu.edu.cn/jwglxt/",
                         "https://jwxt.zjgsu.edu.cn/other/"):
                with self.subTest(base=base):
                    with self.assertRaises(ValueError):
                        create_adapter("JSESSIONID=fixture", base_url=base)
                    with self.assertRaises(ValueError):
                        launcher.normalize_base(base)
        session.assert_not_called()

    def test_registration_cannot_replace_builtin_adapter(self):
        with self.assertRaisesRegex(ValueError, "已注册"):
            register_adapter("zjgsu", Mock())
        for school_id in ("", " example "):
            with self.assertRaises(ValueError):
                register_adapter(school_id, Mock())
        with self.assertRaises(TypeError):
            register_adapter("example", None)

    def test_registered_adapter_runs_through_launcher_helpers(self):
        course = Course(xkkz_id="round", kch_id="course", kcmc="示例课程",
                        jxb=[Jxb("class", "submission", jxbmc="示例教学班")])
        client = Mock()
        client.fetch_course.return_value = course
        client.select_course.return_value = ("1", "提交成功")
        factory = Mock(return_value=client)
        register_adapter("example", factory)
        log = Mock()
        actual = launcher.make_client("https://example.invalid/", "fixture", log,
                                      school_id="example")
        factory.assert_called_once_with(cookie="fixture", base_url="https://example.invalid/", log=log)
        result = launcher.fetch_course(actual, "示例课程")
        self.assertEqual(launcher.select_jxb(actual, result.course, result.jxbs[0], log),
                         ("1", "提交成功"))
        client.select_course.assert_called_once_with("course", "submission", xkkz_id="round")

    def test_zjgsu_query_submit_and_selected_keep_tab_context(self):
        client = create_adapter("JSESSIONID=fixture")
        self.addCleanup(client.s.close)
        html = (
            '<input type="hidden" name="firstXkkzId" value="AAAA">'
            '<input type="hidden" name="xkxnm" value="2026">'
            '<input type="hidden" name="xkxqm" value="1">'
            '<a onclick="queryCourse(this,\'01\',\'AAAA\',\'2026\',\'123\')">主修课程</a>'
            '<a onclick="queryCourse(this,\'10\',\'BBBB\',\'2026\',\'123\')">通识选修课</a>'
        )
        row = {"kch_id": "course-id", "kch": "COURSE01", "kcmc": "示例课程"}
        teaching_class = "(2026-2027-1)-COURSE01-01"
        detail = {"jxb_id": "class-id", "do_jxb_id": "submission-id",
                  "jxbmc": teaching_class, "sksj": "星期一第1-2节{1-16周}",
                  "yxzrs": "20", "jxbrl": "30"}
        posts = []

        def post(url, *, data, **kwargs):
            posts.append((url, dict(data)))
            if "PartDisplay" in url:
                return Mock(json=lambda: [] if data["kklxdm"] == "01" else [row])
            if "cxJxbWithKch" in url:
                self.assertEqual(data["xkkz_id"], "BBBB")
                return Mock(json=lambda: [detail])
            if "xkBcZy" in url:
                self.assertEqual(data["jxb_ids"], "submission-id")
                self.assertEqual(data["xkkz_id"], "BBBB")
                return Mock(json=lambda: {"flag": "1", "msg": "提交成功"},
                            status_code=200, text='{"flag":"1","msg":"提交成功"}')
            if "ChoosedDisplay" in url:
                return Mock(json=lambda: [dict(detail, jxbmc="【示例课程】" + teaching_class,
                                               kch_id="course-id", xkkz_id="BBBB", sxbj="1", xf="2")])
            self.fail(f"Unexpected URL: {url}")

        with patch.object(client.s, "get", return_value=Mock(text=html, status_code=200)), \
             patch.object(client.s, "post", side_effect=post):
            self.assertTrue(client.init())
            result = launcher.fetch_course(client, "示例课程")
            self.assertEqual(result.course.tab_name, "通识选修课")
            self.assertEqual(launcher.select_jxb(client, result.course, result.jxbs[0], lambda _: None),
                             ("1", "提交成功"))
            selected = client.fetch_selected_courses()
        self.assertEqual(selected["courses"][0]["teaching_class"], teaching_class)
        self.assertEqual(selected["courses"][0]["course_name"], "示例课程")
        self.assertEqual(selected["courses"][0]["status"], "已选上")
        self.assertEqual(selected["count"], 1)
        self.assertEqual(len(posts), 5)


if __name__ == "__main__":
    unittest.main()
