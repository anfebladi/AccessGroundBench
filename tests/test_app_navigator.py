import contextlib
import io
import unittest

import app_navigator
import orchestrator


class AppNavigatorTests(unittest.TestCase):
    def test_screen_registry_contains_orchestrator_screens(self):
        missing = [screen for screen in orchestrator.SCREENS if screen not in app_navigator.SCREEN_TARGETS]
        self.assertEqual([], missing)

    def test_unknown_screen_fails_clearly(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                app_navigator.get_screen_target("not_a_real_screen")

    def test_parse_window_current_focus(self):
        output = (
            "mCurrentFocus=Window{a1 u0 "
            "com.android.settings/com.android.settings.Settings}"
        )
        self.assertEqual(
            "com.android.settings",
            app_navigator.parse_foreground_package(output),
        )

    def test_parse_activity_top_resumed(self):
        output = (
            "topResumedActivity=ActivityRecord{1 u0 "
            "com.google.android.dialer/.DialtactsActivity t12}"
        )
        self.assertEqual(
            "com.google.android.dialer",
            app_navigator.parse_foreground_package(output),
        )

    def test_parse_package_name_fallback(self):
        output = "packageName=com.google.android.apps.messaging"
        self.assertEqual(
            "com.google.android.apps.messaging",
            app_navigator.parse_foreground_package(output),
        )

    def test_parse_prioritizes_focus_line(self):
        output = "\n".join((
            "ActivityRecord{1 u0 com.google.android.apps.nexuslauncher/.Launcher}",
            "mCurrentFocus=Window{2 u0 com.android.settings/com.android.settings.Settings}",
        ))
        self.assertEqual(
            "com.android.settings",
            app_navigator.parse_foreground_package(output),
        )

    def test_permission_controller_detection(self):
        self.assertTrue(app_navigator.is_permission_controller("com.google.android.permissioncontroller"))
        self.assertTrue(app_navigator.is_permission_controller("com.android.permissioncontroller"))
        self.assertFalse(app_navigator.is_permission_controller("com.google.android.contacts"))

    def test_parse_bounds(self):
        self.assertEqual(
            (157, 1341, 922, 1497),
            app_navigator.parse_bounds("[157,1341][922,1497]"),
        )
        self.assertIsNone(app_navigator.parse_bounds("157,1341,922,1497"))

    def test_select_permission_allow_button_over_deny(self):
        xml_text = """<?xml version='1.0' encoding='UTF-8'?>
        <hierarchy>
          <node text="Don't allow" resource-id="com.android.permissioncontroller:id/permission_deny_button" bounds="[157,1523][922,1679]" />
          <node text="Allow" resource-id="com.android.permissioncontroller:id/permission_allow_button" bounds="[157,1341][922,1497]" />
        </hierarchy>
        """
        self.assertEqual(
            (539, 1419),
            app_navigator.select_permission_allow_target(xml_text),
        )

    def test_select_permission_text_fallback(self):
        xml_text = """<?xml version='1.0' encoding='UTF-8'?>
        <hierarchy>
          <node text="While using the app" resource-id="android:id/button1" bounds="[100,200][500,300]" />
        </hierarchy>
        """
        self.assertEqual(
            (300, 250),
            app_navigator.select_permission_allow_target(xml_text),
        )

    def test_select_permission_returns_none_for_only_deny(self):
        xml_text = """<?xml version='1.0' encoding='UTF-8'?>
        <hierarchy>
          <node text="Don't allow" resource-id="com.android.permissioncontroller:id/permission_deny_button" bounds="[157,1523][922,1679]" />
          <node text="Cancel" resource-id="android:id/button2" bounds="[157,1341][922,1497]" />
        </hierarchy>
        """
        self.assertIsNone(app_navigator.select_permission_allow_target(xml_text))


if __name__ == "__main__":
    unittest.main()
