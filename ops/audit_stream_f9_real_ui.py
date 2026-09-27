from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import subprocess
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
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
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


def inventory(base_url: str) -> dict[str, object]:
    health = _get_json(base_url, "/api/health")
    page = _get_json(base_url, "/api/stream/messages", {"limit": 200})
    messages = _items(page)
    categories = sorted(
        {
            str(item.get("category", ""))
            for item in messages
            if item.get("category")
        }
    )
    primary = next(
        (
            item
            for item in messages
            if str(item.get("category", "")) in {"market", "intelligence"}
        ),
        messages[0] if messages else None,
    )
    degraded = next(
        (
            item
            for item in messages
            if str(item.get("category", "")) in {"risk", "system"}
        ),
        None,
    )
    capital = next(
        (item for item in messages if str(item.get("category", "")) == "capital"),
        None,
    )
    return {
        "health": health,
        "message_count": len(messages),
        "categories": categories,
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


def _incoming_probe(wait_seconds: int) -> str:
    return (
        "(async()=>{"
        "const before=new Set([...document.querySelectorAll('.message')]"
        ".map(n=>n.dataset.identity||''));"
        "const viewport=document.getElementById('streamViewport');"
        "if(viewport)viewport.scrollTop=0;"
        f"const deadline=Date.now()+{wait_seconds * 1000};"
        "while(Date.now()<deadline){await new Promise(r=>setTimeout(r,500));"
        "const ids=[...document.querySelectorAll('.message')]"
        ".map(n=>n.dataset.identity||'');"
        "const fresh=ids.filter(id=>id&&!before.has(id));"
        "const button=document.getElementById('newMessageButton');"
        "if(fresh.length||button?.hidden===false)return {observed:true,fresh,"
        "unreadAffordance:button?.hidden===false,"
        "count:document.getElementById('newMessageCount')?.textContent||''};}"
        "return {observed:false,fresh:[],unreadAffordance:false,count:''};})()"
    )


def _screenshot(session: CdpSession, path: Path) -> None:
    raw = session.command(
        "Page.captureScreenshot",
        {"format": "png", "captureBeyondViewport": False},
    )
    data = raw.get("data")
    if not isinstance(data, str) or not data:
        raise F9AuditError("screenshot missing")
    path.write_bytes(base64.b64decode(data))


def browser_probe(
    *,
    browser: Path,
    base_url: str,
    item: dict[str, Any],
    width: int,
    height: int,
    mobile: bool,
    screenshot: Path,
    incoming_wait_seconds: int = 0,
) -> dict[str, object]:
    identity = _identity(item)
    category = str(item.get("category", ""))
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

        incoming: dict[str, object] = {
            "required": incoming_wait_seconds > 0,
            "observed": False,
            "unread_affordance": False,
        }
        if incoming_wait_seconds > 0:
            incoming_result = _eval(
                session,
                _incoming_probe(incoming_wait_seconds),
                await_promise=True,
            )
            if isinstance(incoming_result, dict):
                incoming = {
                    "required": True,
                    "observed": incoming_result.get("observed") is True,
                    "unread_affordance": incoming_result.get("unreadAffordance")
                    is True,
                    "fresh_identities": incoming_result.get("fresh", []),
                    "unread_count": incoming_result.get("count", ""),
                }

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
            "incoming": incoming,
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
            "schema_version": "stream-final-f9-real-ui-v1/2",
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
        incoming_wait_seconds=(
            args.incoming_wait_seconds if args.require_incoming else 0
        ),
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
        incoming = desktop.get("incoming")
        if not isinstance(incoming, dict) or incoming.get("observed") is not True:
            open_requirements.append("incoming_live_message")
        elif incoming.get("unread_affordance") is not True:
            open_requirements.append("unread_new_message_affordance")

    report: dict[str, object] = {
        "schema_version": "stream-final-f9-real-ui-v1/2",
        "status": "PASS_CANDIDATE" if not open_requirements else "OPEN",
        "inventory": inv,
        "desktop": desktop,
        "mobile": mobile,
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
