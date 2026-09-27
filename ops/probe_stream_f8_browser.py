from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from capture_chromium_viewport import CdpSession, _free_port, _wait_target

REAL_CAPITAL = 0


def _value(result: dict[str, Any]) -> object:
    outer = result.get("result", {})
    if not isinstance(outer, dict):
        raise TypeError("CDP Runtime.evaluate missing result")
    if "exceptionDetails" in result:
        raise RuntimeError(f"CDP Runtime.evaluate exception: {result['exceptionDetails']!r}")
    return outer.get("value")


def _evaluate(
    session: CdpSession,
    expression: str,
    *,
    await_promise: bool = False,
) -> object:
    result = session.command(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": True,
        },
        timeout_seconds=20.0,
    )
    return _value(result)


def _wait_message_expression(identity: str) -> str:
    encoded = json.dumps(identity)
    return (
        "(async()=>{"
        "if(document.fonts&&document.fonts.ready){await document.fonts.ready;}"
        "for(let i=0;i<50;i++){"
        f"const node=document.querySelector('.message[data-identity='+JSON.stringify({encoded})+']');"
        "if(node){return true;}"
        "await new Promise(r=>setTimeout(r,120));"
        "}"
        "return false;"
        "})()"
    )


def _snapshot_expression(identity: str) -> str:
    encoded = json.dumps(identity)
    return (
        "(()=>{"
        f"const identity={encoded};"
        "const node=[...document.querySelectorAll('.message')].find(n=>n.dataset.identity===identity)||null;"
        "const notification=window.CryptoSignalNotifications?.snapshot?.()||null;"
        "return {"
        "href:location.href,"
        "fixture:new URLSearchParams(location.search).get('fixture')||'',"
        "uiVersion:document.body?.dataset?.uiVersion||'',"
        "identity:node?.dataset?.identity||'',"
        "deepLinked:Boolean(node?.classList?.contains('is-deep-linked')),"
        "messageText:(node?.querySelector('.message-copy')?.textContent||'').trim(),"
        "messageCount:document.querySelectorAll('.message').length,"
        "scrollWidth:document.documentElement.scrollWidth,"
        "innerWidth:window.innerWidth,"
        "notification"
        "};"
        "})()"
    )


def _interaction_expression(identity: str, search_text: str, category: str) -> str:
    identity_js = json.dumps(identity)
    search_js = json.dumps(search_text)
    category_js = json.dumps(category)
    return (
        "(async()=>{"
        f"const identity={identity_js};"
        f"const searchText={search_js};"
        f"const category={category_js};"
        "const find=()=>document.querySelector('.message[data-identity="'+identity+'"]');"
        "let node=find();"
        "if(!node)return {error:'message_missing_before_interaction'};"
        "node.querySelector('.message-summary')?.click();"
        "for(let i=0;i<30;i++){"
        "const detail=node.querySelector('.message-detail');"
        "if(detail&&!detail.hidden&&detail.textContent.trim())break;"
        "await new Promise(r=>setTimeout(r,120));"
        "}"
        "const detail=node.querySelector('.message-detail');"
        "const expanded=Boolean(detail&&!detail.hidden);"
        "const evidenceButtons=[...node.querySelectorAll('[data-evidence-kind]')];"
        "if(evidenceButtons.length)evidenceButtons[0].click();"
        "await new Promise(r=>setTimeout(r,450));"
        "const evidenceWindowCount=document.querySelectorAll('.evidence-window').length;"
        "document.getElementById('searchButton')?.click();"
        "await new Promise(r=>setTimeout(r,80));"
        "const search=document.getElementById('searchInput');"
        "if(search){search.value=searchText;search.dispatchEvent(new Event('input',{bubbles:true}));}"
        "const select=document.getElementById('categoryFilter');"
        "if(select){select.value=category;select.dispatchEvent(new Event('change',{bubbles:true}));}"
        "document.getElementById('applyFiltersButton')?.click();"
        "for(let i=0;i<40;i++){"
        "if(find())break;"
        "await new Promise(r=>setTimeout(r,120));"
        "}"
        "node=find();"
        "return {"
        "expanded,"
        "evidenceButtonCount:evidenceButtons.length,"
        "evidenceWindowCount,"
        "searchRetainedExact:Boolean(node),"
        "searchResultCount:document.querySelectorAll('.message').length,"
        "notification:window.CryptoSignalNotifications?.snapshot?.()||null"
        "};"
        "})()"
    )


def _assert_snapshot(snapshot: object, identity: str) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise TypeError("browser snapshot must be object")
    if snapshot.get("fixture"):
        raise RuntimeError("F8 browser probe entered fixture mode")
    if snapshot.get("identity") != identity:
        raise RuntimeError("deep link did not resolve exact persisted message")
    if snapshot.get("deepLinked") is not True:
        raise RuntimeError("exact persisted message was not deep-link highlighted")
    if not str(snapshot.get("messageText", "")).strip():
        raise RuntimeError("exact persisted message text is empty")
    if int(snapshot.get("scrollWidth", -1)) > int(snapshot.get("innerWidth", -2)):
        raise RuntimeError("browser viewport has horizontal overflow")
    notification = snapshot.get("notification")
    if not isinstance(notification, dict):
        raise TypeError("notification audit snapshot unavailable")
    audit = notification.get("audit")
    if not isinstance(audit, dict):
        raise TypeError("notification audit body unavailable")
    if int(audit.get("chimePlayed", -1)) != 0:
        raise RuntimeError("historical/deep-link load emitted a chime")
    if int(audit.get("duplicate", -1)) != 0:
        raise RuntimeError("historical/deep-link load recorded duplicate delivery")
    return snapshot


def run_probe(args: argparse.Namespace) -> dict[str, object]:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    profile = args.output.parent / f".f8-chrome-profile-{os.getpid()}"
    log_path = args.output.parent / "f8-browser.chrome.log"
    url = (
        args.base_url.rstrip("/")
        + "/stream-preview?message="
        + args.narrative_identity
    )
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
        f"--user-data-dir={profile}",
        "about:blank",
    ]
    process: subprocess.Popen[bytes] | None = None
    session: CdpSession | None = None
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        target = _wait_target(port, url)
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
                "deviceScaleFactor": 1,
                "mobile": args.mobile,
                "screenWidth": args.width,
                "screenHeight": args.height,
            },
        )
        session.command("Page.navigate", {"url": url})
        ready = _evaluate(
            session,
            _wait_message_expression(args.narrative_identity),
            await_promise=True,
        )
        if ready is not True:
            raise RuntimeError("exact persisted message did not render")

        initial = _assert_snapshot(
            _evaluate(session, _snapshot_expression(args.narrative_identity)),
            args.narrative_identity,
        )
        original_text = str(initial["messageText"])

        interaction = _evaluate(
            session,
            _interaction_expression(
                args.narrative_identity,
                args.search_text,
                args.category,
            ),
            await_promise=True,
        )
        if not isinstance(interaction, dict):
            raise TypeError("browser interaction result must be object")
        if interaction.get("error"):
            raise RuntimeError(str(interaction["error"]))
        if interaction.get("expanded") is not True:
            raise RuntimeError("real production message did not expand")
        if int(interaction.get("evidenceButtonCount", 0)) < 1:
            raise RuntimeError("real production message exposes no evidence launcher")
        if int(interaction.get("evidenceWindowCount", 0)) < 1:
            raise RuntimeError("evidence launcher did not open an evidence window")
        if interaction.get("searchRetainedExact") is not True:
            raise RuntimeError("real UI search/filter lost the exact persisted message")

        session.command("Page.navigate", {"url": url})
        ready_again = _evaluate(
            session,
            _wait_message_expression(args.narrative_identity),
            await_promise=True,
        )
        if ready_again is not True:
            raise RuntimeError("exact message did not render after refresh navigation")
        refreshed = _assert_snapshot(
            _evaluate(session, _snapshot_expression(args.narrative_identity)),
            args.narrative_identity,
        )
        if str(refreshed["messageText"]) != original_text:
            raise RuntimeError("persisted message text changed after refresh navigation")

        screenshot = session.command(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
        )
        data = screenshot.get("data")
        if not isinstance(data, str) or not data:
            raise RuntimeError("CDP screenshot missing")
        args.screenshot.write_bytes(base64.b64decode(data))

        return {
            "schema_version": "stream-final-f8-browser-probe-v1/1",
            "status": "PASS",
            "url": url,
            "narrative_identity": args.narrative_identity,
            "category": args.category,
            "search_text": args.search_text,
            "initial": initial,
            "interaction": interaction,
            "refreshed": refreshed,
            "immutable_refresh": True,
            "fixture_query": False,
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }
    finally:
        if session is not None:
            session.close()
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:48700")
    parser.add_argument("--narrative-identity", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--search-text", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--mobile", action="store_true")
    args = parser.parse_args()

    report = run_probe(args)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("F8_REAL_BROWSER_PROBE_PASS=YES")
    print("HISTORICAL_BACKFILL=NO")
    print("SYNTHETIC_ACTIVITY=NO")
    print("REAL_CAPITAL=0")


if __name__ == "__main__":
    main()
