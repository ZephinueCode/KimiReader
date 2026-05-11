"""
Kimi 平台实现 (kimi.moonshot.cn)
"""

from typing import List
import playwright.sync_api as pw

from .base import BasePlatform, ChatMessage, ChatSession


class KimiPlatform(BasePlatform):
    name = "kimi"
    domain = "kimi.moonshot.cn"
    login_url = "https://kimi.moonshot.cn"

    login_button_selectors = [
        'button:has-text("登录")',
        'button:has-text("登入")',
        'button:has-text("Login")',
        'button:has-text("Sign in")',
        'button:has-text("立即登录")',
        'a:has-text("登录")',
        'a:has-text("Login")',
        '[class*="login"]',
        '[class*="signin"]',
    ]

    user_indicator_selectors = [
        '[class*="avatar"]',
        '[class*="user"]',
        '[class*="profile"]',
        'img[alt*="头像"]',
        '[class*="logout"]',
        'button:has-text("退出")',
    ]

    session_list_selectors = [
        '[class*="chat-list"] [class*="item"]',
        '[class*="session"]',
        '[class*="conversation"] [class*="title"]',
        '[class*="history"] [class*="item"]',
        'a[href*="/chat/"]',
        'a[href*="/c/"]',
    ]

    expand_all_selectors = [
        'text=全部聊天记录',
        'text=查看全部',
        'text=全部对话',
        'text=更多',
        'text=More',
        'text=All chats',
        '[class*="all-chat"]',
        '[class*="view-all"]',
    ]

    sidebar_selectors = [
        '[class*="sidebar"]',
        '[class*="chat-list"]',
        '[class*="session-list"]',
        'nav',
        'aside',
    ]

    message_container_selectors = [
        '[class*="message-list"]',
        '[class*="chat-list"]',
        '[class*="conversation-content"]',
        '[class*="messages"]',
        'main',
        'body',
    ]

    message_item_selectors = [
        '> div',
        '[class*="message"]',
        '[class*="bubble"]',
        '[class*="chat-item"]',
    ]

    api_url_patterns = ["session", "conversation", "chat", "history"]

    def extract_messages(self, page: pw.Page) -> List[ChatMessage]:
        """Kimi 消息提取。"""
        messages = self._generic_message_extract(page)
        if not messages:
            messages = self._extract_from_state(page)
        return messages
