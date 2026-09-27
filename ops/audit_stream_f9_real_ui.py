from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ops.capture_chromium_viewport import CdpSession, _free_port, _wait_target

REAL_CAPITAL = 0
DEPTH_LABELS = {"SIMPLE", "PRO", "INTELLIGENCE", "DECISION", "CAPITAL"}


class F9AuditError(RuntimeError):
    pass


def _get_json(
    base_url: str,
    path: str,
    params: dict[str, object] | None = None,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(
            {key: str(value) for key, value in params.items()}
        )
    with urllib.request.urlopen(url, timeout=10) as response:
        raw = json.loads(response.read().decode("utf-8"))
    if not isinstance(raw, dict):
        raise F9AuditError(f"{path} did not return an object")
    return raw


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("items")
    if not isinstance(raw, list):
        page = payload.get("page")
        raw = page.get("items") if isinstance(page, dict) else []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _identity(item: dict[str, Any]) -> str:
    value = str(item.get("narrative_identity", ""))
    if len(value) != 64:
        raise F9AuditError("production message has invalid narrative identity")
    return value


def _category_items(base_url: str, category: str) -> list[dict[str, Any]]:
    payload = _get_json(
        base_url,
        "/api/stream/messages",
        {"category": category, "limit": 200},
    )
    return _items(payload)


def _annotated_category_item(
    items: dict[str, list[dict[str, Any]]],
    categories: tuple[str, ...],
) -> dict[str, Any] | None:
    for category in categories:
        values = items.get(category, [])
        if not values:
            continue
        item = dict(values[0])
        item["_f9_observed_category"] = category
        return item
    return None


def inventory(base_url: str) -> dict[str, object]:
    health = _get_json(base_url, "/api/health")
    page = _get_json(base_url, "/api/stream/messages", {"limit": 200})
    messages = _items(page)
    by_category = {
        category: _category_items(base_url, category)
        for category in (
            "market",
            "intelligence",
            "risk",
            "system",
            "capital",
        )
    }
    categories = sorted(
        category for category, values in by_category.items() if values
    )
    primary = _annotated_category_item(
        by_category,
        ("market", "intelligence"),
    )
    degraded = _annotated_category_item(
        by_category,
        ("risk", "system"),
    )
    capital = _annotated_category_item(by_category, ("capital",))
    return {
        "health": health,
        "message_count": len(messages),
        "categories": categories,
        "observed_counts": {
            category: len(values)
            for category, values in by_category.items()
        },
        "primary": primary,
        "degraded": degraded,
        "capital": capital,
    }


def _value(result: dict[str, Any]) -> object:
    if "exceptionDetails" in result:
        raise F9AuditError(f"CDP exception: {result['exceptionDetails']!r}")
    outer = result.get("result")
    if not isinstance(outer, dict):
        raise F9AuditError("CDP result missing")
    return outer.get("value")


def _eval(
    session: CdpSession,
    expression: str,
    *,
    await_promise: bool = False,
) -> object:
    return _value(
        session.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
            timeout_seconds=30.0,
        )
    )


def _wait_identity(identity: str) -> str:
    encoded = json.dumps(identity)
    return (
        "(async()=>{for(let i=0;i<80;i++){"
        f"const id={encoded};"
        "const n=[...document.querySelectorAll('.message')]"
        ".find(x=>x.dataset.identity===id);"
        "if(n)return true;await new Promise(r=>setTimeout(r,100));}"
        "return false;})()"
    )


def _wait_live_root() -> str:
    return (
        "(async()=>{for(let i=0;i<120;i++){"
        "const params=new URLSearchParams(location.search);"
        "const count=document.querySelectorAll('.message').length;"
        "const transport=(document.getElementById('transportMode')?.textContent||'').trim();"
        "const label=(document.getElementById('connectionLabel')?.textContent||'').trim();"
        "if(location.pathname==='/'&&!params.get('message')&&!params.get('fixture')"
        "&&count>0&&transport==='SSE CANLI'&&label==='CANLI')"
        "return {ready:true,count,transport,label};"
        "await new Promise(r=>setTimeout(r,100));}"
        "return {ready:false,count:document.querySelectorAll('.message').length,"
        "transport:(document.getElementById('transportMode')?.textContent||'').trim(),"
        "label:(document.getElementById('connectionLabel')?.textContent||'').trim()};})()"
    )


def _snapshot(identity: str) -> str:
    encoded = json.dumps(identity)
    return (
        "(()=>{"
        f"const id={encoded};"
        "const n=[...document.querySelectorAll('.message')]"
        ".find(x=>x.dataset.identity===id)||null;"
        "return {path:location.pathname,"
        "fixture:new URLSearchParams(location.search).get('fixture')||'',"
        "identity:n?.dataset?.identity||'',"
        "category:n?.dataset?.category||'',"
        "copy:(n?.querySelector('.message-copy')?.textContent||'').trim(),"
        "state:(n?.querySelector('.message-state')?.textContent||'').trim(),"
        "meta:[...n?.querySelectorAll('.message-meta>*')||[]]"
        ".map(x=>(x.textContent||'').trim()),"
        "chips:[...n?.querySelectorAll('.message-chips>*')||[]]"
        ".map(x=>(x.textContent||'').trim()),"
        "scrollWidth:document.documentElement.scrollWidth,"
        "innerWidth:window.innerWidth,"
        "soundControls:Boolean(document.getElementById('soundButton')&&"
        "document.getElementById('soundEnabledToggle'))};})()"
    )


def _interaction(identity: str, category: str, search_text: str) -> str:
    identity_js = json.dumps(identity)
    category_js = json.dumps(category)
    search_js = json.dumps(search_text)
    return (
        "(async()=>{"
        f"const id={identity_js},cat={category_js},searchText={search_js};"
        "const find=()=>[...document.querySelectorAll('.message')]"
        ".find(x=>x.dataset.identity===id)||null;"
        "let n=find();if(!n)return {error:'message_missing'};"
        "let summary=n.querySelector('.message-summary');"
        "let detail=n.querySelector('.message-detail');"
        "if(summary?.getAttribute('aria-expanded')!=='true'||!detail||detail.hidden)"
        "summary?.click();"
        "let evidence=[];"
        "for(let i=0;i<70;i++){n=find();detail=n?.querySelector('.message-detail')||null;"
        "evidence=n?[...n.querySelectorAll('[data-evidence-kind]')]:[];"
        "if(detail&&!detail.hidden&&evidence.length)break;"
        "await new Promise(r=>setTimeout(r,100));}"
        "for(const b of evidence.slice(0,3)){b.click();"
        "await new Promise(r=>setTimeout(r,180));}"
        "const wins=[...document.querySelectorAll('.evidence-window')];"
        "const detach=wins.map(w=>w.querySelector('[data-window-action=detach]')"
        "?.dataset?.detachUrl||'').filter(Boolean);"
        "document.getElementById('soundButton')?.click();"
        "await new Promise(r=>setTimeout(r,80));"
        "const soundDrawerOpen=document.getElementById('settingsDrawer')"
        "?.hidden===false;"
        "document.querySelector('[data-close-drawer=settingsDrawer]')?.click();"
        "window.__f9SearchFetches=[];"
        "const nativeFetch=window.fetch.bind(window);"
        "window.fetch=async(...args)=>{const u=String(args[0] instanceof Request?"
        "args[0].url:args[0]);const response=await nativeFetch(...args);"
        "if(u.includes('/api/stream/messages?')){const clone=response.clone();"
        "let count=null;try{const body=await clone.json();"
        "const items=Array.isArray(body?.page?.items)?body.page.items:"
        "(Array.isArray(body?.items)?body.items:[]);count=items.length;}catch{}"
        "window.__f9SearchFetches.push({url:u,http:response.status,count});}"
        "return response;};"
        "document.getElementById('searchButton')?.click();"
        "await new Promise(r=>setTimeout(r,80));"
        "const q=document.getElementById('searchInput');if(q)q.value=searchText;"
        "const f=document.getElementById('categoryFilter');if(f)f.value=cat;"
        "document.getElementById('applyFiltersButton')?.click();"
        "for(let i=0;i<120;i++){const kept=find();"
        "const d=window.__cryptoSignalStreamS12?.discoverySnapshot?.()||null;"
        "const done=window.__f9SearchFetches.some(x=>x?.http===200&&"
        "Number(x?.count)>=1);"
        "if(kept&&done&&d?.filters?.text===searchText&&d?.filters?.category===cat)"
        "break;await new Promise(r=>setTimeout(r,100));}"
        "const retained=Boolean(find());"
        "document.getElementById('searchButton')?.click();"
        "await new Promise(r=>setTimeout(r,80));"
        "if(q)q.value='F9_NO_MATCH_'+id;if(f)f.value='';"
        "document.getElementById('applyFiltersButton')?.click();"
        "for(let i=0;i<80;i++){if(document.getElementById('emptyState')"
        "?.hidden===false)break;await new Promise(r=>setTimeout(r,100));}"
        "const emptyVisible=document.getElementById('emptyState')?.hidden===false;"
        "return {expanded:Boolean(detail&&!detail.hidden),"
        "detailText:(detail?.textContent||'').trim(),"
        "labels:[...n.querySelectorAll('.depth-heading span')]"
        ".map(x=>(x.textContent||'').trim()),"
        "evidenceButtonCount:evidence.length,evidenceWindowCount:wins.length,"
        "detachUrls:detach,soundDrawerOpen,searchRetainedExact:retained,"
        "emptyStateVisible:emptyVisible};})()"
    )


def _observe_incoming(
    session: CdpSession,
    wait_seconds: int,
) -> dict[str, object]:
    baseline = _eval(
        session,
        (
            "(async()=>{"
            "const viewport=document.getElementById('streamViewport');"
            "if(viewport){viewport.scrollTop=viewport.scrollHeight;"
            "await new Promise(r=>setTimeout(r,120));"
            "viewport.scrollTop=0;await new Promise(r=>setTimeout(r,120));}"
            "const button=document.getElementById('newMessageButton');"
            "return {ids:[...document.querySelectorAll('.message')]"
            ".map(n=>n.dataset.identity||'').filter(Boolean),"
            "unreadAffordance:button?.hidden===false,"
            "count:document.getElementById('newMessageCount')?.textContent||''};"
            "})()"
        ),
        await_promise=True,
    )
    if not isinstance(baseline, dict):
        raise F9AuditError("live-root incoming baseline unavailable")
    if baseline.get("unreadAffordance") is True:
        raise F9AuditError("live-root unread affordance was already active at baseline")
    raw_before = baseline.get("ids")
    before = (
        {str(value) for value in raw_before}
        if isinstance(raw_before, list)
        else set()
    )
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(0.5)
        current = _eval(
            session,
            (
                "(()=>{"
                "const ids=[...document.querySelectorAll('.message')]"
                ".map(n=>n.dataset.identity||'').filter(Boolean);"
                "const button=document.getElementById('newMessageButton');"
                "return {ids,unreadAffordance:button?.hidden===false,"
                "count:document.getElementById('newMessageCount')?.textContent||'',"
                "transport:(document.getElementById('transportMode')?.textContent||'').trim(),"
                "label:(document.getElementById('connectionLabel')?.textContent||'').trim()};"
                "})()"
            ),
        )
        if not isinstance(current, dict):
            continue
        raw_ids = current.get("ids")
        ids = (
            [str(value) for value in raw_ids]
            if isinstance(raw_ids, list)
            else []
        )
        fresh = [value for value in ids if value not in before]
        unread = current.get("unreadAffordance") is True
        if fresh or unread:
            return {
                "required": True,
                "observed": True,
                "unread_affordance": unread,
                "fresh_identities": fresh,
                "unread_count": current.get("count", ""),
                "transport": current.get("transport", ""),
                "connection_label": current.get("label", ""),
            }
    return {
        "required": True,
        "observed": False,
        "unread_affordance": False,
        "fresh_identities": [],
        "unread_count": "",
        "transport": "SSE CANLI",
        "connection_label": "CANLI",
    }


def _screenshot(session: CdpSession, path: Path) -> None:
    raw = session.command(
        "Page.captureScreenshot",
        {"format": "png", "captureBeyondViewport": False},
    )
    data = raw.get("data")
    if not isinstance(data, str) or not data:
        raise F9AuditError("screenshot missing")
    path.write_bytes(base64.b64decode(data))


def incoming_live_probe(
    *,
    browser: Path,
    base_url: str,
    width: int,
    height: int,
    wait_seconds: int,
    screenshot: Path,
) -> dict[str, object]:
    port = _free_port()
    profile = screenshot.parent / f".f9-live-profile-{os.getpid()}"
    log_path = screenshot.parent / "f9-chrome-live.log"
    url = base_url.rstrip("/") + "/"
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
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
        with log_path.open("wb") as handle:
            process = subprocess.Popen(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        target = _wait_target(port, url)
        ws = target.get("webSocketDebuggerUrl")
        if not isinstance(ws, str):
            raise F9AuditError("live-root Chromium websocket unavailable")
        session = CdpSession(ws)
        session.command("Page.enable")
        session.command("Runtime.enable")
        session.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
                "screenWidth": width,
                "screenHeight": height,
            },
        )
        session.command("Page.navigate", {"url": url})
        ready = _eval(session, _wait_live_root(), await_promise=True)
        if not isinstance(ready, dict) or ready.get("ready") is not True:
            raise F9AuditError(f"live mixed Stream did not reach SSE ready state: {ready!r}")
        incoming = _observe_incoming(session, wait_seconds)
        _screenshot(session, screenshot)
        return {
            "path": "/",
            "fixture": False,
            "deep_link": False,
            "sse_ready": True,
            "initial_message_count": int(ready.get("count", 0)),
            "transport": ready.get("transport", ""),
            "connection_label": ready.get("label", ""),
            **incoming,
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


def browser_probe(
    *,
    browser: Path,
    base_url: str,
    item: dict[str, Any],
    width: int,
    height: int,
    mobile: bool,
    screenshot: Path,
) -> dict[str, object]:
    identity = _identity(item)
    category = str(
        item.get("category")
        or item.get("_f9_observed_category")
        or ""
    )
    symbol = str(item.get("symbol", "")).strip()
    timeframe = str(item.get("timeframe", "")).strip()
    text_bundle = item.get("text")
    search_text = (
        str(text_bundle.get("collapsed_text", ""))
        if isinstance(text_bundle, dict)
        else ""
    )
    search_text = search_text.strip() or symbol or timeframe or identity[:12]
    port = _free_port()
    profile = screenshot.parent / f".f9-profile-{width}-{os.getpid()}"
    log_path = screenshot.parent / f"f9-chrome-{width}.log"
    url = base_url.rstrip("/") + "/?message=" + identity
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
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
        with log_path.open("wb") as handle:
            process = subprocess.Popen(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        target = _wait_target(port, url)
        ws = target.get("webSocketDebuggerUrl")
        if not isinstance(ws, str):
            raise F9AuditError("Chromium websocket unavailable")
        session = CdpSession(ws)
        session.command("Page.enable")
        session.command("Runtime.enable")
        session.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": mobile,
                "screenWidth": width,
                "screenHeight": height,
            },
        )
        session.command("Page.navigate", {"url": url})
        if _eval(session, _wait_identity(identity), await_promise=True) is not True:
            raise F9AuditError("production message did not render on Product root")
        initial = _eval(session, _snapshot(identity))
        if not isinstance(initial, dict):
            raise F9AuditError("browser snapshot invalid")

        interaction = _eval(
            session,
            _interaction(identity, category, search_text),
            await_promise=True,
        )
        if not isinstance(interaction, dict) or interaction.get("error"):
            raise F9AuditError(f"browser interaction failed: {interaction!r}")
        _screenshot(session, screenshot)

        meta_raw = initial.get("meta")
        meta = (
            {str(value) for value in meta_raw}
            if isinstance(meta_raw, list)
            else set()
        )
        labels_raw = interaction.get("labels")
        labels = (
            {str(value) for value in labels_raw}
            if isinstance(labels_raw, list)
            else set()
        )
        detail_text = str(interaction.get("detailText", "")).casefold()
        chips_raw = initial.get("chips")
        chips = (
            [str(value) for value in chips_raw]
            if isinstance(chips_raw, list)
            else []
        )
        summary_surface = " ".join(
            [str(initial.get("state", "")), *chips]
        ).casefold()
        importance = str(item.get("importance", "")).strip().casefold()
        comprehension = {
            "what_changed": bool(str(initial.get("copy", "")).strip()),
            "asset_timeframe": symbol in meta and timeframe in meta,
            "system_view": bool(str(initial.get("state", "")).strip()),
            "importance_visible": not importance or importance in summary_surface,
            "next_condition": "sonraki koşul" in detail_text
            or "geçersizleş" in detail_text,
            "proof_entry": int(interaction.get("evidenceButtonCount", 0)) >= 1,
        }
        detach_raw = interaction.get("detachUrls")
        detach_urls = (
            [str(value) for value in detach_raw]
            if isinstance(detach_raw, list)
            else []
        )
        checks = {
            "product_root": initial.get("path") == "/",
            "no_fixture": not initial.get("fixture"),
            "no_horizontal_overflow": int(initial.get("scrollWidth", 999999))
            <= int(initial.get("innerWidth", -1)),
            "real_message_rendered": initial.get("identity") == identity,
            "message_expansion": interaction.get("expanded") is True,
            "depths": DEPTH_LABELS.issubset(labels),
            "evidence_window": int(interaction.get("evidenceWindowCount", 0)) >= 1,
            "multiple_evidence_windows": int(
                interaction.get("evidenceWindowCount", 0)
            )
            >= 2,
            "detached_proof": any(
                "/stream-evidence?narrative=" in value for value in detach_urls
            ),
            "search_filter": interaction.get("searchRetainedExact") is True,
            "empty_state": interaction.get("emptyStateVisible") is True,
            "sound_controls": initial.get("soundControls") is True
            and interaction.get("soundDrawerOpen") is True,
            "ten_second_comprehension": all(comprehension.values()),
        }
        return {
            "identity": identity,
            "category": category,
            "viewport": [width, height],
            "mobile": mobile,
            "initial": initial,
            "interaction": interaction,
            "comprehension": comprehension,
            "checks": checks,
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


def run(args: argparse.Namespace) -> dict[str, object]:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    inv = inventory(args.base_url)
    health = inv.get("health")
    if not isinstance(health, dict):
        raise F9AuditError("health unavailable")
    if int(health.get("real_capital", -1)) != REAL_CAPITAL:
        raise F9AuditError("REAL_CAPITAL boundary changed")
    if health.get("read_only") is not True:
        raise F9AuditError("Product is not read-only")

    primary = inv.get("primary")
    if not isinstance(primary, dict):
        return {
            "schema_version": "stream-final-f9-real-ui-v1/3",
            "status": "OPEN_NO_REAL_MESSAGES",
            "inventory": inv,
            "open_requirements": ["real_mixed_message_stream"],
            "historical_backfill_used": False,
            "synthetic_activity_used": False,
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }

    desktop = browser_probe(
        browser=args.browser,
        base_url=args.base_url,
        item=primary,
        width=1440,
        height=1000,
        mobile=False,
        screenshot=args.output.parent / "f9-desktop.png",
    )
    mobile = browser_probe(
        browser=args.browser,
        base_url=args.base_url,
        item=primary,
        width=430,
        height=860,
        mobile=True,
        screenshot=args.output.parent / "f9-mobile.png",
    )
    incoming_live: dict[str, object] = {
        "required": args.require_incoming,
        "observed": False,
        "unread_affordance": False,
    }
    if args.require_incoming:
        incoming_live = incoming_live_probe(
            browser=args.browser,
            base_url=args.base_url,
            width=1440,
            height=1000,
            wait_seconds=args.incoming_wait_seconds,
            screenshot=args.output.parent / "f9-live-incoming.png",
        )

    open_requirements: list[str] = []
    for name, probe in (("desktop", desktop), ("mobile", mobile)):
        checks = probe.get("checks")
        if not isinstance(checks, dict):
            raise F9AuditError(f"{name} browser checks missing")
        open_requirements.extend(
            f"{name}:{key}" for key, value in checks.items() if value is not True
        )

    categories_raw = inv.get("categories")
    categories = (
        set(categories_raw) if isinstance(categories_raw, list) else set()
    )
    if not ({"market", "intelligence"} & categories):
        open_requirements.append("market_or_intelligence_message")
    if not ({"risk", "system"} & categories):
        open_requirements.append("degraded_source_message")
    if args.require_capital and "capital" not in categories:
        open_requirements.append("capital_message")

    if args.require_incoming:
        if incoming_live.get("sse_ready") is not True:
            open_requirements.append("live_root_sse")
        if incoming_live.get("observed") is not True:
            open_requirements.append("incoming_live_message")
        elif incoming_live.get("unread_affordance") is not True:
            open_requirements.append("unread_new_message_affordance")

    report: dict[str, object] = {
        "schema_version": "stream-final-f9-real-ui-v1/2",
        "status": "PASS_CANDIDATE" if not open_requirements else "OPEN",
        "inventory": inv,
        "desktop": desktop,
        "mobile": mobile,
        "incoming_live": incoming_live,
        "open_requirements": sorted(set(open_requirements)),
        "scope": {
            "physically_required": ["market_or_intelligence", "risk_or_system"],
            "deferred": ["decision", "outcome", "capital_portfolio"],
        },
        "historical_backfill_used": False,
        "synthetic_activity_used": False,
        "read_only": True,
        "production_authority": False,
        "real_capital": REAL_CAPITAL,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:48700")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--require-capital", action="store_true")
    parser.add_argument("--require-incoming", action="store_true")
    parser.add_argument("--incoming-wait-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.incoming_wait_seconds < 0:
        parser.error("--incoming-wait-seconds must be non-negative")

    report = run(args)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    open_values = report.get("open_requirements")
    open_requirements = (
        [str(value) for value in open_values]
        if isinstance(open_values, list)
        else []
    )
    print(f"F9_REAL_UI_STATUS={report['status']}")
    print(f"F9_OPEN_REQUIREMENTS={','.join(open_requirements) or 'NONE'}")
    print("HISTORICAL_BACKFILL=NO")
    print("SYNTHETIC_ACTIVITY=NO")
    print("REAL_CAPITAL=0")
    if args.require_complete and report["status"] != "PASS_CANDIDATE":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
