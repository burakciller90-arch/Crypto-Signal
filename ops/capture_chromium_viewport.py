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
from websockets.typing import Origin


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
            origin=Origin("http://127.0.0.1"),
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

        if args.probe_expansion_anchor:
            probe_result = session.command(
                "Runtime.evaluate",
                {
                    "expression": (
                        "(async()=>{"
                        "const viewport=document.getElementById('streamViewport');"
                        "const items=[...document.querySelectorAll('.message')];"
                        "const item=items[Math.min(2,Math.max(0,items.length-1))];"
                        "if(!viewport||!item){return {ok:false,reason:'missing_target'};}"
                        "item.scrollIntoView({block:'center'});"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
                        "const beforeTop=item.getBoundingClientRect().top;"
                        "const beforeScroll=viewport.scrollTop;"
                        "const button=item.querySelector('.message-summary');"
                        "if(!button){return {ok:false,reason:'missing_summary'};}"
                        "button.click();"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(r))));"
                        "await new Promise(r=>setTimeout(r,120));"
                        "const afterTop=item.getBoundingClientRect().top;"
                        "const labels=[...item.querySelectorAll('.depth-heading span')].map(n=>n.textContent);"
                        "return {"
                        "ok:item.classList.contains('is-expanded'),"
                        "beforeTop,afterTop,beforeScroll,afterScroll:viewport.scrollTop,"
                        "anchorDriftPx:Math.abs(afterTop-beforeTop),"
                        "labels"
                        "};"
                        "})()"
                    ),
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )
            raw_probe = probe_result.get("result", {})
            if not isinstance(raw_probe, dict):
                raise RuntimeError("CDP expansion probe result missing")
            expansion_probe = raw_probe.get("value", {})
            if not isinstance(expansion_probe, dict):
                raise RuntimeError("CDP expansion probe value missing")
            if expansion_probe.get("ok") is not True:
                raise RuntimeError(
                    f"message expansion probe failed: {expansion_probe!r}"
                )
            anchor_drift = float(expansion_probe.get("anchorDriftPx", 9999))
            if anchor_drift > 1.0:
                raise RuntimeError(
                    f"message expansion anchor drift: {anchor_drift}"
                )
            labels = expansion_probe.get("labels", [])
            required_labels = {
                "SIMPLE",
                "PRO",
                "INTELLIGENCE",
                "DECISION",
                "TRADE GEOMETRY",
                "CAPITAL",
                "PROOF",
            }
            if not isinstance(labels, list) or not required_labels.issubset(
                {str(value) for value in labels}
            ):
                raise RuntimeError(
                    f"message expansion depth incomplete: {labels!r}"
                )
            metrics["expansion_probe"] = expansion_probe

        if args.probe_window_manager:
            window_probe_result = session.command(
                "Runtime.evaluate",
                {
                    "expression": (
                        "(async()=>{"
                        "await new Promise(r=>setTimeout(r,180));"
                        "const wins=[...document.querySelectorAll('.evidence-window')];"
                        "if(wins.length<3){return {ok:false,reason:'window_count',count:wins.length};}"
                        "const validSha=v=>/^[0-9a-f]{64}$/.test(v||'');"
                        "const first=wins[0],second=wins[1],third=wins[2];"
                        "const identities=wins.map(w=>w.dataset.narrativeIdentity||'');"
                        "const kinds=wins.map(w=>w.dataset.kind||'');"
                        "if(!identities.every(validSha)){return {ok:false,reason:'identity',identities};}"
                        "const before=first.getBoundingClientRect();"
                        "const bar=first.querySelector('.evidence-window-drag');"
                        "if(!bar){return {ok:false,reason:'drag_handle'};}"
                        "bar.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerId:21,clientX:before.left+60,clientY:before.top+24}));"
                        "window.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,button:0,pointerId:21,clientX:before.left+120,clientY:before.top+64}));"
                        "window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,pointerId:21,clientX:before.left+120,clientY:before.top+64}));"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
                        "const after=first.getBoundingClientRect();"
                        "const resize=second.querySelector('.evidence-window-resize');"
                        "if(!resize){return {ok:false,reason:'resize_handle'};}"
                        "const resizeBefore=second.getBoundingClientRect();"
                        "resize.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerId:22,clientX:resizeBefore.right-4,clientY:resizeBefore.bottom-4}));"
                        "window.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,button:0,pointerId:22,clientX:resizeBefore.right+76,clientY:resizeBefore.bottom+46}));"
                        "window.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,pointerId:22,clientX:resizeBefore.right+76,clientY:resizeBefore.bottom+46}));"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
                        "const resizeAfter=second.getBoundingClientRect();"
                        "const pin=first.querySelector('[data-window-action=pin]');"
                        "const minimize=second.querySelector('[data-window-action=minimize]');"
                        "if(!pin||!minimize){return {ok:false,reason:'controls'};}"
                        "pin.click();minimize.click();"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
                        "let stored=[];"
                        "try{stored=JSON.parse(localStorage.getItem('crypto-signal-stream-v1-s9-windows')||'[]');}catch{}"
                        "const detach=first.querySelector('[data-window-action=detach]');"
                        "const detachUrl=detach&&detach.dataset?detach.dataset.detachUrl:'';"
                        "const stream=document.getElementById('streamViewport');"
                        "const streamVisible=!!stream&&stream.getBoundingClientRect().height>100;"
                        "return {"
                        "ok:true,count:wins.length,identities,kinds,"
                        "dragDx:Math.round(after.left-before.left),dragDy:Math.round(after.top-before.top),"
                        "resizeDw:Math.round(resizeAfter.width-resizeBefore.width),resizeDh:Math.round(resizeAfter.height-resizeBefore.height),"
                        "pinned:first.classList.contains('is-pinned'),"
                        "minimized:second.classList.contains('is-minimized'),"
                        "storedCount:Array.isArray(stored)?stored.length:-1,"
                        "detachUrl,streamVisible,"
                        "thirdPinned:third.classList.contains('is-pinned')"
                        "};"
                        "})()"
                    ),
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )
            raw_window_probe = window_probe_result.get("result", {})
            if not isinstance(raw_window_probe, dict):
                raise RuntimeError("CDP window-manager probe result missing")
            window_probe = raw_window_probe.get("value", {})
            if not isinstance(window_probe, dict):
                raise RuntimeError("CDP window-manager probe value missing")
            if window_probe.get("ok") is not True:
                raise RuntimeError(f"evidence window-manager probe failed: {window_probe!r}")
            if int(window_probe.get("count", 0)) < 3:
                raise RuntimeError(f"evidence multi-window count failed: {window_probe!r}")
            drag_dx = abs(int(window_probe.get("dragDx", 0)))
            drag_dy = abs(int(window_probe.get("dragDy", 0)))
            if drag_dx + drag_dy < 30 or max(drag_dx, drag_dy) < 15:
                raise RuntimeError(f"evidence drag probe failed: {window_probe!r}")
            if int(window_probe.get("resizeDw", 0)) < 40 or int(
                window_probe.get("resizeDh", 0)
            ) < 25:
                raise RuntimeError(f"evidence resize probe failed: {window_probe!r}")
            if window_probe.get("pinned") is not True:
                raise RuntimeError(f"evidence pin probe failed: {window_probe!r}")
            if window_probe.get("minimized") is not True:
                raise RuntimeError(f"evidence minimize probe failed: {window_probe!r}")
            if int(window_probe.get("storedCount", 0)) < 3:
                raise RuntimeError(f"evidence session persistence failed: {window_probe!r}")
            detach_url = str(window_probe.get("detachUrl", ""))
            if "/stream-evidence?narrative=" not in detach_url or "&kind=" not in detach_url:
                raise RuntimeError(f"evidence detach identity URL failed: {window_probe!r}")
            if window_probe.get("streamVisible") is not True:
                raise RuntimeError(f"evidence windows hid Stream surface: {window_probe!r}")
            metrics["window_manager_probe"] = window_probe

        if args.probe_frozen_proof:
            proof_probe_result = session.command(
                "Runtime.evaluate",
                {
                    "expression": (
                        "(async()=>{"
                        "await new Promise(r=>setTimeout(r,260));"
                        "const win=document.querySelector('.evidence-window[data-kind=proof]');"
                        "if(!win){return {ok:false,reason:'proof_window_missing'};}"
                        "const proof=win.querySelector('.frozen-visual-proof');"
                        "const chart=win.querySelector('.frozen-proof-chart');"
                        "if(!proof||!chart){return {ok:false,reason:'chart_missing'};}"
                        "const candles=[...chart.querySelectorAll('[data-candle-identity]')];"
                        "const annotations=[...chart.querySelectorAll('[data-annotation-identity]')];"
                        "const candleIds=candles.map(n=>n.getAttribute('data-candle-identity')||'');"
                        "const annotationIds=annotations.map(n=>n.getAttribute('data-annotation-identity')||'');"
                        "const sourceIds=annotations.map(n=>n.getAttribute('data-source-evidence-identity')||'').filter(Boolean);"
                        "const provenance=[...win.querySelectorAll('.frozen-proof-identities code')].map(n=>({kind:n.dataset.identityKind||'',text:n.textContent||''}));"
                        "const domains=[...win.querySelectorAll('.frozen-proof-domain')].map(n=>({domain:n.dataset.domain||'',state:n.dataset.visualState||''}));"
                        "const resolved=domains.filter(x=>x.state==='resolved_frozen_bundle').length;"
                        "const identityOnly=domains.filter(x=>x.state==='identity_only').length;"
                        "const unavailable=domains.filter(x=>x.state==='unavailable').length;"
                        "const stream=document.getElementById('streamViewport');"
                        "const streamVisible=!!stream&&stream.getBoundingClientRect().height>100;"
                        "const textContent=proof.textContent||'';"
                        "return {ok:true,candleCount:candles.length,annotationCount:annotations.length,"
                        "allCandleIds:candleIds.every(Boolean),allAnnotationIds:annotationIds.every(Boolean),"
                        "sourceIdentityCount:sourceIds.length,provenanceKinds:provenance.map(x=>x.kind),"
                        "resolved,identityOnly,unavailable,streamVisible,"
                        "currentDataSubstitutionNone:textContent.includes('Current-data substitution: YOK'),"
                        "narrativeIdentity:proof.dataset.narrativeIdentity||''"
                        "};"
                        "})()"
                    ),
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )
            raw_proof_probe = proof_probe_result.get("result", {})
            if not isinstance(raw_proof_probe, dict):
                raise RuntimeError("CDP frozen-proof probe result missing")
            proof_probe = raw_proof_probe.get("value", {})
            if not isinstance(proof_probe, dict):
                raise RuntimeError("CDP frozen-proof probe value missing")
            if proof_probe.get("ok") is not True:
                raise RuntimeError(f"frozen visual proof probe failed: {proof_probe!r}")
            if int(proof_probe.get("candleCount", 0)) < 20:
                raise RuntimeError(f"frozen proof candle coverage failed: {proof_probe!r}")
            if int(proof_probe.get("annotationCount", 0)) < 3:
                raise RuntimeError(f"frozen proof annotation coverage failed: {proof_probe!r}")
            if proof_probe.get("allCandleIds") is not True:
                raise RuntimeError(f"frozen proof candle identity failed: {proof_probe!r}")
            if proof_probe.get("allAnnotationIds") is not True:
                raise RuntimeError(f"frozen proof annotation identity failed: {proof_probe!r}")
            if int(proof_probe.get("sourceIdentityCount", 0)) < 2:
                raise RuntimeError(f"frozen proof source identity failed: {proof_probe!r}")
            provenance_kinds = set(proof_probe.get("provenanceKinds", []))
            if not {"message", "forecast", "proof", "signal", "bundle"}.issubset(
                provenance_kinds
            ):
                raise RuntimeError(f"frozen proof provenance incomplete: {proof_probe!r}")
            if int(proof_probe.get("resolved", 0)) < 2:
                raise RuntimeError(f"frozen proof resolved-domain coverage failed: {proof_probe!r}")
            if int(proof_probe.get("identityOnly", 0)) < 2:
                raise RuntimeError(f"frozen proof identity-only contract failed: {proof_probe!r}")
            if int(proof_probe.get("unavailable", 0)) < 1:
                raise RuntimeError(f"frozen proof unavailable-domain contract failed: {proof_probe!r}")
            if proof_probe.get("streamVisible") is not True:
                raise RuntimeError(f"frozen proof hid Stream surface: {proof_probe!r}")
            if proof_probe.get("currentDataSubstitutionNone") is not True:
                raise RuntimeError(f"frozen proof substitution boundary failed: {proof_probe!r}")
            metrics["frozen_proof_probe"] = proof_probe

        if args.probe_capital_story:
            capital_probe_result = session.command(
                "Runtime.evaluate",
                {
                    "expression": (
                        "(async()=>{"
                        "await new Promise(r=>setTimeout(r,260));"
                        "const expected=['capital_candidate','capital_eligible','capital_hold','capital_blocked','capital_sized','capital_executed','capital_reduced','capital_exited','capital_accounting_updated','capital_outcome'];"
                        "const messages=[...document.querySelectorAll('.message[data-subtype]')];"
                        "const subtypes=messages.map(n=>n.dataset.subtype||'');"
                        "const ids=messages.map(n=>n.dataset.identity||'');"
                        "const vaults=[...new Set(messages.map(n=>n.dataset.vaultId||'').filter(Boolean))];"
                        "const labels=messages.map(n=>n.querySelector('.message-state')?.textContent||'');"
                        "const expanded=document.querySelector('.message.is-expanded');"
                        "const detail=expanded?.querySelector('.message-detail');"
                        "const detailText=detail?.textContent||'';"
                        "const lineageCodes=detail?[...detail.querySelectorAll('.proof-panel code')].map(n=>n.textContent||''):[];"
                        "const stream=document.getElementById('streamViewport');"
                        "const streamVisible=!!stream&&stream.getBoundingClientRect().height>100;"
                        "return {ok:true,count:messages.length,subtypes,ids,vaults,labels,"
                        "missing:expected.filter(x=>!subtypes.includes(x)),"
                        "validIds:ids.every(v=>/^[0-9a-f]{64}$/.test(v)),"
                        "expandedSubtype:expanded?.dataset.subtype||'',"
                        "detailHasRealCapital:detailText.includes('REAL_CAPITAL=0'),"
                        "detailHasPnl:detailText.includes('Gerçekleşen PnL'),"
                        "lineageCodeCount:lineageCodes.length,streamVisible};"
                        "})()"
                    ),
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )
            raw_capital_probe = capital_probe_result.get("result", {})
            if not isinstance(raw_capital_probe, dict):
                raise RuntimeError("CDP capital-story probe result missing")
            capital_probe = raw_capital_probe.get("value", {})
            if not isinstance(capital_probe, dict):
                raise RuntimeError("CDP capital-story probe value missing")
            if capital_probe.get("ok") is not True:
                raise RuntimeError(f"capital story probe failed: {capital_probe!r}")
            if int(capital_probe.get("count", 0)) < 10:
                raise RuntimeError(f"capital story message count failed: {capital_probe!r}")
            if capital_probe.get("missing"):
                raise RuntimeError(f"capital story lifecycle incomplete: {capital_probe!r}")
            if capital_probe.get("validIds") is not True:
                raise RuntimeError(f"capital story identity coverage failed: {capital_probe!r}")
            vaults = set(capital_probe.get("vaults", []))
            if not {"CORE", "TACTICAL", "OPPORTUNITY_RESERVE"}.issubset(vaults):
                raise RuntimeError(f"capital story three-vault coverage failed: {capital_probe!r}")
            labels = set(capital_probe.get("labels", []))
            if not {
                "SERMAYE ADAYI",
                "SERMAYE UYGUN",
                "NAKİTTE BEKLE",
                "SERMAYE BLOKE",
                "SERMAYE BOYUTLANDI",
                "SERMAYE İŞLENDİ",
                "POZİSYON AZALTILDI",
                "POZİSYON KAPANDI",
                "MUHASEBE GÜNCELLENDİ",
                "SONUÇ KAYDEDİLDİ",
            }.issubset(labels):
                raise RuntimeError(f"capital story state labels failed: {capital_probe!r}")
            if capital_probe.get("expandedSubtype") != "capital_outcome":
                raise RuntimeError(f"capital outcome expansion failed: {capital_probe!r}")
            if capital_probe.get("detailHasRealCapital") is not True:
                raise RuntimeError(f"capital REAL_CAPITAL boundary failed: {capital_probe!r}")
            if capital_probe.get("detailHasPnl") is not True:
                raise RuntimeError(f"capital PnL detail failed: {capital_probe!r}")
            if int(capital_probe.get("lineageCodeCount", 0)) < 3:
                raise RuntimeError(f"capital lineage display failed: {capital_probe!r}")
            if capital_probe.get("streamVisible") is not True:
                raise RuntimeError(f"capital fixture hid Stream surface: {capital_probe!r}")
            metrics["capital_story_probe"] = capital_probe

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
    parser.add_argument("--probe-expansion-anchor", action="store_true")
    parser.add_argument("--probe-window-manager", action="store_true")
    parser.add_argument("--probe-frozen-proof", action="store_true")
    parser.add_argument("--probe-capital-story", action="store_true")
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
        f"expansion_probe={'YES' if metrics.get('expansion_probe') else 'NO'}",
        f"window_manager_probe={'YES' if metrics.get('window_manager_probe') else 'NO'}",
        f"frozen_proof_probe={'YES' if metrics.get('frozen_proof_probe') else 'NO'}",
        f"capital_story_probe={'YES' if metrics.get('capital_story_probe') else 'NO'}",
    )


if __name__ == "__main__":
    main()
