"""Isolated terminal fixture: require two Ctrl+C bytes within 800 ms to exit."""
import os
import sys
import termios
import time
import tty


fd = sys.stdin.fileno()
saved = termios.tcgetattr(fd)
try:
    tty.setraw(fd)
    os.write(sys.stdout.fileno(), b"EXIT_FIXTURE_READY\r\n")
    armed_at = None
    while True:
        key = os.read(fd, 1)
        if not key:
            break
        if key != b"\x03":
            continue
        now = time.monotonic()
        if armed_at is not None and now - armed_at < 0.8:
            os.write(sys.stdout.fileno(), b"EXIT_FIXTURE_CONFIRMED\r\n")
            # A real CLI may need time to flush its transcript after confirmation.
            time.sleep(0.5)
            break
        armed_at = now
        os.write(sys.stdout.fileno(), b"Press Ctrl+C again to exit\r\n")
finally:
    termios.tcsetattr(fd, termios.TCSANOW, saved)
