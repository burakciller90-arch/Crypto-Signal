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


def _start_browser(browser: Path, url: str, out_dir: Path) -> tuple[subprocess.Popen[bytes], CdpSession]:
    log_path = out_dir / "mi5-browser.chrome.log"
    log_path.write_bytes(b"")
    port = _free_port()
    user_data = out_dir / f".mi5-chrome-profile-{os.getpid()}"
    command = [
        str(browser),
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
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        target = _wait_target(port, url, timeout_seconds=30.0)
        websocket_url = target.get("webSocketDebuggerUrl")
        if not isinstance(websocket_url, str):
            raise RuntimeError("Chrome target missing websocket URL")
        return process, CdpSession(websocket_url)
    except Exception:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        raise


def _capture(
    *,
    browser: Path,
    url: str,
    output: Path,
    width: int,
    height: int,
    mobile: bool,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    process, session = _start_browser(browser, url, output.parent)
    try:
        session.command("Page.enable")
        session.command("Runtime.enable")
        session.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1.0,
                "mobile": mobile,
                "screenWidth": width,
                "screenHeight": height,
            },
        )
        session.command("Page.navigate", {"url": url})

        settle = session.command(
            "Runtime.evaluate",
            {
                "expression": r"""
(async()=>{
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const deadline=Date.now()+10000;
  while(Date.now()<deadline){
    const item=document.querySelector('.message.is-expanded');
    const rows=item?[...item.querySelectorAll('.family-evidence-action')]:[];
    if(item&&rows.length===5) break;
    await sleep(120);
  }
  await sleep(350);
  return {
    innerWidth:window.innerWidth,
    innerHeight:window.innerHeight,
    scrollWidth:document.documentElement.scrollWidth,
    scrollHeight:document.documentElement.scrollHeight,
    uiVersion:document.body?.dataset?.uiVersion||''
  };
})()
""",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        metrics = settle.get("result", {}).get("value", {})
        if not isinstance(metrics, dict):
            raise RuntimeError("MI5 browser metrics missing")
        if int(metrics.get("innerWidth", -1)) != width:
            raise RuntimeError(f"MI5 viewport width mismatch: {metrics!r}")
        if int(metrics.get("scrollWidth", width + 1)) > width:
            raise RuntimeError(f"MI5 horizontal overflow: {metrics!r}")

        probe = session.command(
            "Runtime.evaluate",
            {
                "expression": r"""
(async()=>{
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const item=document.querySelector('.message.is-expanded');
  if(!item) return {ok:false,reason:'expanded_message_missing'};
  const detail=item.querySelector('.message-detail');
  if(!detail) return {ok:false,reason:'message_detail_missing'};

  const labels=[...detail.querySelectorAll('.depth-heading span')].map(n=>(n.textContent||'').trim());
  const rows=[...detail.querySelectorAll('.family-evidence-action')];
  const expected=['geometry','liquidity','order_flow','derivatives','onchain'];
  const kinds=rows.map(r=>r.dataset.evidenceKind||r.dataset.family||'');
  const raw=(document.querySelector('.message-list')?.textContent||'').toLowerCase();
  const rawTokens=[
    'sell_pressure','buy_pressure','state değişti','measured:',
    'bid_side_liquidity_take_candidate','ask_side_liquidity_take_candidate','→'
  ];
  const leaks=rawTokens.filter(token=>raw.includes(token));

  const results=[];
  for(const row of rows){
    const kind=row.dataset.evidenceKind||row.dataset.family||'';
    row.click();
    const deadline=Date.now()+5000;
    let win=null;
    while(Date.now()<deadline){
      win=document.querySelector('.evidence-window[data-kind="'+kind+'"]');
      if(win && win.querySelector('.family-frozen-proof')) break;
      await sleep(100);
    }
    if(!win){
      results.push({kind,ok:false,reason:'window_missing'});
      continue;
    }
    const proof=win.querySelector('.family-frozen-proof');
    const resolution=proof?.dataset?.resolutionState||'';
    const proofKind=proof?.dataset?.familyKind||'';
    const hasWhy=(win.textContent||'').includes('Bu mesajda neden önemli?');
    const chart=!!win.querySelector('.frozen-proof-chart');
    const currentSubstitutionText=(win.textContent||'').toLowerCase();
    const noCurrentSubstitution=
      currentSubstitutionText.includes('current data ile') ||
      currentSubstitutionText.includes('current-data substitution') ||
      currentSubstitutionText.includes('güncel veri');
    results.push({
      kind,
      ok:Boolean(proof)&&proofKind===kind&&hasWhy,
      resolution,
      proofKind,
      hasWhy,
      chart,
      noCurrentSubstitution
    });
  }

  const globalProofAction=!!detail.querySelector('.proof-action');
  const globalLauncher=!!detail.querySelector('.evidence-launcher');
  const controls={
    search:!!document.getElementById('searchButton'),
    filter:!!document.getElementById('filterButton'),
    sound:!!document.getElementById('soundButton'),
    settings:!!document.getElementById('settingsButton'),
    loadOlder:!!document.getElementById('loadOlderButton')
  };
  const connection=(document.getElementById('connectionLabel')?.textContent||'').trim();
  const transport=(document.getElementById('transportMode')?.textContent||'').trim();
  const snapshot=window.__cryptoSignalStreamS14?.snapshot?.()||null;

  return {
    ok:true,
    identity:item.dataset.identity||'',
    labels,
    rowCount:rows.length,
    kinds,
    expected,
    leaks,
    globalProofAction,
    globalLauncher,
    results,
    controls,
    connection,
    transport,
    snapshot
  };
})()
""",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        value = probe.get("result", {}).get("value", {})
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise RuntimeError(f"MI5 DOM probe failed: {value!r}")
        if int(value.get("rowCount", 0)) != 5:
            raise RuntimeError(f"MI5 five-family row count failed: {value!r}")
        if value.get("kinds") != value.get("expected"):
            raise RuntimeError(f"MI5 family order failed: {value!r}")
        if value.get("leaks"):
            raise RuntimeError(f"MI5 raw telemetry leak: {value!r}")
        if value.get("globalProofAction") is True or value.get("globalLauncher") is True:
            raise RuntimeError(f"MI5 global proof CTA still visible: {value!r}")
        labels = set(value.get("labels", []))
        if not {"KARAR ÖZETİ", "5 KANIT AİLESİ"}.issubset(labels):
            raise RuntimeError(f"MI5 hierarchy labels missing: {value!r}")
        if {"SIMPLE", "PRO", "INTELLIGENCE", "PROOF"}.intersection(labels):
            raise RuntimeError(f"MI5 legacy decision depth leaked: {value!r}")
        controls = value.get("controls", {})
        if not isinstance(controls, dict) or not all(bool(v) for v in controls.values()):
            raise RuntimeError(f"MI5 search/history/sound controls missing: {value!r}")
        results = value.get("results", [])
        if not isinstance(results, list) or len(results) != 5:
            raise RuntimeError(f"MI5 family proof results incomplete: {value!r}")
        allowed = {"READY_EXACT", "IDENTITY_ONLY_EXACT", "UNAVAILABLE_EXPLICIT"}
        for result in results:
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise RuntimeError(f"MI5 family proof window failed: {value!r}")
            if result.get("resolution") not in allowed:
                raise RuntimeError(f"MI5 proof resolution escaped contract: {value!r}")
            if result.get("kind") != "geometry" and result.get("chart") is True:
                raise RuntimeError(f"MI5 non-geometry chart authority leak: {value!r}")
        geometry = next((r for r in results if r.get("kind") == "geometry"), None)
        if geometry is None:
            raise RuntimeError(f"MI5 geometry proof missing: {value!r}")
        if geometry.get("resolution") == "READY_EXACT" and geometry.get("chart") is not True:
            raise RuntimeError(f"MI5 ready geometry proof lacks frozen chart: {value!r}")

        screenshot = session.command(
            "Page.captureScreenshot",
            {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
        )
        encoded = screenshot.get("data")
        if not isinstance(encoded, str) or not encoded:
            raise RuntimeError("MI5 screenshot payload missing")
        output.write_bytes(base64.b64decode(encoded))
        return {**metrics, "mi5_probe": value}
    finally:
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
    parser.add_argument("--metrics-out", type=Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--mobile", action="store_true")
    args = parser.parse_args()

    if not args.browser.is_file():
        raise SystemExit(f"browser missing: {args.browser}")
    metrics = _capture(
        browser=args.browser,
        url=args.url,
        output=args.output,
        width=args.width,
        height=args.height,
        mobile=args.mobile,
    )
    args.metrics_out.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("MI5_REAL_BROWSER_ACCEPTANCE_PASS=YES")
    print("REAL_CAPITAL=0")


if __name__ == "__main__":
    main()
