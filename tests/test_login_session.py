"""Offline login fixtures are synthetic: they are not SFC endpoint/schema evidence."""
from __future__ import annotations

import io
import json
import unittest
from unittest.mock import Mock, patch

import requests

import login_session as auth
from school_adapter import create_adapter
from sfc_api import BASE as SFC_BASE, LOGIN_URL, SfcClient
import zjgsu_api
import zjgsu_launcher as launcher


FIXTURE_HOME = SFC_BASE + "fixture/authenticated"  # Synthetic, never a production default.
FIXTURE_BODY = '<main data-fixture-session="authenticated">fixture account</main>'


def response(url=FIXTURE_HOME, body=FIXTURE_BODY, status=200, headers=None):
    result = requests.Response()
    result.url = url
    result.request = requests.Request("GET", url).prepare()
    result.status_code = status
    result._content = body.encode("utf-8")
    result.encoding = "utf-8"
    result.headers.update(headers or {})
    return result


def fixture_probe(url=FIXTURE_HOME):
    return auth.SessionProbe(url, lambda r: 'data-fixture-session="authenticated"' in r.text)


class LoginSessionTests(unittest.TestCase):
    def setUp(self):
        # Fail the test on unexpected HTTP. CDP calls are mocked separately.
        no_network = patch("requests.adapters.HTTPAdapter.send",
                           side_effect=AssertionError("Offline tests must not access the network"))
        self.transport = no_network.start()
        self.addCleanup(no_network.stop)

    def client(self, **kwargs):
        client = SfcClient("fixture_session=fixture-secret", **kwargs)
        self.addCleanup(client.s.close)
        return client

    def test_sfc_factory_has_own_base_cookie_scope_and_no_eager_login(self):
        with patch("login_session.SchoolSession.send", side_effect=AssertionError("No eager request")):
            client = launcher.make_client(None, "fixture_session=value", Mock(), school_id="sfc")
            self.addCleanup(client.s.close)
        self.assertIsInstance(client, SfcClient)
        self.assertEqual(client.base, SFC_BASE)
        self.assertNotEqual(client.base, zjgsu_api.BASE)
        self.assertEqual([(c.name, c.domain, c.secure) for c in client.s.cookies],
                         [("fixture_session", "jwgl.sfc.edu.cn", True)])

    def test_unknown_school_rejected_before_session_or_browser_creation(self):
        with patch("login_session.SchoolSession") as session:
            for school_id in ("missing", "", "sfc "):
                with self.subTest(school_id=school_id):
                    with self.assertRaisesRegex(ValueError, "尚未适配学校"):
                        create_adapter("fixture_session=value", school_id=school_id)
                    with self.assertRaises(ValueError):
                        launcher.build_edge_args(SFC_BASE, school_id=school_id)
        session.assert_not_called()

    def test_sfc_domain_and_base_restrictions_before_allocation(self):
        bases = (
            zjgsu_api.BASE, "http://jwgl.sfc.edu.cn/jwglxt/",
            "https://jwgl.sfc.edu.cn.evil.invalid/jwglxt/",
            "https://sub.jwgl.sfc.edu.cn/jwglxt/",
            "https://jwgl.sfc.edu.cn@evil.invalid/jwglxt/",
            "https://user@jwgl.sfc.edu.cn/jwglxt/",
            "https://jwgl.sfc.edu.cn:444/jwglxt/",
            SFC_BASE + "?next=evil", SFC_BASE + "#fragment",
            SFC_BASE + "xtgl/login_slogin.html",
            "https://jwgl.sfc.edu.cn/other/jwglxt/",
        )
        with patch("login_session.SchoolSession") as session:
            for base in bases:
                with self.subTest(base=base):
                    with self.assertRaises(ValueError):
                        create_adapter("fixture_session=value", base_url=base, school_id="sfc")
                    with self.assertRaises(ValueError):
                        launcher.normalize_base(base, school_id="sfc")
        session.assert_not_called()
        self.assertEqual(launcher.normalize_base(SFC_BASE.rstrip("/"), school_id="sfc"), SFC_BASE)

    def test_cookie_not_prepared_for_other_school_and_send_guard_blocks_subdomains(self):
        client = self.client()
        good = client.s.prepare_request(requests.Request("GET", FIXTURE_HOME))
        self.assertIn("fixture_session=fixture-secret", good.headers["Cookie"])
        for url in (zjgsu_api.BASE, "https://sub.jwgl.sfc.edu.cn/jwglxt/", "http://jwgl.sfc.edu.cn/jwglxt/"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    client.s.get(url)
        other = client.s.prepare_request(requests.Request("GET", zjgsu_api.BASE))
        self.assertNotIn("Cookie", other.headers)
        self.transport.assert_not_called()

    def test_redirect_rechecked_before_any_foreign_request(self):
        client = self.client()
        adapter = client.s.get_adapter(FIXTURE_HOME)
        for location in (zjgsu_api.BASE, "https://sub.jwgl.sfc.edu.cn/jwglxt/",
                         "https://jwgl.sfc.edu.cn.evil.invalid/jwglxt/"):
            with self.subTest(location=location):
                with patch.object(adapter, "send", return_value=response(
                        status=302, headers={"Location": location})) as send:
                    with self.assertRaises(ValueError):
                        client.s.get(FIXTURE_HOME)
                self.assertEqual(send.call_count, 1)
                self.assertEqual(send.call_args.args[0].url, FIXTURE_HOME)

    def test_cookie_text_cannot_inject_headers(self):
        with self.assertRaises(ValueError):
            auth.create_login_session("session=value\r\nOther: header", school_id="sfc")

    def test_cookie_alone_never_confirms_sfc_login_without_verified_probe(self):
        client = self.client()
        self.assertFalse(client.check_login())
        self.assertEqual(client.login_check.status, "unverified")
        self.transport.assert_not_called()

    def test_password_login_cookie_capture_then_verified_session_and_expiry(self):
        # The user enters the account/password in Edge. We consume the resulting
        # scoped Cookie; no programmatic credential form or password storage exists.
        tab = {"type": "page", "url": FIXTURE_HOME, "webSocketDebuggerUrl": "ws://127.0.0.1:9228/fixture"}
        cookies = [
            {"name": "fixture_session", "value": "fixture-secret", "domain": ".sfc.edu.cn"},
            {"name": "wrong", "value": "wrong-secret", "domain": ".zjgsu.edu.cn"},
            {"name": "suffix", "value": "bad", "domain": "jwgl.sfc.edu.cn.evil.invalid"},
            {"name": "publicsuffix", "value": "bad", "domain": ".edu.cn"},
        ]
        ws = Mock()
        ws.recv.return_value = json.dumps({"id": 2, "result": {"cookies": cookies}})
        log = Mock()
        with patch("login_session.urllib.request.urlopen", return_value=io.BytesIO(json.dumps([tab]).encode())), \
             patch("login_session.websocket.create_connection", return_value=ws):
            cookie = launcher.capture_cookie_from_edge(log, school_id="sfc")
        self.assertEqual(cookie, "fixture_session=fixture-secret")
        self.assertNotIn("fixture-secret", str(log.call_args_list))
        command = json.loads(ws.send.call_args.args[0])
        self.assertEqual(command["params"]["urls"], [FIXTURE_HOME])
        ws.close.assert_called_once()
        client = create_adapter(cookie, school_id="sfc")
        self.addCleanup(client.s.close)
        client.login_probe = fixture_probe()
        adapter = client.s.get_adapter(FIXTURE_HOME)
        with patch.object(adapter, "send", return_value=response()) as send:
            self.assertTrue(client.check_login())
            self.assertEqual(client.login_check.status, "authenticated")
            self.assertEqual(send.call_args.args[0].headers["Cookie"], cookie)
        with patch.object(adapter, "send", return_value=response(body='<input TYPE = "password">')):
            self.assertFalse(client.check_login())
            self.assertEqual(client.login_check.status, "unauthenticated")

    def test_no_wrong_tab_fallback_even_if_host_appears_inside_query(self):
        tabs = [{"type": "page", "url": "https://evil.invalid/?next=" + LOGIN_URL,
                 "webSocketDebuggerUrl": "ws://127.0.0.1/fixture"}]
        with patch("login_session.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(tabs).encode())), \
             patch("login_session.websocket.create_connection") as ws:
            with self.assertRaises(RuntimeError):
                launcher.capture_cookie_from_edge(Mock(), school_id="sfc")
        ws.assert_not_called()

    def test_session_verification_requires_positive_evidence_and_preserves_states(self):
        client = self.client(login_probe=fixture_probe())
        cases = [
            (response(body=""), "unverified"),
            (response(body="教学管理信息服务平台"), "unverified"),
            (response(body="入口已关闭"), "unverified"),
            (response(body="<input type='password'>" + FIXTURE_BODY), "unauthenticated"),
            (response(url=LOGIN_URL), "unauthenticated"),
            (response(status=302, headers={"Location": LOGIN_URL}), "unverified"),
            (response(status=401), "unauthenticated"),
            (response(status=403), "unauthenticated"),
            (response(status=404), "unavailable"),
            (response(status=503), "unavailable"),
        ]
        for result, status in cases:
            with self.subTest(status=result.status_code, body=result.text):
                with patch.object(client.s, "get", return_value=result) as get:
                    self.assertFalse(client.check_login())
                    self.assertEqual(client.login_check.status, status)
                self.assertFalse(get.call_args.kwargs["allow_redirects"])
        with patch.object(client.s, "get", side_effect=requests.Timeout):
            self.assertFalse(client.check_login())
            self.assertEqual(client.login_check.status, "unavailable")

    def test_external_probe_rejected_without_request(self):
        client = self.client(login_probe=fixture_probe(zjgsu_api.BASE))
        with self.assertRaises(ValueError):
            client.check_login()
        self.transport.assert_not_called()

    def test_sfc_business_operations_fail_before_network(self):
        client = self.client()
        operations = (client.init, lambda: client.fetch_course("fixture"),
                      client.fetch_all_courses_detailed, client.fetch_selected_courses,
                      lambda: client.select_course("course", "class", "round"))
        for operation in operations:
            with self.assertRaisesRegex(NotImplementedError, "尚未验证"):
                operation()
        self.transport.assert_not_called()

    def test_launcher_sfc_verifier_never_initializes_course_business(self):
        client = self.client()
        with patch.object(client, "init", side_effect=AssertionError("No course probe")) as init, \
             patch("zjgsu_launcher.make_client", return_value=client) as factory:
            result = launcher.verify_cookie_full(SFC_BASE, "fixture_session=value", Mock(), school_id="sfc")
        self.assertIn("尚未确认", result)
        self.assertIn("尚待", result)
        self.assertEqual(factory.call_args.kwargs["school_id"], "sfc")
        init.assert_not_called()

    def test_old_zjgsu_login_probe_and_rotated_worker_session(self):
        client = create_adapter("JSESSIONID=initial")
        self.addCleanup(client.s.close)
        with patch.object(client.s, "get", return_value=response(
                url=zjgsu_api.BASE + "xtgl/index_initMenu.html?jsdm=xs", body="<main>legacy menu</main>")) as get:
            self.assertTrue(client.check_login())
        self.assertEqual(get.call_args.args[0], zjgsu_api.BASE + "xtgl/index_initMenu.html?jsdm=xs")
        client.s.cookies.set("JSESSIONID", "rotated", domain="jwxt.zjgsu.edu.cn", secure=True)
        worker = client._new_session()
        self.addCleanup(worker.close)
        self.assertEqual(worker.cookies.get("JSESSIONID", domain="jwxt.zjgsu.edu.cn"), "rotated")
        self.assertEqual({c.domain for c in worker.cookies}, {"jwxt.zjgsu.edu.cn"})
        self.assertIn("--remote-debugging-port=9227", launcher.build_edge_args(zjgsu_api.BASE))
        self.assertEqual(launcher.build_edge_args(zjgsu_api.BASE)[-1], zjgsu_api.BASE)


    def test_legacy_same_school_login_redirect_still_works(self):
        client = create_adapter("JSESSIONID=fixture")
        self.addCleanup(client.s.close)
        start = zjgsu_api.BASE + "xtgl/index_initMenu.html?jsdm=xs"
        landing = zjgsu_api.BASE + "fixture/legacy-menu"
        with patch.object(client.s.get_adapter(start), "send", side_effect=[
                response(url=start, status=302, headers={"Location": landing}),
                response(url=landing, body="<main>legacy menu</main>")]) as send:
            self.assertTrue(client.check_login())
        self.assertEqual(send.call_count, 2)
        self.assertEqual([call.args[0].url for call in send.call_args_list], [start, landing])

    def test_legacy_cdp_prefers_course_tab_and_keeps_default_port(self):
        home = {"type": "page", "url": zjgsu_api.BASE,
                "webSocketDebuggerUrl": "ws://127.0.0.1:9227/home"}
        course = dict(home, url=zjgsu_api.BASE + "xsxk/fixture?ticket=fixture",
                      webSocketDebuggerUrl="ws://127.0.0.1:9227/course")
        ws = Mock()
        ws.recv.return_value = json.dumps({"id": 2, "result": {"cookies": [
            {"name": "JSESSIONID", "value": "fixture", "domain": ".zjgsu.edu.cn"}]}})
        with patch("login_session.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps([home, course]).encode())) as get, \
             patch("login_session.websocket.create_connection", return_value=ws) as connect:
            self.assertEqual(launcher.capture_cookie_from_edge(Mock()), "JSESSIONID=fixture")
        self.assertEqual(get.call_args.args[0], "http://127.0.0.1:9227/json")
        self.assertEqual(connect.call_args.args[0], course["webSocketDebuggerUrl"])
        self.assertEqual(json.loads(ws.send.call_args.args[0])["params"]["urls"], [course["url"]])

    def test_sfc_browser_profile_and_capture_callback_snapshot(self):
        args = launcher.build_edge_args(SFC_BASE, school_id="sfc")
        self.assertIn("--remote-debugging-port=9228", args)
        self.assertTrue(any("edge_profile_sfc" in arg for arg in args))
        self.assertEqual(args[-1], LOGIN_URL)
        app = Mock()
        app.selected_school_id.return_value = "sfc"
        launcher.App.capture_cookie(app)
        work = app.run_thread.call_args.args[0]
        self.assertTrue(app.run_thread.call_args.kwargs["login_task"])
        app.selected_school_id.return_value = "zjgsu"
        with patch("zjgsu_launcher.capture_cookie_from_edge", return_value="fixture_session=value") as capture:
            self.assertEqual(work(), ("cookie", "fixture_session=value"))
        capture.assert_called_once_with(app.thread_log, school_id="sfc")

    def test_sfc_background_reconciliation_and_general_worker_are_blocked(self):
        app = Mock()
        app.selected_school_id.return_value = "sfc"
        launcher.App.refresh_selected_courses(app)
        app.run_thread.assert_not_called()
        self.assertIn("川影", launcher.App.auto_refresh_block_reason(app))
        work = Mock()
        launcher.App.run_thread(app, work)
        work.assert_not_called()
        with patch("zjgsu_launcher.SETTINGS_FILE") as settings:
            launcher.App.save_runtime_settings(app)
        settings.exists.assert_not_called()


if __name__ == "__main__":
    unittest.main()
