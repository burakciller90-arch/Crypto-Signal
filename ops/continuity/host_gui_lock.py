#!/usr/bin/env python3
import fcntl
import os
import subprocess
import sys

LOCK = "/Users/Shared/.crypto-signal-chatgpt-gui.lockfile"

if len(sys.argv) < 2:
    print("USAGE: host_gui_lock.py command [args...]", file=sys.stderr)
    raise SystemExit(64)

fd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o666)
try:
    if os.stat(LOCK).st_uid == os.getuid():
        os.chmod(LOCK, 0o666)
except OSError:
    pass

try:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("HOST_GUI_BUSY")
        raise SystemExit(2)
    raise SystemExit(subprocess.run(sys.argv[1:], check=False).returncode)
finally:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
