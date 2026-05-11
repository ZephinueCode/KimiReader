"""
DeepSeek 平台实现 (chat.deepseek.com)
"""

from typing import List
import playwright.sync_api as pw

from .base import BasePlatform, ChatMessage


class DeepSeekPlatform(BasePlatform):
    name = "deepseek"
    domain = "chat.deepseek.com"
    login_url = "https://chat.deepseek.com"

    login_button_selectors = [
        'button:has-text("登录")',
        'button:has-text("Log in")',
        'button:has-text("Sign in")',
        'a:has-text("登录")',
        'a:has-text("Log in")',
        '[class*="login"]',
        'button[data-testid*="login"]',
    ]

    user_indicator_selectors = [
        '[class*="avatar"]',
        '[class*="user"]',
        'img[alt*="avatar"]',
        'img[alt*="user"]',
        '[class*="account"]',
        '[class*="profile"]',
    ]

    session_list_selectors = [
        '[class*="session"]',
        '[class*="chat-item"]',
        '[class*="conversation"]',
        'nav a',
        'aside a',
        '[class*="sidebar"] a',
        '[class*="history"] > div',
        '[class*="list"] > div',
    ]

    expand_all_selectors = [
        'text=全部对话',
        'text=查看全部',
        'text=更多',
        'text=More',
        'text=All',
        '[class*="show-more"]',
        '[class*="expand"]',
    ]

    sidebar_selectors = [
        '[class*="sidebar"]',
        'nav',
        'aside',
        '[class*="drawer"]',
    ]

    message_container_selectors = [
        '[class*="message-list"]',
        '[class*="chat-content"]',
        '[class*="conversation"]',
        'main',
        'article',
        'body',
    ]

    message_item_selectors = [
        '[class*="message"]',
        '> div',
        '[class*="bubble"]',
        '[class*="chat-item"]',
    ]

    api_url_patterns = ["session", "conversation", "chat", "history", "messages"]

    def extract_messages(self, page: pw.Page) -> List[ChatMessage]:
        """DeepSeek 消息提取。"""
        messages = self._generic_message_extract(page)

        # DeepSeek 特有的：用户和助手消息通常有 data-testid 或 role 属性
        if not messages:
            try:
                dom_messages = page.evaluate("""
                    () => {
                        const results = [];
                        const items = document.querySelectorAll('[data-testid*="message"], [data-role], [role="user"], [role="assistant"]');
                        for (const el of items) {
                            const text = el.innerText || '';
                            if (text.length < 2) continue;
                            const roleAttr = el.getAttribute('data-role') || el.getAttribute('role') || '';
                            let role = 'unknown';
                            if (roleAttr.includes('user') || el.className.includes('user')) role = 'user';
                            else if (roleAttr.includes('assistant') || roleAttr.includes('bot') || el.className.includes('assistant')) role = 'assistant';
                            else {
                                // 通过位置判断
                                const rect = el.getBoundingClientRect();
                                if (rect.left > window.innerWidth * 0.25) role = 'user';
                                else role = 'assistant';
                            }
                            results.push({role, content: text.trim()});
                        }
                        return results;
                    }
                """)
                for item in dom_messages:
                    if item.get("content"):
                        messages.append(ChatMessage(role=item["role"], content=item["content"]))
            except Exception:
                pass

        if not messages:
            messages = self._extract_from_state(page)

        return messages
