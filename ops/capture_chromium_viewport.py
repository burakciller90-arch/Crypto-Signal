from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from websockets.sync.client import connect


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_target(port: int, url: str, *, timeout_seconds: float = 12.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    encoded = urllib.parse.quote(url, safe="")
    endpoint = f"http://127.0.0.1:{port}/json/new?{encoded}"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(endpoint, method="PUT")
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("webSocketDebuggerUrl"):
                return payload
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.15)
    raise RuntimeError(f"Chrome DevTools target unavailable: {last_error!r}")


class CdpSession:
    def __init__(self, websocket_url: str) -> None:
        self._socket = connect(
            websocket_url,
            origin="http://127.0.0.1",
            open_timeout=5,
            close_timeout=2,
        )
        self._next_id = 1

    def close(self) -> None:
        self._socket.close()

    def command(self, method: str, params: dict[str, object] | None = None) -> dict[str, Any]:
        command_id = self._next_id
        self._next_id += 1
        self._socket.send(
            json.dumps(
                {
                    "id": command_id,
                    "method": method,
                    "params": params or {},
                },
                separators=(",", ":"),
            )
        )
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            raw = self._socket.recv(timeout=2)
            message = json.loads(raw)
            if not isinstance(message, dict) or message.get("id") != command_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP {method} failed: {message['error']!r}")
            result = message.get("result", {})
            if not isinstance(result, dict):
                raise TypeError(f"CDP {method} returned invalid result")
            return result
        raise RuntimeError(f"CDP {method} timed out")


def _capture(args: argparse.Namespace) -> dict[str, object]:
    port = _free_port()
    user_data = args.output.parent / f".chrome-profile-{os.getpid()}"
    log_path = args.output.parent / f"{args.output.stem}.chrome.log"
    command = [
        str(args.browser),
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--hide-scrollbars",
        "--metrics-recording-only",
        "--no-default-browser-check",
        "--no-first-run",
        "--renderer-process-limit=2",
        "--remote-allow-origins=*",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        "about:blank",
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    session: CdpSession | None = None
    try:
        target = _wait_target(port, args.url)
        websocket_url = target.get("webSocketDebuggerUrl")
        if not isinstance(websocket_url, str):
            raise TypeError("Chrome target missing websocket URL")
        session = CdpSession(websocket_url)
        session.command("Page.enable")
        session.command("Runtime.enable")
        session.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": args.width,
                "height": args.height,
                "deviceScaleFactor": args.device_scale_factor,
                "mobile": args.mobile,
                "screenWidth": args.width,
                "screenHeight": args.height,
            },
        )
        session.command("Page.navigate", {"url": args.url})
        settle = session.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(async()=>{"
                    "if(document.fonts&&document.fonts.ready){await document.fonts.ready;}"
                    "await new Promise(r=>setTimeout(r,900));"
                    "return {"
                    "innerWidth:window.innerWidth,"
                    "innerHeight:window.innerHeight,"
                    "scrollWidth:document.documentElement.scrollWidth,"
                    "scrollHeight:document.documentElement.scrollHeight,"
                    "devicePixelRatio:window.devicePixelRatio,"
                    "uiVersion:document.body&&document.body.dataset.uiVersion"
                    "};"
                    "})()"
                ),
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        result = settle.get("result", {})
        if not isinstance(result, dict):
            raise TypeError("CDP metrics evaluation result missing")
        metrics = result.get("value", {})
        if not isinstance(metrics, dict):
            raise TypeError("CDP viewport metrics missing")

        if int(metrics.get("innerWidth", -1)) != args.width:
            raise RuntimeError(
                f"viewport width mismatch: {metrics.get('innerWidth')!r} != {args.width}"
            )
        if args.require_no_horizontal_overflow:
            scroll_width = int(metrics.get("scrollWidth", -1))
            if scroll_width > args.width:
                raise RuntimeError(
                    f"horizontal overflow: scrollWidth={scroll_width} width={args.width}"
                )

        screenshot = session.command(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": False,
            },
        )
        encoded = screenshot.get("data")
        if not isinstance(encoded, str) or not encoded:
            raise RuntimeError("CDP screenshot payload missing")
        args.output.write_bytes(base64.b64decode(encoded))
        return {
            "url": args.url,
            "width": args.width,
            "height": args.height,
            "mobile": args.mobile,
            "device_scale_factor": args.device_scale_factor,
            **metrics,
        }
    finally:
        if session is not None:
            session.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metrics-out", type=Path, default=None)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--device-scale-factor", type=float, default=1.0)
    parser.add_argument("--mobile", action="store_true")
    parser.add_argument("--require-no-horizontal-overflow", action="store_true")
    args = parser.parse_args()

    if not args.browser.is_file():
        raise SystemExit(f"browser missing: {args.browser}")
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("viewport dimensions must be positive")
    if args.device_scale_factor <= 0:
        raise SystemExit("device scale factor must be positive")

    metrics = _capture(args)
    metrics_out = args.metrics_out or args.output.with_suffix(".metrics.json")
    metrics_out.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "CHROMIUM_CDP_CAPTURE_PASS=YES",
        f"viewport={metrics.get('innerWidth')}x{metrics.get('innerHeight')}",
        f"scroll_width={metrics.get('scrollWidth')}",
        f"ui_version={metrics.get('uiVersion')}",
    )


if __name__ == "__main__":
    main()
