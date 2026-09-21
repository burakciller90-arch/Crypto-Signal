#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from continuity_contracts import require_exact_binding

BASE = Path("/Volumes/Crypto-504/Crypto-Signal/Development")
STATE = BASE / "runtime" / "continuity"
WAKE = STATE / "wake"
TARGET_FILE = WAKE / "current_chat_url"
EXPECTED_FILE = WAKE / "expected_chat_url"
RECEIPTS = WAKE / "receipts"
PAUSE_FILE = STATE / "user_pause"
SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
SHARED_PAUSE_FILE = SHARED / "user_pause"
SHARED_TARGET_FILE = SHARED / "current_chat_url"
SHARED_EXPECTED_FILE = SHARED / "expected_chat_url"
LOG = WAKE / "transport.log"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def log(event: str, key: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
    with LOG.open("a") as handle:
        handle.write(f"{stamp} event={key} status={event}\n")
def write_receipt(path: Path, status: str, event_id: str, key: str, message_sha: str) -> None:
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %z")
    tmp.write_text(
        f"status={status}\n"
        f"event_id={event_id}\n"
        f"event_key={key}\n"
        f"message_sha256={message_sha}\n"
        f"updated={stamp}\n"
    )
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def receipt_message_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith("message_sha256="):
            return line.split("=", 1)[1]
    return ""


APPLESCRIPT = r"""
on run argv
  set targetUrl to item 1 of argv
  set js to item 2 of argv
  tell application "Safari"
    repeat with w in windows
      repeat with t in tabs of w
        try
          if (URL of t as text) is targetUrl then
            try
              return do JavaScript js in t
            on error errMsg number errNum
              return "JAVASCRIPT_ERROR:" & errNum & ":" & errMsg
            end try
          end if
        end try
      end repeat
    end repeat
  end tell
  return "TARGET_NOT_FOUND"
end run
"""


def run_js(target_url: str, js: str) -> str:
    proc = subprocess.run(
        ["/usr/bin/osascript", "-", target_url, js],
        input=APPLESCRIPT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return f"OSASCRIPT_ERROR:{proc.returncode}:{proc.stderr.strip()}"
    return proc.stdout.strip()
def main() -> int:
    if PAUSE_FILE.exists() or SHARED_PAUSE_FILE.exists():
        print(
            "WAKE_TRANSPORT_PAUSED "
            f"local={PAUSE_FILE} shared={SHARED_PAUSE_FILE}"
        )
        return 0
    if len(sys.argv) != 3:
        print("USAGE: wake_chatgpt.py event_id message", file=sys.stderr)
        return 64

    event_id, message = sys.argv[1], sys.argv[2]
    def read(path: Path) -> str:
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            return ""

    try:
        target_url = require_exact_binding(
            expected=read(EXPECTED_FILE),
            local_current=read(TARGET_FILE),
            shared_current=read(SHARED_TARGET_FILE),
            shared_expected=read(SHARED_EXPECTED_FILE),
        )
    except ValueError as exc:
        print(f"TARGET_URL_BINDING_INVALID:{exc}")
        return 2

    RECEIPTS.mkdir(parents=True, exist_ok=True)
    key = sha(event_id)
    short = key[:16]
    marker = f"[#cryptowake:{short}]"
    wire_message = f"{message} {marker}"
    message_sha = sha(wire_message)
    receipt = RECEIPTS / f"{key}.state"
    bound_sha = receipt_message_sha(receipt)
    if bound_sha is not None:
        if bound_sha and bound_sha != message_sha:
            log("EVENT_ID_MESSAGE_CONFLICT", short)
            print("EVENT_ID_MESSAGE_CONFLICT")
            return 65
        log("ALREADY_RECEIPTED", short)
        print("ALREADY_SENT")
        return 0
    msg_json = json.dumps(wire_message)
    marker_json = json.dumps(marker)
    state_js = (
        "(()=>{const marker=" + marker_json + ";"
        "const users=[...document.querySelectorAll('[data-message-author-role=\"user\"]')];"
        "if(users.slice(-80).some(x=>(x.innerText||'').includes(marker)))return 'OBSERVED';"
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
    if state == "OBSERVED":
        write_receipt(receipt, "OBSERVED", event_id, key, message_sha)
        log("OBSERVED", short)
        print("ALREADY_SENT")
        return 0
    if state in {"CHATGPT_BUSY", "NO_EDITOR", "DRAFT_BUSY", "TARGET_NOT_FOUND"}:
        log(state, short)
        print(state)
        return 2
    if state.startswith(("OSASCRIPT_ERROR:", "JAVASCRIPT_ERROR:")):
        log(state, short)
        print(state)
        return 2
    if state == "READY":
        fill_js = (
            "(()=>{const msg=" + msg_json + ";const marker=" + marker_json + ";"
            "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
            "const cur=(e.innerText||'').trim();if(cur.includes(marker))return 'FILLED';"
            "if(cur)return 'DRAFT_BUSY';e.focus();"
            "const ok=document.execCommand('insertText',false,msg);"
            "return ok&&((e.innerText||'').includes(marker))?'FILLED':'FILL_FAILED';})()"
        )
        filled = run_js(target_url, fill_js)
        if filled != "FILLED":
            log(filled, short)
            print(filled)
            return 3

    write_receipt(receipt, "SUBMITTING", event_id, key, message_sha)
    send_js = (
        "(()=>{const marker=" + marker_json + ";"
        "const users=[...document.querySelectorAll('[data-message-author-role=\"user\"]')];"
        "if(users.slice(-80).some(x=>(x.innerText||'').includes(marker)))return 'ALREADY_SENT';"
        "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
        "const draft=(e.innerText||'').trim();if(!draft.includes(marker))return 'DRAFT_CHANGED';"
        "const b=document.querySelector('button[data-testid=\"send-button\"]');"
        "if(!b||b.disabled)return 'NO_SEND';b.click();return 'CLICKED';})()"
    )
    sent = run_js(target_url, send_js)
    if sent == "ALREADY_SENT":
        write_receipt(receipt, "OBSERVED", event_id, key, message_sha)
        log("OBSERVED_AFTER_PREPARE", short)
        print("ALREADY_SENT")
        return 0
    if sent != "CLICKED":
        receipt.unlink(missing_ok=True)
        log(sent, short)
        print(sent)
        return 3

    check_js = (
        "(()=>{const marker=" + marker_json + ";"
        "const users=[...document.querySelectorAll('[data-message-author-role=\"user\"]')];"
        "if(users.slice(-80).some(x=>(x.innerText||'').includes(marker)))return 'OBSERVED';"
        "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
        "const draft=(e.innerText||'').trim();"
        "if(draft.includes(marker))return 'DRAFT_PRESENT';"
        "if(draft==='')return 'EDITOR_CLEARED';return 'DRAFT_CHANGED';})()"
    )
    for _ in range(20):
        time.sleep(0.5)
        check = run_js(target_url, check_js)
        if check == "OBSERVED":
            write_receipt(receipt, "OBSERVED", event_id, key, message_sha)
            log("OBSERVED_AFTER_CLICK", short)
            print("SENT")
            return 0
        if check == "EDITOR_CLEARED":
            write_receipt(receipt, "SUBMITTED", event_id, key, message_sha)
            log("SUBMITTED_EDITOR_CLEARED", short)
            print("SUBMITTED")
            return 0
        if check == "DRAFT_CHANGED":
            write_receipt(receipt, "SUBMITTED_UNCONFIRMED", event_id, key, message_sha)
            log("SUBMITTED_DRAFT_CHANGED", short)
            print("SUBMITTED_UNCONFIRMED")
            return 0

    write_receipt(receipt, "SUBMITTED_UNCONFIRMED", event_id, key, message_sha)
    log("SUBMITTED_UNCONFIRMED_TIMEOUT", short)
    print("SUBMITTED_UNCONFIRMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
