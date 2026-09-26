from __future__ import annotations

import argparse
import base64
import json
import os
import re
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

    def command(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout_seconds: float = 12.0,
    ) -> dict[str, Any]:
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
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                raw = self._socket.recv(timeout=min(2.0, remaining))
            except TimeoutError:
                continue
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

        if args.probe_discovery:
            discovery_probe_result = session.command(
                "Runtime.evaluate",
                {
                    "expression": (
                        "(async()=>{"
                        "await new Promise(r=>setTimeout(r,260));"
                        "const api=window.__cryptoSignalStreamS12;"
                        "if(!api){return {ok:false,reason:'s12_api_missing'};}"
                        "const ids=['searchInput','symbolFilter','categoryFilter','timeframeFilter','vaultFilter','evidenceFilter','stateFilter','importanceFilter','fromDateFilter','toDateFilter','clearFiltersButton','applyFiltersButton'];"
                        "const missing=ids.filter(id=>!document.getElementById(id));"
                        "if(missing.length){return {ok:false,reason:'controls_missing',missing};}"
                        "const initialMessage=new URL(location.href).searchParams.get('message')||'';"
                        "const initialExpanded=[...document.querySelectorAll('.message.is-expanded')].some(n=>(n.dataset.identity||'')===initialMessage);"
                        "document.getElementById('applyFiltersButton').click();"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
                        "const applied=api.discoverySnapshot();"
                        "const query=api.queryParams({limit:50}).toString();"
                        "document.getElementById('filterButton').click();"
                        "document.getElementById('categoryFilter').value='capital';"
                        "document.getElementById('vaultFilter').value='CORE';"
                        "document.getElementById('evidenceFilter').value='';"
                        "document.getElementById('stateFilter').value='capital_executed';"
                        "document.getElementById('applyFiltersButton').click();"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
                        "const capital=api.discoverySnapshot();"
                        "const capitalQuery=api.queryParams({limit:50}).toString();"
                        "document.getElementById('filterButton').click();"
                        "document.getElementById('clearFiltersButton').click();"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
                        "const cleared=api.discoverySnapshot();"
                        "const clearedQuery=api.queryParams({limit:50}).toString();"
                        "const first=document.querySelector('.message:not(.is-expanded) .message-summary');"
                        "if(!(first instanceof HTMLButtonElement)){return {ok:false,reason:'collapsed_message_missing'};}"
                        "const target=first.closest('.message');"
                        "if(!(target instanceof HTMLElement)){return {ok:false,reason:'message_target_missing'};}"
                        "first.click();"
                        "await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));"
                        "const expanded=target.classList.contains('is-expanded')?target:null;"
                        "const deepLink=new URL(location.href).searchParams.get('message')||'';"
                        "const detail=expanded?.querySelector('.message-detail');"
                        "const proofAction=!!expanded?.querySelector('.proof-action');"
                        "document.getElementById('filterButton').click();"
                        "document.getElementById('searchInput').value='likidite';"
                        "document.getElementById('symbolFilter').value='BTCUSDT';"
                        "document.getElementById('categoryFilter').value='decision';"
                        "document.getElementById('timeframeFilter').value='4h';"
                        "document.getElementById('evidenceFilter').value='order_flow_cvd';"
                        "document.getElementById('stateFilter').value='watch';"
                        "document.getElementById('importanceFilter').value='important';"
                        "document.getElementById('fromDateFilter').value='2026-09-20';"
                        "document.getElementById('toDateFilter').value='2026-09-25';"
                        "const stream=document.getElementById('streamViewport');"
                        "return {ok:true,missing,initialMessage,initialExpanded,"
                        "appliedFilters:applied.filters,query,capitalFilters:capital.filters,capitalQuery,"
                        "clearedFilters:cleared.filters,clearedQuery,deepLink,"
                        "expandedIdentity:expanded?.dataset.identity||'',"
                        "detailVisible:!!detail&&!detail.hidden,"
                        "detailLength:(detail?.textContent||'').length,"
                        "proofAction,drawerOpen:!document.getElementById('discoveryDrawer').hidden,"
                        "streamVisible:!!stream&&stream.getBoundingClientRect().height>100"
                        "};"
                        "})()"
                    ),
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )
            discovery_exception = discovery_probe_result.get("exceptionDetails")
            if isinstance(discovery_exception, dict):
                description = discovery_exception.get("text", "unknown JS exception")
                exception_object = discovery_exception.get("exception", {})
                if isinstance(exception_object, dict):
                    description = str(
                        exception_object.get("description", description)
                    )
                raise RuntimeError(
                    f"CDP discovery probe JavaScript exception: {description}"
                )
            raw_discovery_probe = discovery_probe_result.get("result", {})
            if not isinstance(raw_discovery_probe, dict):
                raise RuntimeError("CDP discovery probe result missing")
            discovery_probe = raw_discovery_probe.get("value", {})
            if not isinstance(discovery_probe, dict):
                raise RuntimeError("CDP discovery probe value missing")
            if discovery_probe.get("ok") is not True:
                raise RuntimeError(f"discovery probe failed: {discovery_probe!r}")
            if discovery_probe.get("initialExpanded") is not True:
                raise RuntimeError(f"discovery direct deep-link failed: {discovery_probe!r}")
            query = str(discovery_probe.get("query", ""))
            for expected in (
                "text=likidite",
                "symbol=BTCUSDT",
                "category=decision",
                "timeframe=4h",
                "evidence_domain=order_flow_cvd",
                "state=watch",
                "importance=important",
                "from_ms=",
                "to_ms=",
            ):
                if expected not in query:
                    raise RuntimeError(
                        f"discovery query missing {expected}: {discovery_probe!r}"
                    )
            capital_query = str(discovery_probe.get("capitalQuery", ""))
            if "vault=CORE" not in capital_query or "state=capital_executed" not in capital_query:
                raise RuntimeError(f"discovery capital filters failed: {discovery_probe!r}")
            if str(discovery_probe.get("clearedQuery", "")) != "limit=50":
                raise RuntimeError(f"discovery clear filters failed: {discovery_probe!r}")
            deep_link = str(discovery_probe.get("deepLink", ""))
            expanded_identity = str(discovery_probe.get("expandedIdentity", ""))
            if not re.fullmatch(r"[0-9a-f]{64}", deep_link) or deep_link != expanded_identity:
                raise RuntimeError(f"discovery exact message link failed: {discovery_probe!r}")
            if discovery_probe.get("detailVisible") is not True or int(
                discovery_probe.get("detailLength", 0)
            ) < 40:
                raise RuntimeError(f"discovery exact detail failed: {discovery_probe!r}")
            if discovery_probe.get("proofAction") is not True:
                raise RuntimeError(f"discovery evidence action failed: {discovery_probe!r}")
            if discovery_probe.get("drawerOpen") is not True:
                raise RuntimeError(f"discovery drawer fixture failed: {discovery_probe!r}")
            if discovery_probe.get("streamVisible") is not True:
                raise RuntimeError(f"discovery hid Stream surface: {discovery_probe!r}")
            metrics["discovery_probe"] = discovery_probe

        if args.probe_notifications:
            notification_probe_result = session.command(
                "Runtime.evaluate",
                {
                    "expression": (
                        "(async()=>{"
                        "await new Promise(r=>setTimeout(r,260));"
                        "const api=window.__cryptoSignalStreamS13;"
                        "if(!api){return {ok:false,reason:'s13_api_missing'};}"
                        "const ids=['soundEnabledToggle','soundModeSelect','soundVolumeInput',"
                        "'soundUnlockButton','testChimeButton','desktopNotificationToggle',"
                        "'desktopPermissionButton','soundStatusPill'];"
                        "const missing=ids.filter(id=>!document.getElementById(id));"
                        "if(missing.length){return {ok:false,reason:'controls_missing',missing};}"
                        "api.resetNotificationAudit();"
                        "api.setNotificationSettings({enabled:true,volume:0.33,mode:'important',desktopEnabled:false});"
                        "document.getElementById('soundUnlockButton').click();"
                        "await new Promise(r=>setTimeout(r,120));"
                        "const unlocked=api.notificationSnapshot();"
                        "const hex=n=>n.toString(16).padStart(64,'0');"
                        "const first=api.simulateFixtureDelivery({identity:hex(9101),category:'decision',importance:'important',delivery:'live_new'});"
                        "const afterFirst=api.notificationSnapshot();"
                        "const duplicate=api.simulateFixtureDelivery({identity:hex(9101),category:'decision',importance:'important',delivery:'live_new'});"
                        "const history=api.simulateFixtureDelivery({identity:hex(9102),category:'decision',importance:'important',delivery:'history'});"
                        "const replay=api.simulateFixtureDelivery({identity:hex(9103),category:'capital',importance:'important',delivery:'replay'});"
                        "const routine=api.simulateFixtureDelivery({identity:hex(9104),category:'decision',importance:'routine',delivery:'live_new'});"
                        "api.setNotificationSettings({enabled:true,volume:0.33,mode:'decision_capital',desktopEnabled:false});"
                        "const capital=api.simulateFixtureDelivery({identity:hex(9105),category:'capital',importance:'routine',delivery:'live_new'});"
                        "api.setNotificationSettings({enabled:false,volume:0.33,mode:'decision_capital',desktopEnabled:false});"
                        "const disabled=api.simulateFixtureDelivery({identity:hex(9106),category:'decision',importance:'important',delivery:'live_new'});"
                        "const final=api.notificationSnapshot();"
                        "let persisted=null;"
                        "try{persisted=JSON.parse(localStorage.getItem(final.storageKey)||'null');}catch{}"
                        "const stream=document.getElementById('streamViewport');"
                        "return {ok:true,missing,"
                        "unlocked:unlocked.unlocked,audioState:unlocked.audioState,"
                        "first,afterFirst:afterFirst.audit,duplicate,history,replay,routine,capital,disabled,"
                        "final:final.audit,persisted,"
                        "permissionRequests:final.audit.permissionRequests,"
                        "statusText:document.getElementById('soundStatusPill')?.textContent||'',"
                        "drawerOpen:!document.getElementById('settingsDrawer').hidden,"
                        "streamVisible:!!stream&&stream.getBoundingClientRect().height>100"
                        "};"
                        "})()"
                    ),
                    "awaitPromise": True,
                    "returnByValue": True,
                    "userGesture": True,
                },
            )
            notification_exception = notification_probe_result.get("exceptionDetails")
            if isinstance(notification_exception, dict):
                description = notification_exception.get(
                    "text",
                    "unknown notification JS exception",
                )
                exception_object = notification_exception.get("exception", {})
                if isinstance(exception_object, dict):
                    description = str(
                        exception_object.get("description", description)
                    )
                raise RuntimeError(
                    f"CDP notification probe JavaScript exception: {description}"
                )
            raw_notification_probe = notification_probe_result.get("result", {})
            if not isinstance(raw_notification_probe, dict):
                raise RuntimeError("CDP notification probe result missing")
            notification_probe = raw_notification_probe.get("value", {})
            if not isinstance(notification_probe, dict):
                raise RuntimeError("CDP notification probe value missing")
            if notification_probe.get("ok") is not True:
                raise RuntimeError(
                    f"notification probe failed: {notification_probe!r}"
                )
            if notification_probe.get("unlocked") is not True:
                raise RuntimeError(
                    f"notification audio unlock failed: {notification_probe!r}"
                )
            if notification_probe.get("audioState") != "running":
                raise RuntimeError(
                    f"notification audio state failed: {notification_probe!r}"
                )
            first = notification_probe.get("first", {})
            after_first = notification_probe.get("afterFirst", {})
            if (
                not isinstance(first, dict)
                or first.get("eligible") is not True
                or first.get("sounded") is not True
                or int(after_first.get("chimePlayed", 0)) != 1
            ):
                raise RuntimeError(
                    f"notification single live chime failed: {notification_probe!r}"
                )
            duplicate = notification_probe.get("duplicate", {})
            if (
                not isinstance(duplicate, dict)
                or duplicate.get("reason") != "duplicate"
            ):
                raise RuntimeError(
                    f"notification identity dedupe failed: {notification_probe!r}"
                )
            for key in ("history", "replay"):
                item = notification_probe.get(key, {})
                if (
                    not isinstance(item, dict)
                    or item.get("reason") != "delivery_silent"
                ):
                    raise RuntimeError(
                        f"notification {key} silence failed: {notification_probe!r}"
                    )
            routine = notification_probe.get("routine", {})
            disabled = notification_probe.get("disabled", {})
            if (
                not isinstance(routine, dict)
                or routine.get("reason") != "mode_filtered"
                or not isinstance(disabled, dict)
                or disabled.get("reason") != "mode_filtered"
            ):
                raise RuntimeError(
                    f"notification optional/mode filter failed: {notification_probe!r}"
                )
            capital = notification_probe.get("capital", {})
            if (
                not isinstance(capital, dict)
                or capital.get("eligible") is not True
                or capital.get("sounded") is not True
            ):
                raise RuntimeError(
                    f"notification Decision+Capital mode failed: {notification_probe!r}"
                )
            final_audit = notification_probe.get("final", {})
            if (
                int(final_audit.get("chimePlayed", 0)) != 2
                or int(final_audit.get("duplicate", 0)) != 1
                or int(final_audit.get("suppressedDelivery", 0)) != 2
                or int(notification_probe.get("permissionRequests", -1)) != 0
            ):
                raise RuntimeError(
                    f"notification delivery accounting failed: {notification_probe!r}"
                )
            persisted = notification_probe.get("persisted", {})
            if (
                not isinstance(persisted, dict)
                or persisted.get("enabled") is not False
                or persisted.get("mode") != "decision_capital"
                or abs(float(persisted.get("volume", -1)) - 0.33) > 0.001
            ):
                raise RuntimeError(
                    f"notification settings persistence failed: {notification_probe!r}"
                )
            if notification_probe.get("drawerOpen") is not True:
                raise RuntimeError(
                    f"notification settings drawer failed: {notification_probe!r}"
                )
            if notification_probe.get("streamVisible") is not True:
                raise RuntimeError(
                    f"notification fixture hid Stream: {notification_probe!r}"
                )
            metrics["notification_probe"] = notification_probe

        if args.probe_s15_end_to_end:
            s15_probe_expression = r"""
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const waitFor = async (predicate, timeoutMs = 16000) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      try {
        const value = predicate();
        if (value) return value;
      } catch {}
      await sleep(50);
    }
    throw new Error("s15_wait_timeout");
  };
  const fetchJson = async (url) => {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`${url} -> ${response.status}`);
    return await response.json();
  };

  await waitFor(
    () =>
      window.__cryptoSignalStreamS12 &&
      window.__cryptoSignalStreamS13 &&
      document.querySelectorAll(".message[data-identity]").length === 1
  );
  const s12 = window.__cryptoSignalStreamS12;
  const s13 = window.__cryptoSignalStreamS13;
  const rootCard = document.querySelector(".message[data-identity]");
  const rootId = rootCard?.dataset.identity || "";
  if (!/^[0-9a-f]{64}$/.test(rootId)) {
    return { ok: false, reason: "root_identity_missing", rootId };
  }

  const rootBeforeEnvelope = await fetchJson(
    `/api/stream/messages/${encodeURIComponent(rootId)}`
  );
  const rootBefore = rootBeforeEnvelope.message;
  const rootDetailEnvelope = await fetchJson(
    `/api/stream/messages/${encodeURIComponent(rootId)}/detail`
  );
  const rootDetail = rootDetailEnvelope.detail;
  if (!rootBefore || !rootDetail?.fact_bundle) {
    return { ok: false, reason: "root_api_truth_missing" };
  }
  const rootCollapsed = rootBefore?.text?.collapsed_text || "";
  const storyIdentity = rootBefore?.story_identity || "";
  const forecastIdentity = rootDetail.fact_bundle.forecast_identity || "";
  const proofIdentity = rootDetail.fact_bundle.proof_identity || "";

  await s12.focusRenderedMessage(rootId);
  await waitFor(() =>
    document.querySelector(
      `.message[data-identity="${rootId}"].is-expanded [data-evidence-kind="proof"]`
    )
  );
  const expandedRoot = document.querySelector(
    `.message[data-identity="${rootId}"].is-expanded`
  );
  const detail = expandedRoot?.querySelector(".message-detail");
  const detailText = detail?.textContent || "";
  const familyCount = detail?.querySelectorAll(".family-card").length || 0;
  const depthLabels = [
    "SIMPLE",
    "PRO",
    "INTELLIGENCE",
    "DECISION",
    "CAPITAL",
  ];
  const depthCoverage = depthLabels.every((label) => detailText.includes(label));

  const proofButton = expandedRoot?.querySelector(
    '[data-evidence-kind="proof"]'
  );
  if (!(proofButton instanceof HTMLButtonElement)) {
    return { ok: false, reason: "proof_button_missing_after_detail_ready" };
  }
  proofButton.click();
  await waitFor(() =>
    document.querySelector(
      '.evidence-window[data-kind="proof"] .frozen-proof-chart'
    )
  );
  const proofWindow = document.querySelector(
    '.evidence-window[data-kind="proof"]'
  );
  const proofCandles = proofWindow?.querySelectorAll(
    "[data-candle-identity]"
  ).length || 0;
  const proofAnnotations = proofWindow?.querySelectorAll(
    "[data-annotation-identity]"
  ).length || 0;
  const proofText = proofWindow?.textContent || "";

  s13.resetNotificationAudit();
  s13.setNotificationSettings({
    enabled: true,
    volume: 0.28,
    mode: "decision_capital",
    desktopEnabled: false,
  });
  document.getElementById("soundUnlockButton")?.click();
  await waitFor(() => s13.notificationSnapshot()?.unlocked === true);
  const unlocked = s13.notificationSnapshot();

  await waitFor(
    () => document.querySelectorAll(".message[data-identity]").length >= 2
  );
  const afterResolutionAudit = s13.notificationSnapshot();
  const afterResolutionCards = [
    ...document.querySelectorAll(".message[data-identity]"),
  ];
  const resolutionCard = afterResolutionCards.find(
    (node) =>
      node.dataset.identity !== rootId &&
      node.dataset.category !== "capital"
  );
  const resolutionId = resolutionCard?.dataset.identity || "";
  if (!/^[0-9a-f]{64}$/.test(resolutionId)) {
    return { ok: false, reason: "resolution_identity_missing", resolutionId };
  }

  const resolutionEnvelope = await fetchJson(
    `/api/stream/messages/${encodeURIComponent(resolutionId)}`
  );
  const rootAfterResolution = (
    await fetchJson(`/api/stream/messages/${encodeURIComponent(rootId)}`)
  ).message;
  const resolutionMessage = resolutionEnvelope.message;

  await waitFor(
    () =>
      [...document.querySelectorAll(".message[data-identity]")].some(
        (node) => node.dataset.category === "capital"
      )
  );
  const afterCapitalAudit = s13.notificationSnapshot();
  const capitalCard = [
    ...document.querySelectorAll(".message[data-identity]"),
  ].find((node) => node.dataset.category === "capital");
  const capitalId = capitalCard?.dataset.identity || "";
  if (!/^[0-9a-f]{64}$/.test(capitalId)) {
    return { ok: false, reason: "capital_identity_missing", capitalId };
  }
  const capitalMessage = (
    await fetchJson(`/api/stream/messages/${encodeURIComponent(capitalId)}`)
  ).message;

  const oldMessageUnchanged =
    rootAfterResolution?.narrative_identity === rootBefore?.narrative_identity &&
    rootAfterResolution?.text?.collapsed_text === rootCollapsed;
  const coherentStory =
    resolutionMessage?.story_identity === storyIdentity &&
    resolutionMessage?.narrative_identity !== rootId;
  const exactCapitalLineage =
    capitalMessage?.forecast_identity === forecastIdentity &&
    capitalMessage?.proof_identity === proofIdentity &&
    /^[0-9a-f]{64}$/.test(capitalMessage?.bundle_identity || "") &&
    /^[0-9a-f]{64}$/.test(capitalMessage?.intent_identity || "") &&
    /^[0-9a-f]{64}$/.test(capitalMessage?.fill_identity || "") &&
    capitalMessage?.real_capital === 0 &&
    capitalMessage?.production_authority === false;

  const searchInput = document.getElementById("searchInput");
  const symbolFilter = document.getElementById("symbolFilter");
  const categoryFilter = document.getElementById("categoryFilter");
  const timeframeFilter = document.getElementById("timeframeFilter");
  const applyFilters = document.getElementById("applyFiltersButton");
  const clearFilters = document.getElementById("clearFiltersButton");
  const searchNeedle = rootCollapsed.slice(0, 36).trim();
  if (
    !(searchInput instanceof HTMLInputElement) ||
    !(symbolFilter instanceof HTMLSelectElement) ||
    !(categoryFilter instanceof HTMLSelectElement) ||
    !(timeframeFilter instanceof HTMLSelectElement) ||
    !(applyFilters instanceof HTMLButtonElement) ||
    !(clearFilters instanceof HTMLButtonElement)
  ) {
    return { ok: false, reason: "discovery_controls_missing" };
  }
  searchInput.value = searchNeedle;
  symbolFilter.value = "BTCUSDT";
  categoryFilter.value = "decision";
  timeframeFilter.value = "4h";
  applyFilters.click();
  await waitFor(() => {
    const snapshot = s12.discoverySnapshot();
    return (
      snapshot.filters.text === searchNeedle &&
      document.querySelector(
        `.message[data-identity="${rootId}"]`
      )
    );
  });
  const searchFoundRoot = !!document.querySelector(
    `.message[data-identity="${rootId}"]`
  );
  await s12.focusRenderedMessage(rootId);
  const deepLinkIdentity = new URL(window.location.href).searchParams.get(
    "message"
  );

  clearFilters.click();
  await waitFor(
    () => document.querySelectorAll(".message[data-identity]").length >= 3
  );
  await s12.focusRenderedMessage(capitalId);
  await waitFor(() =>
    document.querySelector(
      `.message[data-identity="${capitalId}"].is-expanded .message-detail`
    )
  );
  const capitalDetail = document.querySelector(
    `.message[data-identity="${capitalId}"].is-expanded .message-detail`
  );
  const capitalDetailText = capitalDetail?.textContent || "";
  const capitalLineageCodes =
    capitalDetail?.querySelectorAll(".proof-panel code").length || 0;

  const stream = document.getElementById("streamViewport");
  return {
    ok: true,
    rootId,
    resolutionId,
    capitalId,
    storyIdentity,
    rootCollapsed,
    familyCount,
    depthCoverage,
    proofCandles,
    proofAnnotations,
    proofHasNoSubstitution: proofText.includes(
      "Current-data substitution: YOK"
    ),
    audioUnlocked: unlocked.unlocked,
    audioState: unlocked.audioState,
    afterResolutionAudit: afterResolutionAudit.audit,
    afterResolutionDelivered: afterResolutionAudit.deliveredCount,
    afterCapitalAudit: afterCapitalAudit.audit,
    afterCapitalDelivered: afterCapitalAudit.deliveredCount,
    oldMessageUnchanged,
    coherentStory,
    exactCapitalLineage,
    searchFoundRoot,
    deepLinkIdentity,
    capitalDetailHasRealCapital:
      capitalDetailText.includes("REAL_CAPITAL=0"),
    capitalLineageCodeCount: capitalLineageCodes,
    totalMessages:
      document.querySelectorAll(".message[data-identity]").length,
    streamVisible:
      !!stream && stream.getBoundingClientRect().height > 100,
    connectionLabel:
      document.getElementById("connectionLabel")?.textContent || "",
  };
})()
"""
            s15_probe_result = session.command(
                "Runtime.evaluate",
                {
                    "expression": s15_probe_expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                    "userGesture": True,
                },
                timeout_seconds=40.0,
            )
            s15_exception = s15_probe_result.get("exceptionDetails")
            if isinstance(s15_exception, dict):
                description = s15_exception.get(
                    "text",
                    "unknown S15 JavaScript exception",
                )
                exception_object = s15_exception.get("exception", {})
                if isinstance(exception_object, dict):
                    description = str(
                        exception_object.get("description", description)
                    )
                raise RuntimeError(
                    f"CDP S15 end-to-end JavaScript exception: {description}"
                )
            raw_s15_probe = s15_probe_result.get("result", {})
            if not isinstance(raw_s15_probe, dict):
                raise RuntimeError("CDP S15 end-to-end probe result missing")
            s15_probe = raw_s15_probe.get("value", {})
            if not isinstance(s15_probe, dict):
                raise RuntimeError("CDP S15 end-to-end probe value missing")
            if s15_probe.get("ok") is not True:
                raise RuntimeError(
                    f"S15 end-to-end probe failed: {s15_probe!r}"
                )
            if int(s15_probe.get("familyCount", 0)) != 5:
                raise RuntimeError(
                    f"S15 five-family detail failed: {s15_probe!r}"
                )
            if s15_probe.get("depthCoverage") is not True:
                raise RuntimeError(
                    f"S15 depth explanation failed: {s15_probe!r}"
                )
            if int(s15_probe.get("proofCandles", 0)) < 20:
                raise RuntimeError(
                    f"S15 frozen candle proof failed: {s15_probe!r}"
                )
            if int(s15_probe.get("proofAnnotations", 0)) < 3:
                raise RuntimeError(
                    f"S15 frozen annotation proof failed: {s15_probe!r}"
                )
            if s15_probe.get("proofHasNoSubstitution") is not True:
                raise RuntimeError(
                    f"S15 frozen proof substitution boundary failed: {s15_probe!r}"
                )
            if (
                s15_probe.get("audioUnlocked") is not True
                or s15_probe.get("audioState") != "running"
            ):
                raise RuntimeError(
                    f"S15 audio unlock failed: {s15_probe!r}"
                )
            after_resolution = s15_probe.get("afterResolutionAudit", {})
            if (
                not isinstance(after_resolution, dict)
                or int(after_resolution.get("chimeDispatches", 0)) != 1
                or int(after_resolution.get("chimePlayed", 0)) != 1
                or int(s15_probe.get("afterResolutionDelivered", 0)) != 1
            ):
                raise RuntimeError(
                    f"S15 first live exactly-once chime failed: {s15_probe!r}"
                )
            after_capital = s15_probe.get("afterCapitalAudit", {})
            if (
                not isinstance(after_capital, dict)
                or int(after_capital.get("chimeDispatches", 0)) != 2
                or int(after_capital.get("chimePlayed", 0)) != 2
                or int(after_capital.get("duplicate", 0)) != 0
                or int(s15_probe.get("afterCapitalDelivered", 0)) != 2
            ):
                raise RuntimeError(
                    f"S15 second live exactly-once chime failed: {s15_probe!r}"
                )
            for key in (
                "oldMessageUnchanged",
                "coherentStory",
                "exactCapitalLineage",
                "searchFoundRoot",
                "capitalDetailHasRealCapital",
                "streamVisible",
            ):
                if s15_probe.get(key) is not True:
                    raise RuntimeError(
                        f"S15 {key} acceptance failed: {s15_probe!r}"
                    )
            if s15_probe.get("deepLinkIdentity") != s15_probe.get("rootId"):
                raise RuntimeError(
                    f"S15 deep-link acceptance failed: {s15_probe!r}"
                )
            if int(s15_probe.get("capitalLineageCodeCount", 0)) < 3:
                raise RuntimeError(
                    f"S15 capital lineage detail failed: {s15_probe!r}"
                )
            if int(s15_probe.get("totalMessages", 0)) < 3:
                raise RuntimeError(
                    f"S15 final Stream message count failed: {s15_probe!r}"
                )
            metrics["s15_end_to_end_probe"] = s15_probe

        if args.probe_long_session:
            session.command(
                "Emulation.setEmulatedMedia",
                {
                    "features": [
                        {
                            "name": "prefers-reduced-motion",
                            "value": "reduce",
                        }
                    ]
                },
            )
            long_probe_expression = r"""
(async () => {
  const wait = () =>
    new Promise((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(resolve))
    );
  await new Promise((resolve) => setTimeout(resolve, 260));
  const api = window.__cryptoSignalStreamS14;
  const viewport = document.getElementById("streamViewport");
  const list = document.getElementById("messageList");
  if (!api || !viewport || !list) {
    return { ok: false, reason: "s14_surface_missing" };
  }

  const initial = api.snapshot();
  const initialMessages = [...list.querySelectorAll(".message")];
  const ariaOk = initialMessages.every(
    (node, index) =>
      node.getAttribute("role") === "article" &&
      Number(node.getAttribute("aria-setsize")) === initial.totalMessages &&
      Number(node.getAttribute("aria-posinset")) ===
        initial.renderStart + index + 1
  );
  const feedRole = list.getAttribute("role");

  viewport.scrollTop = 0;
  const firstInitial = list.querySelector(".message");
  const firstId = firstInitial?.dataset.identity || "";
  const firstTop = firstInitial?.getBoundingClientRect().top ?? 0;
  api.shiftOlder();
  await wait();
  await new Promise((resolve) => setTimeout(resolve, 60));
  const afterOlder = api.snapshot();
  const retainedOlder = list.querySelector(
    `.message[data-identity="${firstId}"]`
  );
  const olderDrift = retainedOlder
    ? Math.abs(retainedOlder.getBoundingClientRect().top - firstTop)
    : 9999;

  viewport.scrollTop = viewport.scrollHeight;
  const lastBeforeNew = [...list.querySelectorAll(".message")].at(-1);
  const lastId = lastBeforeNew?.dataset.identity || "";
  const lastTop = lastBeforeNew?.getBoundingClientRect().top ?? 0;
  api.shiftNewer();
  await wait();
  await new Promise((resolve) => setTimeout(resolve, 60));
  const afterNewer = api.snapshot();
  const retainedNew = list.querySelector(
    `.message[data-identity="${lastId}"]`
  );
  const newerDrift = retainedNew
    ? Math.abs(retainedNew.getBoundingClientRect().top - lastTop)
    : 9999;

  const visibleMessages = [...list.querySelectorAll(".message")];
  const anchor = visibleMessages[Math.min(20, visibleMessages.length - 1)];
  anchor?.scrollIntoView({ block: "center" });
  await wait();
  const prependId = anchor?.dataset.identity || "";
  const prependTop = anchor?.getBoundingClientRect().top ?? 0;
  const prependResult = api.prependFixturePage(50);
  await wait();
  await new Promise((resolve) => setTimeout(resolve, 60));
  const afterPrepend = api.snapshot();
  const prependAnchor = list.querySelector(
    `.message[data-identity="${prependId}"]`
  );
  const prependDrift = prependAnchor
    ? Math.abs(prependAnchor.getBoundingClientRect().top - prependTop)
    : 9999;

  const expandable = [...list.querySelectorAll(".message")].find(
    (node) => node.querySelector(".message-summary") && node.dataset.identity
  );
  expandable?.scrollIntoView({ block: "center" });
  await wait();
  const expansionTop = expandable?.getBoundingClientRect().top ?? 0;
  expandable?.querySelector(".message-summary")?.click();
  await wait();
  await new Promise((resolve) => setTimeout(resolve, 120));
  const expansionDrift = expandable
    ? Math.abs(expandable.getBoundingClientRect().top - expansionTop)
    : 9999;
  const expanded = Boolean(expandable?.classList.contains("is-expanded"));

  const searchButton = document.getElementById("searchButton");
  searchButton?.focus();
  api.openDiscovery();
  await wait();
  const drawer = document.getElementById("discoveryDrawer");
  const focusInside = Boolean(drawer?.contains(document.activeElement));
  const focusables = drawer
    ? [
        ...drawer.querySelectorAll(
          'button:not([disabled]),input:not([disabled]),select:not([disabled]),' +
            'textarea:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])'
        ),
      ].filter((node) => !node.hidden)
    : [];
  const firstFocus = focusables[0];
  const lastFocus = focusables.at(-1);
  lastFocus?.focus();
  document.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Tab", bubbles: true })
  );
  const tabWrapped = document.activeElement === firstFocus;
  document.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
  );
  await wait();
  const escapeClosed = drawer?.hidden === true;
  const focusRestored = document.activeElement === searchButton;

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const transition = getComputedStyle(
    list.querySelector(".message")
  ).transitionDuration;
  document.documentElement.style.fontSize = "125%";
  await wait();
  const fontScaleNoOverflow =
    document.documentElement.scrollWidth <= window.innerWidth;
  document.documentElement.style.fontSize = "";
  const final = api.snapshot();

  return {
    ok: true,
    feedRole,
    ariaOk,
    initial,
    afterOlder,
    afterNewer,
    olderDrift,
    newerDrift,
    prependResult,
    afterPrepend,
    prependDrift,
    expanded,
    expansionDrift,
    focusInside,
    tabWrapped,
    escapeClosed,
    focusRestored,
    reduced,
    transition,
    fontScaleNoOverflow,
    final,
  };
})()
"""
            long_probe_result = session.command(
                "Runtime.evaluate",
                {
                    "expression": long_probe_expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )
            raw_long_probe = long_probe_result.get("result", {})
            if not isinstance(raw_long_probe, dict):
                raise RuntimeError("CDP long-session probe result missing")
            long_probe = raw_long_probe.get("value", {})
            if not isinstance(long_probe, dict) or long_probe.get("ok") is not True:
                raise RuntimeError(f"long-session probe failed: {long_probe!r}")
            initial = long_probe.get("initial", {})
            after_older = long_probe.get("afterOlder", {})
            after_newer = long_probe.get("afterNewer", {})
            after_prepend = long_probe.get("afterPrepend", {})
            final = long_probe.get("final", {})
            if int(initial.get("totalMessages", 0)) != 10_000:
                raise RuntimeError(f"10k fixture state failed: {long_probe!r}")
            if not 1 <= int(initial.get("renderedMessages", 0)) <= 180:
                raise RuntimeError(f"bounded DOM window failed: {long_probe!r}")
            if long_probe.get("feedRole") != "feed" or long_probe.get("ariaOk") is not True:
                raise RuntimeError(f"feed accessibility semantics failed: {long_probe!r}")
            if int(after_older.get("renderStart", -1)) >= int(initial.get("renderStart", -1)):
                raise RuntimeError(f"virtual older shift failed: {long_probe!r}")
            if float(long_probe.get("olderDrift", 9999)) > 6:
                raise RuntimeError(f"virtual older anchor drift failed: {long_probe!r}")
            if int(after_newer.get("renderStart", -1)) <= int(after_older.get("renderStart", -1)):
                raise RuntimeError(f"virtual newer shift failed: {long_probe!r}")
            if float(long_probe.get("newerDrift", 9999)) > 6:
                raise RuntimeError(f"virtual newer anchor drift failed: {long_probe!r}")
            prepend_result = long_probe.get("prependResult", {})
            if prepend_result.get("ok") is not True or int(prepend_result.get("count", 0)) != 50:
                raise RuntimeError(f"reverse-prepend fixture failed: {long_probe!r}")
            if int(after_prepend.get("totalMessages", 0)) != 10_050:
                raise RuntimeError(f"reverse-prepend state count failed: {long_probe!r}")
            if float(long_probe.get("prependDrift", 9999)) > 6:
                raise RuntimeError(f"reverse-prepend anchor drift failed: {long_probe!r}")
            if long_probe.get("expanded") is not True:
                raise RuntimeError(f"long-session expansion failed: {long_probe!r}")
            if float(long_probe.get("expansionDrift", 9999)) > 6:
                raise RuntimeError(f"long-session expansion anchor drift failed: {long_probe!r}")
            for key in ("focusInside", "tabWrapped", "escapeClosed", "focusRestored"):
                if long_probe.get(key) is not True:
                    raise RuntimeError(f"drawer keyboard accessibility failed: {long_probe!r}")
            if long_probe.get("reduced") is not True or long_probe.get("transition") not in {"0s", "0s, 0s, 0s"}:
                raise RuntimeError(f"reduced-motion acceptance failed: {long_probe!r}")
            if long_probe.get("fontScaleNoOverflow") is not True:
                raise RuntimeError(f"font scaling overflow failed: {long_probe!r}")
            if int(final.get("renderedMessages", 9999)) > 180:
                raise RuntimeError(f"final bounded DOM failed: {long_probe!r}")
            if int(final.get("detailCacheSize", 9999)) > 80:
                raise RuntimeError(f"detail-cache bound failed: {long_probe!r}")
            if float(final.get("lastRenderDurationMs", 9999)) > 1000:
                raise RuntimeError(f"long-session render latency failed: {long_probe!r}")
            heap_usage = session.command("Runtime.getHeapUsage")
            used_heap = float(heap_usage.get("usedSize", -1))
            if used_heap < 0 or used_heap > 160 * 1024 * 1024:
                raise RuntimeError(
                    f"long-session JS heap outside acceptance bound: {used_heap}"
                )
            long_probe["jsHeapUsedBytes"] = used_heap
            metrics["long_session_probe"] = long_probe

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
    parser.add_argument("--probe-discovery", action="store_true")
    parser.add_argument("--probe-notifications", action="store_true")
    parser.add_argument("--probe-long-session", action="store_true")
    parser.add_argument("--probe-s15-end-to-end", action="store_true")
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
        f"discovery_probe={'YES' if metrics.get('discovery_probe') else 'NO'}",
        f"notification_probe={'YES' if metrics.get('notification_probe') else 'NO'}",
        f"long_session_probe={'YES' if metrics.get('long_session_probe') else 'NO'}",
        f"s15_end_to_end_probe={'YES' if metrics.get('s15_end_to_end_probe') else 'NO'}",
    )


if __name__ == "__main__":
    main()
