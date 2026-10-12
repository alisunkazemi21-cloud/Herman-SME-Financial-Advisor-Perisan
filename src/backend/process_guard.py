"""Lifecycle containment for a cooperating local parser; not a security sandbox."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


class WindowsJob:
    """Children inherit a non-breakaway job; the parser waits for assignment."""

    def __init__(self) -> None:
        from ctypes import wintypes as w

        class BasicLimit(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", w.DWORD), ("min_working", ctypes.c_size_t),
                        ("max_working", ctypes.c_size_t), ("active_limit", w.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimit(ctypes.Structure):
            _fields_ = [("basic", BasicLimit), ("io", IoCounters), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                        ("peak_job", ctypes.c_size_t)]

        class Accounting(ctypes.Structure):
            _fields_ = [("user", ctypes.c_int64), ("kernel", ctypes.c_int64),
                        ("period_user", ctypes.c_int64), ("period_kernel", ctypes.c_int64),
                        ("faults", w.DWORD), ("total", w.DWORD), ("active", w.DWORD),
                        ("terminated", w.DWORD)]

        self.accounting = Accounting
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
            "QueryInformationJobObject":
                ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimit()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway flags.
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.api.CloseHandle(self.handle)
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, pid: int) -> None:
        process = self.api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(process)

    def close(self) -> None:
        try:
            if not self.api.TerminateJobObject(self.handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
            deadline = time.monotonic() + 5
            while True:
                info = self.accounting()
                if not self.api.QueryInformationJobObject(
                    self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if info.active == 0:
                    break
                if time.monotonic() >= deadline:
                    raise OSError("parser cleanup deadline")
                time.sleep(0.02)
        finally:
            self.api.CloseHandle(self.handle)


def _posix_group_has_live_members(group_id: int) -> bool:
    """Ignore exited Linux zombies, which may await reaping by another process."""
    if sys.platform.startswith("linux"):
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                if os.getpgid(int(entry.name)) != group_id:
                    continue
                fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            except (ProcessLookupError, FileNotFoundError):
                continue
            if fields[0] not in {"Z", "X", "x"}:
                return True
        return False
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    return True


def _stop_posix_group(process: subprocess.Popen) -> None:
    group_id = process.pid
    try:
        os.killpg(group_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)
    deadline = time.monotonic() + 5
    while _posix_group_has_live_members(group_id):
        if time.monotonic() >= deadline:
            raise OSError("parser cleanup deadline")
        time.sleep(0.02)


def run_contained(command: list[str], folder: Path, timeout: float) -> None:
    """The command must read one G byte from stdin before importing parsers."""
    if not 0 < timeout <= 60:
        raise ValueError("parser timeout must be within 60 seconds")
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "LANG"}}
    environment.update(TEMP=str(folder), TMP=str(folder), TMPDIR=str(folder),
                       PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1")
    job = WindowsJob() if os.name == "nt" else None
    process = None
    try:
        process = subprocess.Popen(
            command, cwd=folder, env=environment, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=os.name != "nt", close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if job:
            job.assign(process.pid)
        process.communicate(input=b"G", timeout=timeout)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
    finally:
        try:
            if job:
                job.close()
            elif process:
                _stop_posix_group(process)
        finally:
            if process:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                if process.stdin:
                    process.stdin.close()
