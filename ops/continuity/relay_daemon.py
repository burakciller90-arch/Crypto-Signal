#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
QUEUE = SHARED / "queue"
RECEIPTS = SHARED / "receipts"
BAD = SHARED / "bad"
PAUSE = SHARED / "user_pause"
SECRET_FILE = SHARED / "relay_secret"
TARGET_FILE = SHARED / "current_chat_url"
HEARTBEAT = SHARED / "relay_heartbeat"
PIDFILE = SHARED / "relay.pid"
LOG = SHARED / "relay.log"
STATUS = SHARED / "relay_status"
RETRY_SECONDS = 2
AUTONOMOUS_PREFIX = "CRYPTO_SIGNAL_AUTONOMOUS_CONTINUE_V1"
TARGET_OPEN_RETRY_SECONDS = 60
_last_target_open_attempt = 0.0

APPLESCRIPT = r"""
on run argv
  set targetUrl to item 1 of argv
  set js to item 2 of argv

  try
    tell application "Google Chrome"
      repeat with w in windows
        repeat with t in tabs of w
          try
            if (URL of t as text) is targetUrl then
              try
                return execute t javascript js
              on error errMsg number errNum
                return "CHROME_JAVASCRIPT_ERROR:" & errNum & ":" & errMsg
              end try
            end if
          end try
        end repeat
      end repeat
    end tell
  on error errMsg number errNum
    if errNum is not -1728 then
      return "CHROME_AUTOMATION_ERROR:" & errNum & ":" & errMsg
    end if
  end try

  try
    tell application "Safari"
      repeat with w in windows
        repeat with t in tabs of w
          try
            if (URL of t as text) is targetUrl then
              try
                return do JavaScript js in t
              on error errMsg number errNum
                return "SAFARI_JAVASCRIPT_ERROR:" & errNum & ":" & errMsg
              end try
            end if
          end try
        end repeat
      end repeat
    end tell
  on error errMsg number errNum
    return "SAFARI_AUTOMATION_ERROR:" & errNum & ":" & errMsg
  end try

  return "TARGET_NOT_FOUND"
end run
"""
def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def scheduled_slot_event_id() -> str:
    now = datetime.now().astimezone()
    slot_minute = 0 if now.minute < 30 else 30
    slot = now.replace(minute=slot_minute, second=0, microsecond=0)
    return f"crypto-30m-continuity:{slot:%Y%m%dT%H%M%z}"


def marker_for(event_id: str) -> str:
    return f"[#cryptowake:{sha(event_id)[:16]}]"


def expected_wire_sha(event_id: str, message: str) -> str:
    wire = f"{message} {marker_for(event_id)}"
    return sha(wire)


def signature(secret: bytes, event_id: str, message: str) -> str:
    payload = f"{event_id}\n{message}".encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
    with LOG.open("a") as handle:
        handle.write(f"{stamp} {message}\n")


def write_receipt(path: Path, status: str, event_id: str, message_sha: str) -> None:
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
    tmp.write_text(
        f"status={status}\n"
        f"event_id={event_id}\n"
        f"event_key={sha(event_id)}\n"
        f"message_sha256={message_sha}\n"
        f"updated={stamp}\n"
    )
    os.chmod(tmp, 0o600)
    tmp.replace(path)
def receipt_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith("message_sha256="):
            return line.split("=", 1)[1]
    return ""


def run_js(target_url: str, js: str) -> str:
    try:
        proc = subprocess.run(
            ["/usr/bin/osascript", "-", target_url, js],
            input=APPLESCRIPT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "OSASCRIPT_TIMEOUT"
    if proc.returncode != 0:
        return f"OSASCRIPT_ERROR:{proc.returncode}:{proc.stderr.strip()}"
    return proc.stdout.strip()


def open_target_in_browser(target_url: str) -> str:
    global _last_target_open_attempt
    now = time.monotonic()
    if now - _last_target_open_attempt < TARGET_OPEN_RETRY_SECONDS:
        return "TARGET_OPEN_THROTTLED"
    _last_target_open_attempt = now
    script = r"""
on run argv
  set targetUrl to item 1 of argv

  try
    tell application "Google Chrome"
      if (count of windows) = 0 then
        make new window
      end if
      tell front window
        make new tab with properties {URL:targetUrl}
      end tell
      activate
    end tell
    return "CHROME_TARGET_OPEN_REQUESTED"
  on error chromeMsg number chromeNum
    try
      tell application "Safari"
        if (count of windows) = 0 then
          make new document with properties {URL:targetUrl}
        else
          tell front window to make new tab with properties {URL:targetUrl}
        end if
        activate
      end tell
      return "SAFARI_TARGET_OPEN_REQUESTED_AFTER_CHROME_ERROR:" & chromeNum & ":" & chromeMsg
    on error safariMsg number safariNum
      return "TARGET_OPEN_ERROR:" & safariNum & ":" & safariMsg
    end try
  end try
end run
"""
    try:
        proc = subprocess.run(
            ["/usr/bin/osascript", "-", target_url],
            input=script,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "TARGET_OPEN_TIMEOUT"
    if proc.returncode != 0:
        return f"TARGET_OPEN_ERROR:{proc.returncode}:{proc.stderr.strip()}"
    return proc.stdout.strip()


def read_event(path: Path) -> tuple[str, str, str]:
    lines = path.read_text().splitlines()
    if len(lines) < 8:
        raise ValueError("relay queue item has fewer than 8 lines")
    event_id = lines[0].strip()
    supplied_sig = lines[6].strip()
    message = lines[7].strip()
    if not event_id or not supplied_sig or not message:
        raise ValueError("relay queue item has missing required fields")
    return event_id, supplied_sig, message


def load_secret() -> bytes:
    secret = SECRET_FILE.read_text().strip().encode()
    if len(secret) < 32:
        raise ValueError("relay secret is invalid")
    return secret
def validate_event(path: Path, secret: bytes) -> tuple[str, str]:
    event_id, supplied_sig, message = read_event(path)
    expected_sig = signature(secret, event_id, message)
    if not hmac.compare_digest(supplied_sig, expected_sig):
        raise ValueError("relay event HMAC mismatch")
    return event_id, message


def deliver(event_id: str, message: str, target_url: str) -> tuple[bool, str]:
    key = sha(event_id)
    marker = marker_for(event_id)
    wire_message = f"{message} {marker}"
    message_sha = sha(wire_message)
    receipt = RECEIPTS / f"{key}.state"

    bound_sha = receipt_sha(receipt)
    if bound_sha is not None:
        if bound_sha and bound_sha != message_sha:
            return False, "EVENT_ID_MESSAGE_CONFLICT"
        return True, "ALREADY_RECEIPTED"

    if message.startswith(AUTONOMOUS_PREFIX):
        canonical_event_id = scheduled_slot_event_id()
        if event_id != canonical_event_id:
            write_receipt(
                receipt,
                "STALE_AUTONOMOUS_WAKE",
                event_id,
                message_sha,
            )
            return True, f"STALE_AUTONOMOUS_WAKE:{canonical_event_id}"

    marker_json = json.dumps(marker)
    message_json = json.dumps(wire_message)
    state_js = (
        "(()=>{const marker=" + marker_json + ";"
        "const users=[...document.querySelectorAll('[data-message-author-role=\"user\"]')];"
        "if(users.slice(-100).some(x=>(x.innerText||'').includes(marker)))return 'OBSERVED';"
        "const stop=[...document.querySelectorAll('button[data-testid=\"stop-button\"]')]"
        ".find(x=>{const s=getComputedStyle(x),r=x.getBoundingClientRect();"
        "return x.isConnected&&!x.disabled&&s.display!=='none'&&s.visibility!=='hidden'"
        "&&Number(s.opacity||1)>0&&r.width>1&&r.height>1&&x.getClientRects().length>0;});"
        "if(stop)return 'CHATGPT_BUSY';"
        "const e=document.querySelector('#prompt-textarea');"
        "if(!e)return 'NO_EDITOR';"
        "const draft=(e.innerText||'').trim();"
        "if(draft.includes(marker))return 'PREPARED';"
        "if(draft)return 'DRAFT_BUSY';return 'READY';})()"
    )
    state = run_js(target_url, state_js)
    if state == "TARGET_NOT_FOUND":
        return False, open_target_in_browser(target_url)
    if state == "OBSERVED":
        write_receipt(receipt, "OBSERVED", event_id, message_sha)
        return True, "OBSERVED"
    if state == "CHATGPT_BUSY":
        stop_js = (
            "(()=>{const stop=[...document.querySelectorAll('button[data-testid=\\\"stop-button\\\"]')]"
            ".find(x=>{const s=getComputedStyle(x),r=x.getBoundingClientRect();"
            "return x.isConnected&&!x.disabled&&s.display!=='none'&&s.visibility!=='hidden'"
            "&&Number(s.opacity||1)>0&&r.width>1&&r.height>1&&x.getClientRects().length>0;});"
            "if(!stop)return 'STOP_NOT_FOUND';stop.click();return 'STOP_CLICKED';})()"
        )
        stopped = run_js(target_url, stop_js)
        if stopped != "STOP_CLICKED":
            return False, stopped
        ready_js = (
            "(()=>{const marker=" + marker_json + ";"
            "const users=[...document.querySelectorAll('[data-message-author-role=\\\"user\\\"]')];"
            "if(users.slice(-100).some(x=>(x.innerText||'').includes(marker)))return 'OBSERVED';"
            "const stop=[...document.querySelectorAll('button[data-testid=\\\"stop-button\\\"]')]"
            ".find(x=>{const s=getComputedStyle(x),r=x.getBoundingClientRect();"
            "return x.isConnected&&!x.disabled&&s.display!=='none'&&s.visibility!=='hidden'"
            "&&Number(s.opacity||1)>0&&r.width>1&&r.height>1&&x.getClientRects().length>0;});"
            "if(stop)return 'STILL_BUSY';"
            "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
            "const draft=(e.innerText||'').trim();"
            "if(draft.includes(marker))return 'PREPARED';"
            "if(draft)return 'DRAFT_BUSY';return 'READY';})()"
        )
        for _ in range(40):
            time.sleep(0.25)
            state = run_js(target_url, ready_js)
            if state in {"READY", "PREPARED", "OBSERVED", "DRAFT_BUSY"}:
                break
        if state == "OBSERVED":
            write_receipt(receipt, "OBSERVED", event_id, message_sha)
            return True, "OBSERVED_AFTER_STOP"
        if state not in {"READY", "PREPARED"}:
            return False, f"AFTER_STOP:{state}"
    if state in {"DRAFT_BUSY", "NO_EDITOR"}:
        return False, state
    if state.startswith(
        (
            "OSASCRIPT_ERROR:",
            "CHROME_JAVASCRIPT_ERROR:",
            "CHROME_AUTOMATION_ERROR:",
            "SAFARI_JAVASCRIPT_ERROR:",
            "SAFARI_AUTOMATION_ERROR:",
        )
    ):
        return False, state

    if state == "READY":
        fill_js = (
            "(()=>{const msg=" + message_json + ";const marker=" + marker_json + ";"
            "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
            "const cur=(e.innerText||'').trim();if(cur.includes(marker))return 'FILLED';"
            "if(cur)return 'DRAFT_BUSY';e.focus();"
            "const ok=document.execCommand('insertText',false,msg);"
            "return ok&&((e.innerText||'').includes(marker))?'FILLED':'FILL_FAILED';})()"
        )
        filled = run_js(target_url, fill_js)
        if filled != "FILLED":
            return False, filled

    write_receipt(receipt, "SUBMITTING", event_id, message_sha)
    send_js = (
        "(()=>{const marker=" + marker_json + ";"
        "const users=[...document.querySelectorAll('[data-message-author-role=\"user\"]')];"
        "if(users.slice(-100).some(x=>(x.innerText||'').includes(marker)))return 'ALREADY_SENT';"
        "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
        "const draft=(e.innerText||'').trim();if(!draft.includes(marker))return 'DRAFT_CHANGED';"
        "const b=document.querySelector('button[data-testid=\"send-button\"]');"
        "if(!b||b.disabled)return 'NO_SEND';b.click();return 'CLICKED';})()"
    )
    sent = run_js(target_url, send_js)
    if sent == "ALREADY_SENT":
        write_receipt(receipt, "OBSERVED", event_id, message_sha)
        return True, "ALREADY_SENT"
    if sent != "CLICKED":
        receipt.unlink(missing_ok=True)
        return False, sent

    check_js = (
        "(()=>{const marker=" + marker_json + ";"
        "const users=[...document.querySelectorAll('[data-message-author-role=\"user\"]')];"
        "if(users.slice(-100).some(x=>(x.innerText||'').includes(marker)))return 'OBSERVED';"
        "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
        "const draft=(e.innerText||'').trim();"
        "if(draft.includes(marker))return 'DRAFT_PRESENT';"
        "if(draft==='')return 'EDITOR_CLEARED';return 'DRAFT_CHANGED';})()"
    )
    for _ in range(20):
        time.sleep(0.5)
        check = run_js(target_url, check_js)
        if check == "OBSERVED":
            write_receipt(receipt, "OBSERVED", event_id, message_sha)
            return True, "OBSERVED_AFTER_CLICK"
        if check == "EDITOR_CLEARED":
            write_receipt(receipt, "SUBMITTED", event_id, message_sha)
            return True, "SUBMITTED_EDITOR_CLEARED"
        if check == "DRAFT_CHANGED":
            write_receipt(receipt, "SUBMITTED_UNCONFIRMED", event_id, message_sha)
            return True, "SUBMITTED_DRAFT_CHANGED"

    write_receipt(receipt, "SUBMITTED_UNCONFIRMED", event_id, message_sha)
    return True, "SUBMITTED_UNCONFIRMED_TIMEOUT"
def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main() -> int:
    for path in (QUEUE, RECEIPTS, BAD):
        path.mkdir(parents=True, exist_ok=True)

    if PIDFILE.exists():
        try:
            old_pid = int(PIDFILE.read_text().strip())
        except ValueError:
            old_pid = 0
        if old_pid and pid_alive(old_pid):
            print(f"RELAY_ALREADY_RUNNING:{old_pid}")
            return 0

    target_url = TARGET_FILE.read_text().splitlines()[0].strip()
    if not target_url.startswith("https://chatgpt.com/c/"):
        raise SystemExit("RELAY_TARGET_INVALID")
    secret = load_secret()
    PIDFILE.write_text(f"{os.getpid()}\n")
    log(f"relay=START pid={os.getpid()} target={target_url}")
    try:
        while True:
            now = time.time()
            HEARTBEAT.write_text(
                f"pid={os.getpid()} updated={now:.3f}\n"
            )
            try:
                target_url = TARGET_FILE.read_text().splitlines()[0].strip()
            except (FileNotFoundError, IndexError):
                target_url = ""
            if not target_url.startswith("https://chatgpt.com/c/"):
                log("relay=TARGET_INVALID")
                time.sleep(RETRY_SECONDS)
                continue
            STATUS.write_text(
                f"state=RUNNING\n"
                f"pid={os.getpid()}\n"
                f"heartbeat_epoch={int(now)}\n"
                f"target_url={target_url}\n"
            )
            if PAUSE.exists():
                time.sleep(RETRY_SECONDS)
                continue

            items = sorted(
                QUEUE.glob("*.wake"),
                key=lambda item: item.stat().st_mtime,
            )
            if not items:
                time.sleep(RETRY_SECONDS)
                continue

            path = items[0]
            try:
                event_id, message = validate_event(path, secret)
            except (OSError, UnicodeError, ValueError) as exc:
                target = BAD / f"{path.name}.bad.{int(time.time())}"
                shutil.move(path, target)
                log(f"event={path.name} status=BAD reason={type(exc).__name__}:{exc}")
                continue

            ok, status = deliver(event_id, message, target_url)
            log(f"event={sha(event_id)[:16]} status={status}")
            if ok:
                path.unlink(missing_ok=True)
            else:
                time.sleep(RETRY_SECONDS)
    finally:
        try:
            if PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        log(f"relay=STOP pid={os.getpid()}")


if __name__ == "__main__":
    raise SystemExit(main())
