import unittest

from scribd_exporter.chrome_launcher import build_chrome_command, _select_page_target


class ChromeLauncherTests(unittest.TestCase):
    def test_build_chrome_command_includes_debug_port_and_profile(self) -> None:
        command = build_chrome_command(
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            9222,
            "/tmp/test-profile",
            "https://example.com",
        )
        self.assertIn("--remote-debugging-port=9222", command)
        self.assertIn("--user-data-dir=/tmp/test-profile", command)
        self.assertEqual(command[-1], "https://example.com")

    def test_select_page_target_prefers_matching_page_url(self) -> None:
        targets = [
            {
                "type": "browser",
                "url": "",
                "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/browser/1",
            },
            {
                "type": "page",
                "url": "https://example.com/document/123",
                "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/1",
            },
        ]
        selected = _select_page_target(targets, "https://example.com/document/123")
        self.assertEqual(selected["webSocketDebuggerUrl"], "ws://127.0.0.1/devtools/page/1")


if __name__ == "__main__":
    unittest.main()
