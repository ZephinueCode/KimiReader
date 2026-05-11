#!/usr/bin/env python3
"""
KimiReader Browser Agent CLI入口（多平台支持）
支持: kimi (kimi.moonshot.cn), deepseek (chat.deepseek.com), chatgpt (chatgpt.com)
"""

import json
import sys
import os
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
elif sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from browser_agent.auth import AuthManager
    from browser_agent.extractor import ChatExtractor
except ImportError as e:
    buf = json.dumps({
        "error": f"Browser agent module not found: {e}. Please run install script first."
    }, ensure_ascii=False)
    sys.stdout.buffer.write(buf.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.exit(1)


def main():
    params = json.load(sys.stdin)
    action = params.get("action", "status")
    platform = params.get("platform", "kimi")
    browser_type = params.get("browser_type", "chromium")
    headless = params.get("headless", True)

    auth = AuthManager(platform=platform)
    extractor = ChatExtractor(platform=platform, auth_manager=auth, browser_type=browser_type)

    try:
        if action == "status":
            result = auth.get_status()

        elif action == "login":
            force = params.get("force", False)
            auth.ensure_login(browser_type=browser_type, force_relogin=force,
                              platform_name=platform)
            result = auth.get_status()

        elif action == "logout":
            auth.logout()
            result = {"status": "logged_out", "platform": platform}

        elif action == "list":
            if not auth.is_logged_in(browser_type):
                result = {
                    "error": f"Not logged in to {platform}. Please run login action first.",
                    "hint": f"Use action='login' with platform='{platform}' to login."
                }
            else:
                sessions = extractor.list_sessions(headless=headless)
                result = {
                    "platform": platform,
                    "sessions": [s.to_dict() for s in sessions],
                    "count": len(sessions),
                }

        elif action == "extract":
            if not auth.is_logged_in(browser_type):
                result = {
                    "error": f"Not logged in to {platform}. Please run login action first.",
                    "hint": f"Use action='login' with platform='{platform}' to login."
                }
            else:
                session_id = params.get("session_id", "")
                url = params.get("url", "")
                index = params.get("index", None)

                if index is not None and not session_id and not url:
                    sessions = extractor.list_sessions(headless=headless)
                    if 0 <= index < len(sessions):
                        session_id = sessions[index].session_id
                        url = sessions[index].url
                    else:
                        result = {
                            "error": f"Invalid index {index}. Found {len(sessions)} sessions."
                        }
                        _write_json(result)
                        return

                if not session_id and not url:
                    sessions = extractor.list_sessions(headless=headless)
                    result = {
                        "error": "No session_id or url provided.",
                        "platform": platform,
                        "sessions": [s.to_dict() for s in sessions],
                        "hint": "Use 'index' parameter (0-based) to select a session, or provide session_id/url."
                    }
                else:
                    data = extractor.extract_session(
                        session_id=session_id or None,
                        url=url or None,
                        headless=headless,
                    )
                    full_text_parts = []
                    for msg in data.get("messages", []):
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        full_text_parts.append(f"**{role}**: {content}")
                    data["full_text"] = "\n\n".join(full_text_parts)
                    result = data

        else:
            result = {"error": f"Unknown action: {action}. Supported: status, login, logout, list, extract"}

    except Exception as e:
        result = {"error": str(e), "action": action, "platform": platform}

    _write_json(result)


def _write_json(data):
    output = json.dumps(data, ensure_ascii=False, indent=2)
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
