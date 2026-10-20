"""Single-instance scheduler lease.

The project ships with an in-process APScheduler and startup recovery that scans
the whole database. Two live backend instances would therefore race to mark each
other's tasks interrupted. This lease makes the boundary explicit: the first
process that acquires the lock runs recovery, scheduling and dispatch; a second
process starts in API-only/standby mode and logs the reason.

The lock is an OS file lock, released automatically when the process exits. It
covers deployments on one host (including a container restart). A future
multi-host deployment needs a database lease plus owner/heartbeat fencing.
"""

from __future__ import annotations

import os
from pathlib import Path


class SchedulerLease:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = open(self.path, "a+b")
        try:
            file.seek(0, os.SEEK_END)
            if file.tell() == 0:
                file.write(b"\0")
                file.flush()
            file.seek(0)
            if not _lock(file):
                file.close()
                return False
        except OSError:
            file.close()
            return False
        self._file = file
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            _unlock(self._file)
        finally:
            self._file.close()
            self._file = None


if os.name == "nt":
    import msvcrt

    def _lock(file) -> bool:  # type: ignore[no-untyped-def]
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(file) -> None:  # type: ignore[no-untyped-def]
        try:
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

else:
    import fcntl

    def _lock(file) -> bool:  # type: ignore[no-untyped-def]
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(file) -> None:  # type: ignore[no-untyped-def]
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
