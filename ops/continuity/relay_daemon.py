#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from continuity_contracts import (
    PROJECT_NAMESPACE,
    RELAY_PROTOCOL,
    decode_relay_event,
    event_key,
    expected_wire_sha,
    marker_for,
    require_chat_url,
)

SHARED = Path("/Users/Shared/.crypto-signal-wake-relay")
QUEUE = SHARED / "queue"
RECEIPTS = SHARED / "receipts"
BAD = SHARED / "bad"
PAUSE = SHARED / "user_pause"
SECRET_FILE = SHARED / "relay_secret"
TARGET_FILE = SHARED / "current_chat_url"
EXPECTED_TARGET_FILE = SHARED / "expected_chat_url"
HEARTBEAT = SHARED / "relay_heartbeat"
PIDFILE = SHARED / "relay.pid"
LOG = SHARED / "relay.log"
STATUS = SHARED / "relay_status"
AUTONOMOUS_STATE = SHARED / "autonomous_wake_state"
AUTONOMOUS_PREFIX = "CRYPTO_SIGNAL_AUTONOMOUS_CONTINUE_V1"
AUTONOMOUS_TTL_SECONDS = 15 * 60
AUTONOMOUS_COOLDOWN_SECONDS = 10 * 60
LOCKED_WAKE_MESSAGE = "Kullanıcı aktif değil ve projeyi tamamlaman için sana bıraktı; HAFIZANA GÜVENME! READ_FIRST, CURRENT_STATUS, Chronicle ve docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md dosyasını oku; gerçek Git/worker/wake/lease state’ini kontrol et, gerçek frontier’ı bul. Tamamlanmış/stale/duplicate işi tekrarlama. Kullanıcı REAL MONEY hariç roadmap’in bitmesini istiyor; güvenli aşamalar arasında onay bekleme ve devam et. REAL_CAPITAL=0. Bir sonraki ajan için yaptığın her işi ve her güncellemeyi GitHub üzerine kaydet. Bu 20 dakikalık mesaj döngüsünü bozamazsın."
LOCKED_WAKE_INTERVAL_SECONDS = 20 * 60
LOCKED_PENDING_RETRY_SECONDS = 20
LOCKED_RECENT_DUPLICATE_SECONDS = 90
LOCKED_SUCCESS_STATE = SHARED / "locked_wake_success"
LOCKED_RESET_REQUEST = SHARED / "locked_wake_reset_requested"
PENDING = SHARED / "pending"
TERMINAL_RECEIPT_STATUSES = {
    "OBSERVED",
    "RECENT_LOCKED_DUPLICATE_DROPPED",
    "STALE_AUTONOMOUS_DROPPED",
    "SEMANTIC_DUPLICATE_DROPPED",
}
RETRY_SECONDS = 2
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
    return event_key(value)


def scheduled_slot_event_id() -> str:
    now = datetime.now().astimezone()
    slot_minute = (now.minute // 20) * 20
    slot = now.replace(minute=slot_minute, second=0, microsecond=0)
    return f"crypto-20m-continuity:{slot:%Y%m%dT%H%M%z}"


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


def receipt_status(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        if line.startswith("status="):
            return line.split("=", 1)[1]
    return ""


def read_locked_success_epoch() -> float | None:
    try:
        lines = LOCKED_SUCCESS_STATE.read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        if line.startswith("last_observed_epoch="):
            try:
                return float(line.split("=", 1)[1])
            except ValueError:
                return None
    return None


def record_locked_success(event_id: str, observed_epoch: float) -> None:
    tmp = LOCKED_SUCCESS_STATE.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(
        f"last_observed_epoch={observed_epoch:.3f}\n"
        f"event_id={event_id}\n"
        f"event_key={sha(event_id)}\n"
    )
    os.chmod(tmp, 0o660)
    tmp.replace(LOCKED_SUCCESS_STATE)


def read_reset_epoch() -> int | None:
    try:
        lines = LOCKED_RESET_REQUEST.read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        if line.startswith("reset_epoch="):
            try:
                return int(line.split("=", 1)[1])
            except ValueError:
                return None
    return None


def locked_recurring_event_id(last_observed_epoch: float | None) -> str:
    if last_observed_epoch is None:
        return "crypto-20m-locked-roadmap:bootstrap"
    return f"crypto-20m-locked-roadmap:after:{int(last_observed_epoch)}"


def write_pending(
    path: Path,
    *,
    event_id: str,
    message_sha: str,
    baseline_exact_count: int,
    clicked_epoch: float,
) -> None:
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(
        f"event_id={event_id}\n"
        f"message_sha256={message_sha}\n"
        f"baseline_exact_count={baseline_exact_count}\n"
        f"clicked_epoch={clicked_epoch:.3f}\n"
    )
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def read_pending(path: Path) -> tuple[str, str, int, float] | None:
    if not path.exists():
        return None
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    try:
        return (
            values["event_id"],
            values["message_sha256"],
            int(values["baseline_exact_count"]),
            float(values["clicked_epoch"]),
        )
    except (KeyError, ValueError):
        return None


def exact_message_count(target_url: str, message_json: str) -> tuple[int | None, str]:
    js = (
        "(()=>{const msg=" + message_json + ";"
        "const users=[...document.querySelectorAll('[data-message-author-role=\\\"user\\\"]')];"
        "return String(users.filter(x=>(x.innerText||'').trim()===msg).length);})()"
    )
    raw = run_js(target_url, js)
    try:
        return int(raw), raw
    except ValueError:
        return None, raw


def complete_locked_delivery(
    *,
    receipt: Path,
    pending: Path,
    event_id: str,
    message_sha: str,
) -> tuple[bool, str]:
    observed_epoch = time.time()
    record_locked_success(event_id, observed_epoch)
    write_receipt(receipt, "OBSERVED", event_id, message_sha)
    pending.unlink(missing_ok=True)
    return True, "OBSERVED"


def is_autonomous_wake(message: str) -> bool:
    return message.startswith(AUTONOMOUS_PREFIX)


def read_last_autonomous_delivery_epoch() -> float | None:
    try:
        lines = AUTONOMOUS_STATE.read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        if line.startswith("last_delivered_epoch="):
            try:
                return float(line.split("=", 1)[1])
            except ValueError:
                return None
    return None


def record_autonomous_delivery(event_id: str, delivered_epoch: float) -> None:
    tmp = AUTONOMOUS_STATE.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(
        f"last_delivered_epoch={delivered_epoch:.3f}\n"
        f"event_id={event_id}\n"
        f"event_key={sha(event_id)}\n"
    )
    os.chmod(tmp, 0o600)
    tmp.replace(AUTONOMOUS_STATE)


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


def load_secret() -> bytes:
    secret = SECRET_FILE.read_text().strip().encode()
    if len(secret) < 32:
        raise ValueError("relay secret is invalid")
    return secret


def validate_event(path: Path, secret: bytes) -> tuple[str, str]:
    event = decode_relay_event(path.read_text(), secret=secret)
    return event.event_id, event.message


def read_shared_binding() -> str:
    try:
        current = require_chat_url(TARGET_FILE.read_text().strip())
        expected = require_chat_url(EXPECTED_TARGET_FILE.read_text().strip())
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError("relay shared exact-chat binding is invalid") from exc
    if current != expected:
        raise ValueError("relay shared exact-chat binding mismatch")
    return current


def deliver(event_id: str, message: str, target_url: str) -> tuple[bool, str]:
    key = sha(event_id)
    exact_locked_wake = message == LOCKED_WAKE_MESSAGE
    marker = marker_for(event_id)
    wire_message = message if exact_locked_wake else f"{message} {marker}"
    message_sha = sha(wire_message)
    receipt = RECEIPTS / f"{key}.state"
    pending = PENDING / f"{key}.pending"

    bound_sha = receipt_sha(receipt)
    status = receipt_status(receipt)
    if bound_sha is not None:
        if bound_sha and bound_sha != message_sha:
            return False, "EVENT_ID_MESSAGE_CONFLICT"
        if status in TERMINAL_RECEIPT_STATUSES:
            return True, f"ALREADY_RECEIPTED:{status}"

    if message.startswith(AUTONOMOUS_PREFIX):
        canonical_event_id = scheduled_slot_event_id()
        if event_id != canonical_event_id:
            write_receipt(
                receipt,
                "STALE_AUTONOMOUS_DROPPED",
                event_id,
                message_sha,
            )
            return True, f"STALE_AUTONOMOUS_DROPPED:{canonical_event_id}"

    marker_json = json.dumps(marker)
    message_json = json.dumps(wire_message)

    baseline_exact_count = 0
    if exact_locked_wake:
        last_success = read_locked_success_epoch()
        reset_event = event_id.startswith("crypto-20m-locked-roadmap:reset:")
        if (
            not reset_event
            and last_success is not None
            and time.time() - last_success < LOCKED_RECENT_DUPLICATE_SECONDS
        ):
            write_receipt(
                receipt,
                "RECENT_LOCKED_DUPLICATE_DROPPED",
                event_id,
                message_sha,
            )
            pending.unlink(missing_ok=True)
            return True, "RECENT_LOCKED_DUPLICATE_DROPPED"

        pending_state = read_pending(pending)
        if pending_state is not None:
            pending_event_id, pending_sha, baseline_exact_count, clicked_epoch = pending_state
            if pending_event_id != event_id or pending_sha != message_sha:
                return False, "LOCKED_PENDING_CONFLICT"
            current_count, raw_count = exact_message_count(target_url, message_json)
            if current_count is not None and current_count > baseline_exact_count:
                return complete_locked_delivery(
                    receipt=receipt,
                    pending=pending,
                    event_id=event_id,
                    message_sha=message_sha,
                )
            age = time.time() - clicked_epoch
            if age < LOCKED_PENDING_RETRY_SECONDS:
                return False, f"LOCKED_PENDING_OBSERVATION:{int(age)}"
            pending.unlink(missing_ok=True)
            log(
                f"event={key[:16]} status=LOCKED_RETRY_UNOBSERVED "
                f"pending_age_seconds={int(age)} count_state={raw_count}"
            )

        current_count, raw_count = exact_message_count(target_url, message_json)
        if current_count is None:
            if raw_count == "TARGET_NOT_FOUND":
                return False, open_target_in_browser(target_url)
            return False, f"LOCKED_COUNT_UNAVAILABLE:{raw_count}"
        baseline_exact_count = current_count

        state_js = (
            "(()=>{const msg=" + message_json + ";"
            "const stop=[...document.querySelectorAll('button[data-testid=\\\"stop-button\\\"]')]"
            ".find(x=>{const s=getComputedStyle(x),r=x.getBoundingClientRect();"
            "return x.isConnected&&!x.disabled&&s.display!=='none'&&s.visibility!=='hidden'"
            "&&Number(s.opacity||1)>0&&r.width>1&&r.height>1&&x.getClientRects().length>0;});"
            "if(stop)return 'CHATGPT_BUSY';"
            "const e=document.querySelector('#prompt-textarea');"
            "if(!e)return 'NO_EDITOR';"
            "const draft=(e.innerText||'').trim();"
            "if(draft===msg)return 'PREPARED';"
            "if(draft)return 'DRAFT_BUSY';return 'READY';})()"
        )
    else:
        state_js = (
            "(()=>{const marker=" + marker_json + ";"
            "const users=[...document.querySelectorAll('[data-message-author-role=\\\"user\\\"]')];"
            "if(users.slice(-100).some(x=>(x.innerText||'').includes(marker)))return 'OBSERVED';"
            "const stop=[...document.querySelectorAll('button[data-testid=\\\"stop-button\\\"]')]"
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
        if not exact_locked_wake:
            return False, "CHATGPT_BUSY"
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
            "(()=>{const msg=" + message_json + ";"
            "const stop=[...document.querySelectorAll('button[data-testid=\\\"stop-button\\\"]')]"
            ".find(x=>{const s=getComputedStyle(x),r=x.getBoundingClientRect();"
            "return x.isConnected&&!x.disabled&&s.display!=='none'&&s.visibility!=='hidden'"
            "&&Number(s.opacity||1)>0&&r.width>1&&r.height>1&&x.getClientRects().length>0;});"
            "if(stop)return 'STILL_BUSY';"
            "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
            "const draft=(e.innerText||'').trim();"
            "if(draft===msg)return 'PREPARED';"
            "if(draft)return 'DRAFT_BUSY';return 'READY';})()"
        )
        for _ in range(60):
            time.sleep(0.25)
            state = run_js(target_url, ready_js)
            if state in {"READY", "PREPARED", "DRAFT_BUSY"}:
                break
        if state not in {"READY", "PREPARED"}:
            return False, f"AFTER_STOP:{state}"

    if state in {"DRAFT_BUSY", "NO_EDITOR"}:
        return False, state
    if state.startswith(
        (
            "OSASCRIPT_TIMEOUT",
            "OSASCRIPT_ERROR:",
            "CHROME_JAVASCRIPT_ERROR:",
            "CHROME_AUTOMATION_ERROR:",
            "SAFARI_JAVASCRIPT_ERROR:",
            "SAFARI_AUTOMATION_ERROR:",
        )
    ):
        return False, state

    if state == "READY":
        if exact_locked_wake:
            fill_js = (
                "(()=>{const msg=" + message_json + ";"
                "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
                "const cur=(e.innerText||'').trim();if(cur===msg)return 'FILLED';"
                "if(cur)return 'DRAFT_BUSY';e.focus();"
                "const ok=document.execCommand('insertText',false,msg);"
                "return ok&&((e.innerText||'').trim()===msg)?'FILLED':'FILL_FAILED';})()"
            )
        else:
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

    if exact_locked_wake:
        write_pending(
            pending,
            event_id=event_id,
            message_sha=message_sha,
            baseline_exact_count=baseline_exact_count,
            clicked_epoch=time.time(),
        )

    if exact_locked_wake:
        send_js = (
            "(()=>{const msg=" + message_json + ";"
            "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
            "const draft=(e.innerText||'').trim();if(draft!==msg)return 'DRAFT_CHANGED';"
            "const b=document.querySelector('button[data-testid=\\\"send-button\\\"]');"
            "if(!b||b.disabled)return 'NO_SEND';b.click();return 'CLICKED';})()"
        )
    else:
        send_js = (
            "(()=>{const marker=" + marker_json + ";"
            "const users=[...document.querySelectorAll('[data-message-author-role=\\\"user\\\"]')];"
            "if(users.slice(-100).some(x=>(x.innerText||'').includes(marker)))return 'ALREADY_SENT';"
            "const e=document.querySelector('#prompt-textarea');if(!e)return 'NO_EDITOR';"
            "const draft=(e.innerText||'').trim();if(!draft.includes(marker))return 'DRAFT_CHANGED';"
            "const b=document.querySelector('button[data-testid=\\\"send-button\\\"]');"
            "if(!b||b.disabled)return 'NO_SEND';b.click();return 'CLICKED';})()"
        )

    sent = run_js(target_url, send_js)
    if sent == "ALREADY_SENT":
        write_receipt(receipt, "OBSERVED", event_id, message_sha)
        return True, "ALREADY_SENT"
    if sent != "CLICKED":
        if exact_locked_wake:
            pending.unlink(missing_ok=True)
        return False, sent

    if exact_locked_wake:
        check_js = (
            "(()=>{const msg=" + message_json + ";"
            "const users=[...document.querySelectorAll('[data-message-author-role=\\\"user\\\"]')];"
            "const count=users.filter(x=>(x.innerText||'').trim()===msg).length;"
            "return count>" + str(baseline_exact_count) + "?'OBSERVED':'WAITING';})()"
        )
    else:
        check_js = (
            "(()=>{const marker=" + marker_json + ";"
            "const users=[...document.querySelectorAll('[data-message-author-role=\\\"user\\\"]')];"
            "return users.slice(-100).some(x=>(x.innerText||'').includes(marker))"
            "?'OBSERVED':'WAITING';})()"
        )

    for _ in range(40):
        time.sleep(0.5)
        check = run_js(target_url, check_js)
        if check == "OBSERVED":
            if exact_locked_wake:
                return complete_locked_delivery(
                    receipt=receipt,
                    pending=pending,
                    event_id=event_id,
                    message_sha=message_sha,
                )
            write_receipt(receipt, "OBSERVED", event_id, message_sha)
            return True, "OBSERVED_AFTER_CLICK"

    return False, (
        "LOCKED_SUBMIT_UNCONFIRMED"
        if exact_locked_wake
        else "SUBMIT_UNCONFIRMED"
    )



def maybe_deliver_locked_wake(target_url: str) -> None:
    reset_epoch = read_reset_epoch()
    last_success = read_locked_success_epoch()
    now = time.time()

    if reset_epoch is not None:
        event_id = f"crypto-20m-locked-roadmap:reset:{reset_epoch}"
    else:
        if (
            last_success is not None
            and now - last_success < LOCKED_WAKE_INTERVAL_SECONDS
        ):
            return
        event_id = locked_recurring_event_id(last_success)

    ok, status = deliver(event_id, LOCKED_WAKE_MESSAGE, target_url)
    log(
        f"locked_scheduler_event={sha(event_id)[:16]} "
        f"status={status} reset={'YES' if reset_epoch is not None else 'NO'}"
    )
    if ok and reset_epoch is not None:
        LOCKED_RESET_REQUEST.unlink(missing_ok=True)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main() -> int:
    for path in (QUEUE, RECEIPTS, BAD, PENDING):
        path.mkdir(parents=True, exist_ok=True)

    if PIDFILE.exists():
        try:
            old_pid = int(PIDFILE.read_text().strip())
        except ValueError:
            old_pid = 0
        if old_pid and pid_alive(old_pid):
            print(f"RELAY_ALREADY_RUNNING:{old_pid}")
            return 0

    try:
        target_url = read_shared_binding()
    except ValueError as exc:
        raise SystemExit(f"RELAY_TARGET_ISOLATION_VIOLATION:{exc}") from exc
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
                target_url = read_shared_binding()
            except ValueError as exc:
                log(f"relay=TARGET_ISOLATION_VIOLATION reason={exc}")
                time.sleep(RETRY_SECONDS)
                continue

            last_success = read_locked_success_epoch()
            next_due = (
                0
                if last_success is None
                else int(last_success + LOCKED_WAKE_INTERVAL_SECONDS)
            )
            STATUS.write_text(
                f"state=RUNNING\n"
                f"relay_protocol={RELAY_PROTOCOL}\n"
                f"project_namespace={PROJECT_NAMESPACE}\n"
                f"pid={os.getpid()}\n"
                f"heartbeat_epoch={int(now)}\n"
                f"target_url={target_url}\n"
                f"locked_last_observed_epoch={'' if last_success is None else int(last_success)}\n"
                f"locked_next_due_epoch={next_due}\n"
                f"locked_reset_pending={'YES' if LOCKED_RESET_REQUEST.exists() else 'NO'}\n"
            )
            if PAUSE.exists():
                time.sleep(RETRY_SECONDS)
                continue

            # Primary scheduler: this relay is already watchdog-supervised and owns
            # the browser transport. It resets cadence only after exact DOM observation.
            maybe_deliver_locked_wake(target_url)

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

            autonomous = is_autonomous_wake(message)
            if autonomous:
                queue_age = max(0.0, now - path.stat().st_mtime)
                if queue_age > AUTONOMOUS_TTL_SECONDS:
                    message_sha = expected_wire_sha(event_id, message)
                    write_receipt(
                        RECEIPTS / f"{sha(event_id)}.state",
                        "STALE_AUTONOMOUS_DROPPED",
                        event_id,
                        message_sha,
                    )
                    path.unlink(missing_ok=True)
                    log(
                        f"event={sha(event_id)[:16]} "
                        f"status=STALE_AUTONOMOUS_DROPPED "
                        f"age_seconds={int(queue_age)}"
                    )
                    continue

                last_delivery = read_last_autonomous_delivery_epoch()
                if (
                    last_delivery is not None
                    and now - last_delivery < AUTONOMOUS_COOLDOWN_SECONDS
                ):
                    message_sha = expected_wire_sha(event_id, message)
                    write_receipt(
                        RECEIPTS / f"{sha(event_id)}.state",
                        "SEMANTIC_DUPLICATE_DROPPED",
                        event_id,
                        message_sha,
                    )
                    path.unlink(missing_ok=True)
                    log(
                        f"event={sha(event_id)[:16]} "
                        "status=SEMANTIC_DUPLICATE_DROPPED "
                        f"cooldown_age_seconds={int(now - last_delivery)}"
                    )
                    continue

            ok, status = deliver(event_id, message, target_url)
            log(f"event={sha(event_id)[:16]} status={status}")
            if ok:
                if autonomous and not status.startswith("ALREADY_RECEIPTED"):
                    record_autonomous_delivery(event_id, time.time())
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
