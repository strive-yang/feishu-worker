"""Check the real project MCP transport without calling any Feishu API tools.

Only initialize, notifications/initialized, and paginated tools/list are sent.
The official server may initialize its approved OAuth store. No tokens, tool
schemas, raw server diagnostics, or business content are printed or saved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import subprocess
import sys
from threading import Thread
from time import monotonic


ROOT = Path(__file__).resolve().parents[1]


def check() -> dict:
    if sys.platform != "win32" or not shutil.which("powershell.exe"):
        raise RuntimeError("Windows PowerShell is required")
    launcher = ROOT / "scripts/start-feishu-mcp.ps1"
    text = launcher.read_text(encoding="utf-8-sig")
    section = text.split("$FeishuTools = @(", 1)[1].split(") -join", 1)[0]
    expected = {name.replace(".", "_") for name in re.findall(r'"([a-zA-Z0-9.]+)"', section)}
    if not expected:
        raise RuntimeError("The project tool allowlist is empty")
    env = os.environ.copy()
    for key in list(env):
        if key.upper() in {"APP_ID", "APP_SECRET", "USER_ACCESS_TOKEN", "DEBUG", "NODE_OPTIONS"}:
            env.pop(key, None)
    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(launcher)],
        cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW)
    messages = Queue()
    protocol_errors = []
    stderr_bytes = [0]

    def read_stdout():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except (ValueError, UnicodeError):
                # Do not retain the offending line, which could be sensitive.
                protocol_errors.append(True)
        messages.put(None)

    def read_stderr():
        while chunk := process.stderr.read(4096):
            stderr_bytes[0] += len(chunk)

    readers = [Thread(target=read_stdout, daemon=True), Thread(target=read_stderr, daemon=True)]
    for reader in readers:
        reader.start()

    def send(message):
        process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        process.stdin.flush()

    def receive(request_id):
        # Bound both the wait and unexpected-message count; never print raw replies.
        deadline = monotonic() + 20
        for _ in range(100):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise RuntimeError("MCP protocol response timed out")
            try:
                response = messages.get(timeout=remaining)
            except Empty:
                raise RuntimeError("MCP protocol response timed out") from None
            if response is None:
                raise RuntimeError("MCP process closed before replying")
            if isinstance(response, dict) and response.get("id") == request_id:
                if "error" in response or not isinstance(response.get("result"), dict):
                    raise RuntimeError("MCP protocol request failed")
                return response["result"]
        raise RuntimeError("Too many unexpected MCP messages")

    forced_cleanup = False
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "feishu-worker-local-check", "version": "0.1.0"}}})
        receive(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        found = set()
        cursor = None
        seen_cursors = set()
        for page in range(100):
            request_id = page + 2
            send({"jsonrpc": "2.0", "id": request_id, "method": "tools/list",
                  "params": {"cursor": cursor} if cursor else {}})
            result = receive(request_id)
            tools = result.get("tools")
            if not isinstance(tools, list):
                raise RuntimeError("Invalid MCP tool list")
            for tool in tools:
                if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                    raise RuntimeError("Invalid MCP tool definition")
                found.add(tool["name"])
            cursor = result.get("nextCursor")
            if not cursor:
                break
            if not isinstance(cursor, str) or cursor in seen_cursors:
                raise RuntimeError("Invalid MCP pagination cursor")
            seen_cursors.add(cursor)
        else:
            raise RuntimeError("MCP pagination exceeded the bound")
        if found != expected:
            raise RuntimeError("MCP tool list differs from the project allowlist")
        process.stdin.close()
        try:
            exit_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            forced_cleanup = True
            exit_code = None
        for reader in readers:
            reader.join(timeout=1)
        return {"initialize": "passed", "tools_list": "passed", "tool_count": len(found),
                "protocol_errors": len(protocol_errors), "stderr_bytes": stderr_bytes[0],
                "exit_after_stdin_close": not forced_cleanup and exit_code == 0,
                "forced_cleanup": forced_cleanup,
                "feishu_api_tools_called": False}
    finally:
        if process.poll() is None:
            # Only the fresh test process tree is targeted. Never search or kill
            # another Agent's MCP process, or print command lines/environment.
            cleanup = subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                     capture_output=True, timeout=10)
            if cleanup.returncode != 0 and process.poll() is None:
                process.kill()
            process.wait(timeout=10)
        for reader in readers:
            reader.join(timeout=1)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe and not pipe.closed:
                pipe.close()


def main() -> int:
    try:
        result = check()
    except Exception:
        print("MCP check failed. Inspect project configuration and local diagnostics privately.", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["exit_after_stdin_close"] and result["protocol_errors"] == 0 else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
