"""Named-pipe client for the native Windows Phone Unlock Service (PhoneUnlockService.exe)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import struct
import subprocess
import time

DEFAULT_CONTROL_PIPE = r"\\.\pipe\PCPhoneRemoteUnlockControl"

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
SECURITY_SQOS_PRESENT = 0x00100000
SECURITY_IDENTIFICATION = 0x00010000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_PIPE_BUSY = 231
ERROR_FILE_NOT_FOUND = 2

_SERVICE_PROCESS: subprocess.Popen | None = None


def _service_exe_candidates() -> list[Path]:
    repo_root = Path(__file__).resolve().parent.parent
    prog_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    return [
        prog_files / "PCPhoneRemote" / "unlock" / "PhoneUnlockService.exe",
        repo_root / "windows-unlock" / "build" / "PhoneUnlockService.exe",
    ]


def ensure_local_service_running(pipe_name: str = DEFAULT_CONTROL_PIPE) -> bool:
    """Ensures PhoneUnlockService.exe is reachable on the control pipe, starting console mode if built locally."""
    global _SERVICE_PROCESS
    if os.name != "nt":
        return False
    if _pipe_exists(pipe_name):
        return True
    if pipe_name != DEFAULT_CONTROL_PIPE:
        return False
    for exe in _service_exe_candidates():
        if exe.exists():
            try:
                _SERVICE_PROCESS = subprocess.Popen(
                    [str(exe), "--console", "--allow-test-peer"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for _ in range(25):
                    if _pipe_exists(pipe_name):
                        return True
                    time.sleep(0.05)
            except OSError:
                pass
    return _pipe_exists(pipe_name)


def _pipe_exists(pipe_name: str) -> bool:
    if os.name != "nt":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel32.WaitNamedPipeW.restype = wintypes.BOOL
    if kernel32.WaitNamedPipeW(pipe_name, 50):
        return True
    return ctypes.get_last_error() == ERROR_PIPE_BUSY


def pipe_transact(payload: dict, pipe_name: str = DEFAULT_CONTROL_PIPE, timeout_ms: int = 14000, auto_start: bool = True) -> dict:
    """Sends a length-prefixed JSON request to PhoneUnlockService.exe and returns the parsed JSON response."""
    if os.name != "nt":
        return {"ok": False, "error": "windows_only", "message": "Windows unlock service requires Windows", "status": 501}

    if auto_start:
        ensure_local_service_running(pipe_name)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel32.WaitNamedPipeW.restype = wintypes.BOOL

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    handle = INVALID_HANDLE_VALUE
    not_found_retries = 0
    while time.monotonic() < deadline:
        handle = kernel32.CreateFileW(
            pipe_name,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION,
            None,
        )
        if handle != INVALID_HANDLE_VALUE and handle is not None:
            break
        err = ctypes.get_last_error()
        if err == ERROR_PIPE_BUSY:
            kernel32.WaitNamedPipeW(pipe_name, 50)
        elif err == ERROR_FILE_NOT_FOUND and not_found_retries < 8:
            not_found_retries += 1
            time.sleep(0.02)
        else:
            return {
                "ok": False,
                "error": "service_unavailable",
                "message": "Служба входа PC Remote не запущена на ПК",
                "status": 503,
            }

    if handle == INVALID_HANDLE_VALUE or handle is None:
        return {
            "ok": False,
            "error": "service_unavailable",
            "message": "Не удалось подключиться к службе входа на ПК",
            "status": 503,
        }

    try:
        raw_req = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        frame = struct.pack("<I", len(raw_req)) + raw_req
        written = wintypes.DWORD(0)
        if not kernel32.WriteFile(handle, frame, len(frame), ctypes.byref(written), None) or written.value != len(frame):
            return {"ok": False, "error": "pipe_write_failed", "message": "Failed to send request to unlock service", "status": 502}

        hdr = ctypes.create_string_buffer(4)
        read_bytes = wintypes.DWORD(0)
        if not kernel32.ReadFile(handle, hdr, 4, ctypes.byref(read_bytes), None) or read_bytes.value != 4:
            return {"ok": False, "error": "pipe_read_failed", "message": "No response from unlock service", "status": 502}

        (resp_len,) = struct.unpack("<I", hdr.raw)
        if resp_len <= 0 or resp_len > 65536:
            return {"ok": False, "error": "pipe_bad_length", "message": "Invalid response size from unlock service", "status": 502}

        chunks = bytearray()
        while len(chunks) < resp_len:
            need = resp_len - len(chunks)
            buf = ctypes.create_string_buffer(need)
            got = wintypes.DWORD(0)
            if not kernel32.ReadFile(handle, buf, need, ctypes.byref(got), None) or got.value == 0:
                return {"ok": False, "error": "pipe_eof", "message": "Incomplete response from unlock service", "status": 502}
            chunks.extend(buf.raw[: got.value])

        return json.loads(chunks.decode("utf-8"))
    except Exception:
        return {"ok": False, "error": "pipe_exception", "message": "Unlock service communication error", "status": 500}
    finally:
        kernel32.CloseHandle(handle)
