import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Dict, Iterator, List


class ChromeLaunchError(RuntimeError):
    """Raised when the project-owned Chrome instance cannot be started."""


@contextmanager
def launch_debug_chrome(start_url: str) -> Iterator[Dict[str, object]]:
    chrome_path = _find_chrome_binary()
    port = _pick_free_port()
    profile_dir = tempfile.mkdtemp(prefix="scribd-exporter-chrome-")
    args = build_chrome_command(chrome_path, port, profile_dir, start_url)
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        metadata = _wait_for_debug_endpoint(port)
        page_target = _wait_for_page_target(port, start_url)
        yield {
            "process": process,
            "port": port,
            "profile_dir": profile_dir,
            "browser_web_socket_debugger_url": metadata["webSocketDebuggerUrl"],
            "web_socket_debugger_url": page_target["webSocketDebuggerUrl"],
        }
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


def _find_chrome_binary() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise ChromeLaunchError("Google Chrome is not installed in /Applications.")


def build_chrome_command(chrome_path: str, port: int, profile_dir: str, start_url: str) -> list:
    return [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-background-networking",
        start_url,
    ]


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_debug_endpoint(port: int) -> Dict[str, object]:
    deadline = time.time() + 15
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json_load(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.2)
    raise ChromeLaunchError("Timed out while waiting for Chrome remote debugging to become ready.")


def _wait_for_page_target(port: int, start_url: str) -> Dict[str, object]:
    deadline = time.time() + 20
    url = f"http://127.0.0.1:{port}/json/list"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                targets = json_load(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.2)
            continue

        page_target = _select_page_target(targets, start_url)
        if page_target is not None:
            return page_target
        time.sleep(0.2)
    raise ChromeLaunchError("Timed out while waiting for the Chrome page target to appear.")


def _select_page_target(targets: List[Dict[str, object]], start_url: str) -> Dict[str, object]:
    parsed_start = urllib.parse.urlsplit(start_url)
    normalized_start = urllib.parse.urlunsplit(
        (parsed_start.scheme, parsed_start.netloc, parsed_start.path, parsed_start.query, "")
    )
    candidates = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
    if not candidates:
        return None

    for target in candidates:
        target_url = str(target.get("url") or "")
        if target_url == start_url or target_url == normalized_start:
            return target

    for target in candidates:
        target_url = str(target.get("url") or "")
        if target_url.startswith(normalized_start) or normalized_start.startswith(target_url):
            return target

    for target in candidates:
        target_url = str(target.get("url") or "")
        if target_url and not target_url.startswith("chrome://") and target_url != "about:blank":
            return target

    return candidates[0]


def json_load(raw: str) -> Dict[str, object]:
    import json

    return json.loads(raw)
