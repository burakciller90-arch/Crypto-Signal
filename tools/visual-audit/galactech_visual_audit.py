from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from websockets.sync.client import connect
from websockets.typing import Origin


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _browser_candidates() -> list[Path]:
    return [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
    ]


def _browser(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path
        raise FileNotFoundError(f"browser not found: {path}")
    for path in _browser_candidates():
        if path.is_file():
            return path
    raise FileNotFoundError("Google Chrome / Chromium not found")


def _wait_target(port: int, url: str, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    encoded = urllib.parse.quote(url, safe="")
    endpoint = f"http://127.0.0.1:{port}/json/new?{encoded}"
    error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(endpoint, method="PUT")
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("webSocketDebuggerUrl"):
                return payload
        except Exception as exc:
            error = exc
            time.sleep(0.15)
    raise RuntimeError(f"Chrome DevTools target unavailable: {error!r}")


class CDP:
    def __init__(self, websocket_url: str, frames_dir: Path) -> None:
        self.ws = connect(
            websocket_url,
            origin=Origin("http://127.0.0.1"),
            open_timeout=5,
            close_timeout=2,
            max_size=64 * 1024 * 1024,
        )
        self.next_id = 1
        self.events: list[dict[str, Any]] = []
        self.frames_dir = frames_dir
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.frame_count = 0

    def close(self) -> None:
        self.ws.close()

    def _send(self, method: str, params: dict[str, object] | None = None) -> int:
        command_id = self.next_id
        self.next_id += 1
        self.ws.send(json.dumps({"id": command_id, "method": method, "params": params or {}}, separators=(",", ":")))
        return command_id

    def _handle(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        if method == "Page.screencastFrame":
            params = message.get("params") or {}
            data = params.get("data")
            session_id = params.get("sessionId")
            if isinstance(data, str):
                self.frame_count += 1
                (self.frames_dir / f"{self.frame_count:06d}.jpg").write_bytes(base64.b64decode(data))
            if session_id is not None:
                self._send("Page.screencastFrameAck", {"sessionId": session_id})
            return
        if method.startswith(("Runtime.", "Log.", "Network.")):
            self.events.append(message)

    def command(self, method: str, params: dict[str, object] | None = None, timeout: float = 15.0) -> dict[str, Any]:
        command_id = self._send(method, params)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                raw = self.ws.recv(timeout=min(2.0, remaining))
            except TimeoutError:
                continue
            message = json.loads(raw)
            if not isinstance(message, dict):
                continue
            if message.get("id") == command_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']!r}")
                result = message.get("result", {})
                return result if isinstance(result, dict) else {}
            self._handle(message)
        raise RuntimeError(f"CDP {method} timed out")

    def pump(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                raw = self.ws.recv(timeout=min(0.25, max(0.05, deadline - time.monotonic())))
            except TimeoutError:
                continue
            message = json.loads(raw)
            if isinstance(message, dict):
                self._handle(message)


def _value(session: CDP, expression: str, await_promise: bool = False) -> Any:
    result = session.command(
        "Runtime.evaluate",
        {"expression": expression, "awaitPromise": await_promise, "returnByValue": True},
    )
    return ((result.get("result") or {}).get("value"))


def _shot(session: CDP, path: Path, full_page: bool = False) -> None:
    params: dict[str, object] = {"format": "png", "fromSurface": True}
    if full_page:
        params["captureBeyondViewport"] = True
    result = session.command("Page.captureScreenshot", params, timeout=30)
    data = result.get("data")
    if not isinstance(data, str):
        raise RuntimeError("Page.captureScreenshot returned no image")
    path.write_bytes(base64.b64decode(data))


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip().lower())
    return cleaned.strip("-") or "step"


def _load_scenario(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    actions = payload.get("actions", payload) if isinstance(payload, dict) else payload
    if not isinstance(actions, list):
        raise TypeError("scenario must be a list or {'actions': [...]}")
    result: list[dict[str, Any]] = []
    for item in actions:
        if not isinstance(item, dict):
            raise TypeError("scenario action must be an object")
        kind = str(item.get("type", "")).lower()
        if kind not in {"wait", "scroll", "click", "screenshot"}:
            raise ValueError(f"unsupported safe action: {kind!r}")
        result.append(item)
    return result


def _resolve_ffmpeg() -> str | None:
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        return bundled if bundled and Path(bundled).is_file() else None
    except Exception:
        return None


def _finalize_video(frames_dir: Path, output: Path) -> dict[str, Any]:
    frames = sorted(frames_dir.glob("*.jpg"))
    ffmpeg = _resolve_ffmpeg()
    result: dict[str, Any] = {"frame_count": len(frames), "ffmpeg": ffmpeg, "video": None}
    if not frames or not ffmpeg:
        return result
    command = [
        ffmpeg, "-y", "-loglevel", "error", "-framerate", "6",
        "-i", str(frames_dir / "%06d.jpg"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(output),
    ]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    result["ffmpeg_returncode"] = completed.returncode
    result["ffmpeg_stderr"] = completed.stderr[-4000:]
    if completed.returncode == 0 and output.is_file():
        result["video"] = output.name
    return result


def audit(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_dir.resolve()
    shots = output / "screenshots"
    frames = output / "video-frames"
    output.mkdir(parents=True, exist_ok=True)
    shots.mkdir(parents=True, exist_ok=True)
    frames.mkdir(parents=True, exist_ok=True)

    browser = _browser(args.browser)
    scenario = _load_scenario(args.scenario)
    port = _free_port()
    profile = output / ".chrome-profile"
    chrome_log = output / "chrome.log"
    command = [
        str(browser), "--headless=new", "--disable-gpu", "--disable-extensions",
        "--disable-background-networking", "--disable-component-update", "--disable-sync",
        "--no-default-browser-check", "--no-first-run", "--remote-allow-origins=*",
        f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
        "about:blank",
    ]
    with chrome_log.open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    session: CDP | None = None
    started = time.time()
    action_results: list[dict[str, Any]] = []
    try:
        target = _wait_target(port, args.url)
        ws_url = target.get("webSocketDebuggerUrl")
        if not isinstance(ws_url, str):
            raise RuntimeError("webSocketDebuggerUrl missing")
        session = CDP(ws_url, frames)
        for domain in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable", "Accessibility.enable"):
            session.command(domain)
        session.command("Emulation.setDeviceMetricsOverride", {
            "width": args.width, "height": args.height, "deviceScaleFactor": 1,
            "mobile": False, "screenWidth": args.width, "screenHeight": args.height,
        })
        session.command("Page.startScreencast", {"format": "jpeg", "quality": 70, "maxWidth": args.width, "maxHeight": args.height, "everyNthFrame": 1})
        session.command("Page.navigate", {"url": args.url})
        session.pump(args.settle_seconds)
        _value(session, "(async()=>{if(document.fonts&&document.fonts.ready){await document.fonts.ready;}await new Promise(r=>setTimeout(r,300));return true})()", True)
        _shot(session, shots / "000-initial.png")

        for index, action in enumerate(scenario, start=1):
            kind = str(action.get("type", "")).lower()
            name = _safe_name(str(action.get("name") or f"{index:03d}-{kind}"))
            record: dict[str, Any] = {"index": index, "type": kind, "name": name, "ok": True}
            try:
                if kind == "wait":
                    session.pump(float(action.get("seconds", 1.0)))
                elif kind == "scroll":
                    delta = int(action.get("delta_y", args.height * 0.75))
                    selector = action.get("selector")
                    selector_json = json.dumps(selector) if isinstance(selector, str) else "null"
                    expression = f"""(()=>{{const s={selector_json};const el=s?document.querySelector(s):null;const t=el||window;if(el)el.scrollBy({{top:{delta},behavior:'smooth'}});else window.scrollBy({{top:{delta},behavior:'smooth'}});return {{selector:s,found:!!el,delta:{delta}}};}})()"""
                    record["result"] = _value(session, expression)
                    session.pump(float(action.get("settle_seconds", 1.1)))
                elif kind == "click":
                    selector = action.get("selector")
                    if not isinstance(selector, str) or not selector:
                        raise ValueError("click requires selector")
                    item_index = int(action.get("index", 0))
                    expression = f"""(()=>{{const els=[...document.querySelectorAll({json.dumps(selector)})];const el=els[{item_index}];if(!el)return {{ok:false,count:els.length}};el.scrollIntoView({{block:'center',inline:'center'}});el.click();return {{ok:true,count:els.length,text:(el.innerText||el.textContent||'').trim().slice(0,300),tag:el.tagName}};}})()"""
                    result = _value(session, expression)
                    record["result"] = result
                    if not isinstance(result, dict) or result.get("ok") is not True:
                        if not bool(action.get("optional", False)):
                            raise RuntimeError(f"click target unavailable: {selector} [{item_index}]")
                        record["ok"] = False
                    session.pump(float(action.get("settle_seconds", 0.9)))
                elif kind == "screenshot":
                    pass
                if bool(action.get("capture", True)):
                    _shot(session, shots / f"{index:03d}-{name}.png")
            except Exception as exc:
                record["ok"] = False
                record["error"] = repr(exc)
                if not bool(action.get("optional", False)):
                    action_results.append(record)
                    raise
            action_results.append(record)

        _shot(session, shots / "999-final.png")
        _shot(session, shots / "999-full-page.png", full_page=True)

        dom = _value(session, "document.documentElement.outerHTML")
        if isinstance(dom, str):
            (output / "dom.html").write_text(dom, encoding="utf-8")
        inventory = _value(session, """(()=>[...document.querySelectorAll('a,button,input,select,textarea,[role=button],[tabindex]')].slice(0,2000).map((el,i)=>{const r=el.getBoundingClientRect();return {i,tag:el.tagName,role:el.getAttribute('role'),text:(el.innerText||el.getAttribute('aria-label')||el.getAttribute('title')||'').trim().slice(0,240),id:el.id||null,classes:el.className||null,disabled:!!el.disabled,rect:{x:r.x,y:r.y,width:r.width,height:r.height}}}))()""")
        (output / "interactive-elements.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
        ax_tree = session.command("Accessibility.getFullAXTree", timeout=30)
        (output / "accessibility-tree.json").write_text(json.dumps(ax_tree, indent=2, ensure_ascii=False), encoding="utf-8")
        metrics = _value(session, "({title:document.title,url:location.href,innerWidth,innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,devicePixelRatio})")
        session.command("Page.stopScreencast")
        session.pump(0.4)
        events = session.events
        (output / "browser-events.json").write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=4)
        shutil.rmtree(profile, ignore_errors=True)

    video = _finalize_video(frames, output / "audit.mp4")
    manifest = {
        "schema_version": 1,
        "tool": "galactech-visual-audit",
        "url": args.url,
        "browser": str(browser),
        "viewport": {"width": args.width, "height": args.height},
        "started_unix": started,
        "duration_seconds": round(time.time() - started, 3),
        "metrics": metrics,
        "actions": action_results,
        "video": video,
        "safety": {
            "allowed_actions": ["wait", "scroll", "click", "screenshot"],
            "arbitrary_javascript_from_scenario": False,
            "arbitrary_shell_from_scenario": False,
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Shared Galactech Chromium visual-audit recorder")
    parser.add_argument("--url")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--browser")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    parser.add_argument("--capabilities", action="store_true")
    args = parser.parse_args()

    if args.capabilities:
        print(json.dumps({
            "tool": "galactech-visual-audit",
            "schema_version": 1,
            "browser": str(_browser(args.browser)),
            "ffmpeg": _resolve_ffmpeg(),
            "safe_actions": ["wait", "scroll", "click", "screenshot"],
        }, indent=2))
        return
    if not args.url or args.output_dir is None:
        parser.error("--url and --output-dir are required unless --capabilities is used")
    manifest = audit(args)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
