import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from collection import orchestrator
from collection.navigation import app_navigator


class AppNavigatorTests(unittest.TestCase):
    def test_screen_registry_contains_orchestrator_screens(self):
        missing = [screen for screen in orchestrator.SCREENS if screen not in app_navigator.SCREEN_TARGETS]
        self.assertEqual([], missing)

    def test_orchestrator_uses_registry_default_order(self):
        self.assertEqual(
            list(app_navigator.default_screen_names()),
            orchestrator.SCREENS,
        )
        self.assertEqual(
            {"calculator", "calendar", "chrome", "camera", "files"},
            {
                name for name, target in app_navigator.SCREEN_TARGETS.items()
                if not target.default_enabled
            },
        )

    def test_unknown_screen_fails_clearly(self):
        with self.assertRaises(app_navigator.UnknownScreenError) as raised:
            app_navigator.get_screen_target("not_a_real_screen")
        self.assertIn("not_a_real_screen", str(raised.exception))

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

    @mock.patch("collection.navigation.app_navigator.time.sleep")
    @mock.patch("collection.navigation.app_navigator.get_foreground_package", return_value="com.google.android.contacts")
    @mock.patch("collection.navigation.app_navigator.get_device_serial", return_value="emulator-5554")
    @mock.patch("collection.navigation.app_navigator.resolve_adb", return_value="adb")
    @mock.patch("collection.navigation.app_navigator.run_adb")
    def test_navigation_tries_next_launch_command_after_failure(
        self, run_adb, _resolve_adb, _get_serial, _foreground, _sleep
    ):
        run_adb.side_effect = [
            subprocess.CalledProcessError(1, ["adb"], stderr="first command failed"),
            subprocess.CompletedProcess([], 0),
        ]

        app_navigator.navigate_to_screen("contacts")

        self.assertEqual(2, run_adb.call_count)
        self.assertEqual(
            ("shell", "monkey", "-p", "com.google.android.contacts", "-c", "android.intent.category.LAUNCHER", "1"),
            run_adb.call_args.args[2:],
        )

    @mock.patch("collection.navigation.app_navigator.time.sleep")
    @mock.patch(
        "collection.navigation.app_navigator.get_foreground_package",
        side_effect=[
            "com.google.android.permissioncontroller",
            "com.google.android.contacts",
        ],
    )
    @mock.patch("collection.navigation.app_navigator.handle_permission_dialog", return_value=True)
    @mock.patch("collection.navigation.app_navigator.get_device_serial", return_value="emulator-5554")
    @mock.patch("collection.navigation.app_navigator.resolve_adb", return_value="adb")
    @mock.patch("collection.navigation.app_navigator.run_adb")
    def test_navigation_relaunches_after_permission_grant(
        self, run_adb, _resolve_adb, _get_serial, handle_permission, _foreground, _sleep
    ):
        app_navigator.navigate_to_screen("contacts")

        self.assertEqual(2, run_adb.call_count)
        handle_permission.assert_called_once_with("adb", "emulator-5554")

    @mock.patch("collection.navigation.app_navigator.time.sleep")
    @mock.patch("collection.navigation.app_navigator.get_foreground_package", return_value="com.android.settings")
    @mock.patch("collection.navigation.app_navigator.get_device_serial", return_value="emulator-5554")
    @mock.patch("collection.navigation.app_navigator.resolve_adb", return_value="adb")
    @mock.patch("collection.navigation.app_navigator.run_adb")
    def test_navigation_raises_typed_error_for_foreground_mismatch(
        self, run_adb, _resolve_adb, _get_serial, _foreground, _sleep
    ):
        with self.assertRaises(app_navigator.NavigationError) as raised:
            app_navigator.navigate_to_screen("contacts")

        self.assertIn("contacts", str(raised.exception))
        self.assertEqual(3, run_adb.call_count)

    def test_xml_package_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            xml_path = Path(directory) / "contacts.xml"
            xml_path.write_text(
                '<hierarchy><node package="com.google.android.contacts" /></hierarchy>',
                encoding="utf-8",
            )
            app_navigator.validate_xml_package(xml_path, "contacts")

    def test_xml_package_validation_rejects_wrong_package(self):
        with tempfile.TemporaryDirectory() as directory:
            xml_path = Path(directory) / "wrong.xml"
            xml_path.write_text(
                '<hierarchy><node package="com.android.settings" /></hierarchy>',
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                app_navigator.validate_xml_package(xml_path, "contacts")


if __name__ == "__main__":
    unittest.main()
