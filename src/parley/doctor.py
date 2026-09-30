"""`parley setup` / `parley doctor`: make WhatsApp Desktop debuggable locally.

The WhatsApp Desktop app we drive renders WhatsApp Web inside WebView2. To
reach it over CDP the app must start with the WebView2 debugging channel open.
There are two ways to say so that work on real builds:

* **User env var (no admin, recommended).** Set
  ``WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<port>`` for
  the whole user session via ``setx``, then relaunch WhatsApp Desktop (the
  profile and login survive). This is what made Live WhatsApp respond here.
* **Machine policy (admin).** Set ``HKLM\\...\\WebView2\\AdditionalBrowserArguments``
  to the same flag. Applies to every WebView2 app on the machine.

The legacy ``HKCU`` policy key is **ignored on current WhatsApp Desktop builds**
(they read the HKLM policy + the env var), so ``parley setup`` no longer
writes it. ``doctor`` reads env var + both registry hives and reports plainly.
"""

from __future__ import annotations

import os
import subprocess
import sys

from .backends.webview import DEFAULT_PORT, port_open

WEBVIEW2_POLICY_KEY_HKLM = r"Software\Policies\Microsoft\Edge\WebView2"
WEBVIEW2_POLICY_KEY_HKCU = r"Software\Policies\Microsoft\Edge\WebView2"
WEBVIEW2_ARG_NAME = "AdditionalBrowserArguments"
WEBVIEW2_ENV_VAR = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"
APP_ID = "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"

_LOGIN_RESTART_HINT = (
    "Restart WhatsApp Desktop (fully quit it, then reopen it) so WebView2 "
    "boots with the debugging port open. Your login survives — the profile is "
    "untouched.\n    explorer.exe shell:AppsFolder\\"
    + APP_ID
)


class SetupError(RuntimeError):
    pass


def _is_windows() -> bool:
    return sys.platform == "win32"


def _winreg():
    if not _is_windows():
        raise SetupError("parley setup currently manages the Windows WebView2 policy registry key")
    import winreg  # noqa: PLC0415

    return winreg


def whatsapp_processes() -> list[str]:
    if not _is_windows():
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process | Where-Object { $_.ProcessName -like '*WhatsApp*' } "
             "| Select-Object -ExpandProperty ProcessName -Unique)"],
            capture_output=True, text=True, timeout=15,
        )
        return [p.strip() for p in out.stdout.splitlines() if p.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def find_debug_flag() -> str | None:
    """Return the current debugging flag string, if one is active anywhere.

    Reads (highest precedence first): the machine-wide HKLM policy key, the
    user-scope env var, then the legacy HKCU policy key (still read and
    reported, though current WhatsApp Desktop builds ignore it).
    """
    if _is_windows():
        winreg = _winreg()
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, WEBVIEW2_POLICY_KEY_HKLM, 0, winreg.KEY_READ) as key:
                    value, _ = winreg.QueryValueEx(key, WEBVIEW2_ARG_NAME)
                    if value:
                        return value
            except OSError:
                continue
    return os.environ.get(WEBVIEW2_ENV_VAR)


def _user_env_value(name: str) -> str | None:
    """Read a var from the *persisted* user environment (works in a fresh shell)."""
    if not _is_windows():
        return os.environ.get(name)
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"[Environment]::GetEnvironmentVariable('{name}','User')"],
            capture_output=True, text=True, timeout=15,
        )
        return (out.stdout or "").strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _broadcast_environment() -> None:
    """Tell Explorer (and apps that listen) the environment changed."""
    try:
        import ctypes  # noqa: PLC0415
        import ctypes.wintypes  # noqa: PLC0415

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        dll = ctypes.windll.user32  # type: ignore[attr-defined]
        dll.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, 0, 2, 5000, ctypes.byref(ctypes.wintypes.DWORD())
        )
    except Exception:
        pass


def set_user_env(name: str, value: str) -> None:
    """Persist a user-scope env var and tell Explorer to notice it."""
    subprocess.run(["setx", name, value], capture_output=True, text=True, timeout=20, check=True)


def unset_user_env(name: str) -> None:
    """Delete a persisted user-scope env var."""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"[Environment]::SetEnvironmentVariable('{name}', $null, 'User')"],
        capture_output=True, text=True, timeout=20, check=True,
    )


def setup(port: int = DEFAULT_PORT, force: bool = False, dry_run: bool = False, admin: bool = False) -> dict:
    """Enable the WebView2 debugging port.

    Default (no admin): set the user env var ``WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS``
    and print a restart hint. ``admin=True``: write the machine-wide HKLM
    policy key instead (needs an admin shell).
    """
    arg = f"--remote-debugging-port={port}"
    current = find_debug_flag() or _user_env_value(WEBVIEW2_ENV_VAR)
    if current and not force and str(port) in (current.split() or []):
        return {"ok": True, "already": True, "arg": current, "hint": None}

    if dry_run:
        method = "env var (user)" if not admin else "registry policy (HKLM)"
        return {"ok": True, "dry_run": True, "would_write": arg, "method": method}

    if admin:
        if not _is_windows():
            raise SetupError("registry setup is Windows-only; use the env var elsewhere")
        winreg = _winreg()
        try:
            with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, WEBVIEW2_POLICY_KEY_HKLM) as key:
                winreg.SetValueEx(key, WEBVIEW2_ARG_NAME, 0, winreg.REG_SZ, arg)
        except OSError as exc:
            raise SetupError(
                f"could not write HKLM\\{WEBVIEW2_POLICY_KEY_HKLM} ({exc}); "
                "this needs an admin shell, or just drop --admin"
            ) from exc
        verified = str(port) in (find_debug_flag() or "")
        method = "registry policy (HKLM)"
    elif _is_windows():
        set_user_env(WEBVIEW2_ENV_VAR, arg)
        _broadcast_environment()
        persisted = _user_env_value(WEBVIEW2_ENV_VAR)
        verified = persisted is not None and str(port) in persisted
        method = "user env var"
    else:
        raise SetupError(
            "on macOS/Linux set the env var yourself, or use a Chromium browser started "
            "with the flag (see `parley doctor`)"
        )

    return {
        "ok": verified,
        "already": False,
        "arg": arg,
        "method": method,
        "verified": verified,
        "hint": _LOGIN_RESTART_HINT,
    }


def undo_setup() -> dict:
    """Remove what `parley setup` writes: the HKLM/HKCU policy keys + user env var."""
    removed: list[str] = []
    if _is_windows():
        winreg = _winreg()
        for hive_name, hive in (("HKLM", winreg.HKEY_LOCAL_MACHINE), ("HKCU", winreg.HKEY_CURRENT_USER)):
            try:
                winreg.DeleteKey(hive, WEBVIEW2_POLICY_KEY_HKLM)
                removed.append(hive_name)
            except OSError:
                pass
    env = _user_env_value(WEBVIEW2_ENV_VAR)
    if env:
        try:
            unset_user_env(WEBVIEW2_ENV_VAR)
            removed.append("user env var")
        except subprocess.SubprocessError:
            removed.append("user env var (manual)")
    return {"ok": True, "removed": removed}


def doctor(port: int = DEFAULT_PORT) -> dict:
    """A read-only report on what parley needs to attach to the real app."""
    checks = []
    platform = sys.platform

    if platform == "win32":
        processes = whatsapp_processes()
        checks.append(
            {
                "name": "WhatsApp Desktop process",
                "ok": bool(processes),
                "detail": ", ".join(processes) or "not running",
            }
        )
        flag = find_debug_flag()
        checks.append(
            {
                "name": "WebView2 debugging flag",
                "ok": flag is not None and str(port) in (flag or ""),
                "detail": flag
                or f"not set (run `parley setup` to set {WEBVIEW2_ENV_VAR})",
            }
        )
        checks.append(
            {
                "name": "port persists for future launches",
                "ok": _user_env_value(WEBVIEW2_ENV_VAR) is not None or (flag and str(port) in flag),
                "detail": "user env var" if _user_env_value(WEBVIEW2_ENV_VAR) else "env var / policy only",
            }
        )
    else:
        checks.append(
            {
                "name": "platform",
                "ok": True,
                "detail": platform,
            }
        )
        checks.append(
            {
                "name": "CDP attach support",
                "ok": None,
                "detail": "on macOS/Linux open web.whatsapp.com in Chrome/Edge started with "
                f"--remote-debugging-port={port} using your chat profile, set "
                "PARLEY_CDP_HOST/PARLEY_CDP_PORT if remote; parley attaches to that tab",
            }
        )

    endpoint = port_open(port)
    checks.append(
        {"name": f"CDP endpoint 127.0.0.1:{port}", "ok": endpoint, "detail": "open" if endpoint else "closed"}
    )
    if endpoint:
        checks.append(
            {
                "name": "SECURITY WARNING",
                "ok": False,
                "detail": (
                    "The WebView2 debugging port is OPEN — ANY process running as you "
                    "can drive your WhatsApp session and read all chats. "
                    "Run `parley setup --undo` when finished, or close WhatsApp Desktop."
                ),
            }
        )
    if endpoint and platform == "win32":
        try:
            from .session import parley_connect
            sess = parley_connect(port=port)
            st = sess.status()
            read_path = st.get("read_path", "unknown")
            checks.append(
                {
                    "name": "WhatsApp read path",
                    "ok": True,
                    "detail": f"{read_path} (store={st.get('store', False)})",
                }
            )
            sess.close()
        except Exception as exc:
            checks.append(
                {
                    "name": "WhatsApp read path",
                    "ok": None,
                    "detail": f"could not detect: {exc}",
                }
            )
    checks.append(
        {
            "name": "parley import",
            "ok": True,
            "detail": f"parley {_version()}",
        }
    )
    return {"ok": all(c["ok"] for c in checks if c["ok"] is True), "checks": checks}


def _version() -> str:
    try:
        from . import __version__

        return __version__
    except Exception:
        return "?"
