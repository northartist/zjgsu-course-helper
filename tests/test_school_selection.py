"""School switching is tested without starting a browser or a GUI event loop."""
import queue
import unittest
from unittest.mock import Mock

import zjgsu_api
import zjgsu_launcher as launcher
from sfc_api import BASE


class SchoolSelectionTests(unittest.TestCase):
    def app(self):
        app = Mock()
        app.worker = None
        app._progress_finished = True
        app.q = queue.Queue()
        app._active_school = "zjgsu"
        app.selected_school_id.return_value = "sfc"
        return app

    def test_displayed_school_name_maps_to_explicit_id_and_unknown_is_rejected(self):
        app = Mock()
        app.school_var.get.return_value = launcher.login_profile("sfc").name
        self.assertEqual(launcher.App.selected_school_id(app), "sfc")
        app.school_var.get.return_value = "未知学校"
        with self.assertRaises(ValueError):
            launcher.App.selected_school_id(app)

    def test_switch_clears_credentials_closes_old_client_and_disables_business_tabs(self):
        app = self.app()
        old_session = app.search_result.client.s
        launcher.App.change_school(app)
        app.base_var.set.assert_called_once_with(BASE)
        app.cookie_box.delete.assert_called_once_with("1.0", "end")
        old_session.close.assert_called_once()
        self.assertIsNone(app.search_result)
        app.nb.select.assert_called_once_with(app.login_tab)
        self.assertEqual([c.kwargs["state"] for c in app.nb.tab.call_args_list], ["disabled"] * 4)
        self.assertEqual(app._active_school, "sfc")
        app.selected_school_id.return_value = "zjgsu"
        app.nb.tab.reset_mock()
        launcher.App.change_school(app)
        self.assertEqual(app.base_var.set.call_args.args[0], zjgsu_api.BASE)
        self.assertEqual([c.kwargs["state"] for c in app.nb.tab.call_args_list], ["normal"] * 4)

    def test_running_worker_and_pending_cookie_result_prevent_cross_school_delivery(self):
        for mode in ("running", "not_settled", "queued"):
            with self.subTest(mode=mode):
                app = self.app()
                if mode == "running":
                    app.worker = Mock()
                    app.worker.is_alive.return_value = True
                elif mode == "not_settled":
                    app._progress_finished = False
                else:
                    app.q.put(("cookie", "JSESSIONID=old-school-fixture"))
                launcher.App.change_school(app)
                app.school_var.set.assert_called_once_with("浙江工商大学")
                app.base_var.set.assert_not_called()
                app.cookie_box.delete.assert_not_called()
