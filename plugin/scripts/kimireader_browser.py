#!/usr/bin/env python3
"""
KimiReader Browser Agent CLI入口
被Kimi Code CLI插件调用，支持以下操作：
- login: 交互式登录
- logout: 清除登录状态
- status: 查看登录状态
- list: 列出网页版上的历史对话
- extract: 提取指定对话的聊天记录
"""

import json
import sys
import os
from pathlib import Path

# 将browser_agent模块加入路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

try:
    from browser_agent.auth import AuthManager
    from browser_agent.extractor import ChatExtractor
except ImportError as e:
    print(json.dumps({
        "error": f"Browser agent module not found: {e}. Please run install script first."
    }, ensure_ascii=False))
    sys.exit(1)


def main():
    params = json.load(sys.stdin)
    action = params.get("action", "status")
    browser_type = params.get("browser_type", "chromium")
    headless = params.get("headless", True)

    auth = AuthManager()
    extractor = ChatExtractor(auth_manager=auth, browser_type=browser_type)

    try:
        if action == "status":
            result = auth.get_status()

        elif action == "login":
            force = params.get("force", False)
            auth.ensure_login(browser_type=browser_type, force_relogin=force)
            result = auth.get_status()

        elif action == "logout":
            auth.logout()
            result = {"status": "logged_out"}

        elif action == "list":
            if not auth.is_logged_in(browser_type):
                result = {
                    "error": "Not logged in. Please run login action first.",
                    "hint": "Use action='login' to open browser and login manually."
                }
            else:
                sessions = extractor.list_sessions(headless=headless)
                result = {
                    "sessions": [s.to_dict() for s in sessions],
                    "count": len(sessions),
                }

        elif action == "extract":
            if not auth.is_logged_in(browser_type):
                result = {
                    "error": "Not logged in. Please run login action first.",
                    "hint": "Use action='login' to open browser and login manually."
                }
            else:
                session_id = params.get("session_id", "")
                url = params.get("url", "")
                index = params.get("index", None)  # 从list结果中选择第index个

                # 如果提供了index，先list再选择
                if index is not None and not session_id and not url:
                    sessions = extractor.list_sessions(headless=headless)
                    if 0 <= index < len(sessions):
                        session_id = sessions[index].session_id
                        url = sessions[index].url
                    else:
                        result = {
                            "error": f"Invalid index {index}. Found {len(sessions)} sessions."
                        }
                        print(json.dumps(result, ensure_ascii=False, indent=2))
                        return

                if not session_id and not url:
                    # 未指定，列出所有让用户选择
                    sessions = extractor.list_sessions(headless=headless)
                    result = {
                        "error": "No session_id or url provided.",
                        "sessions": [s.to_dict() for s in sessions],
                        "hint": "Use 'index' parameter (0-based) to select a session from the list, or provide session_id/url."
                    }
                else:
                    data = extractor.extract_session(
                        session_id=session_id or None,
                        url=url or None,
                        headless=headless,
                    )
                    # 同时生成full_text便于直接阅读
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
        result = {"error": str(e), "action": action}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
