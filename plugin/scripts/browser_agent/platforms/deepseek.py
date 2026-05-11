"""
DeepSeek 平台实现 (chat.deepseek.com)
"""

from typing import List
import playwright.sync_api as pw

from .base import BasePlatform, ChatMessage, ChatSession


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
        # DeepSeek 使用哈希 class，直接匹配 href 模式最可靠
        'a[href*="/a/chat/s/"]',
        'a[href*="/chat/s/"]',
        # 备用：如果 href 没加载出来，尝试通用的 a 标签（在已登录页面中，侧边栏的 a 基本都是会话）
        'nav a',
        'aside a',
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

    def extract_sessions_from_dom(self, page: pw.Page, max_sessions: int = 30) -> List[ChatSession]:
        """DeepSeek 特定的 DOM 提取：哈希 class + 嵌套标题结构。"""
        sessions = []
        seen_ids = set()

        # 策略1：直接通过 href 模式匹配（最可靠）
        try:
            items = page.locator('a[href*="/a/chat/s/"]').all()
            for item in items:
                try:
                    href = item.get_attribute("href") or ""
                    # 提取 uuid：/a/chat/s/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
                    import re
                    match = re.search(r"/a/chat/s/([a-f0-9-]+)", href)
                    sid = match.group(1) if match else ""

                    # DeepSeek 的标题在嵌套的 div.c08e6e93 里
                    title = ""
                    try:
                        title_el = item.locator('div[class*="c08e6e93"]').first
                        if title_el.is_visible(timeout=500):
                            title = title_el.inner_text(timeout=1000).strip()
                    except Exception:
                        # fallback：用 a 标签的整体文本，但要去掉日期分组标题
                        full_text = item.inner_text(timeout=1000).strip()
                        # 去掉可能的 svg/按钮文本
                        lines = [l for l in full_text.split('\n') if l.strip() and len(l.strip()) > 2]
                        if lines:
                            title = lines[0]

                    url = f"https://{self.domain}{href}" if href.startswith("/") else href

                    if sid and title and sid not in seen_ids:
                        seen_ids.add(sid)
                        sessions.append(ChatSession(
                            session_id=sid,
                            title=title,
                            url=url,
                        ))
                except Exception:
                    continue
        except Exception:
            pass

        # 策略2：如果策略1没结果，回退到通用提取
        if not sessions:
            sessions = super().extract_sessions_from_dom(page, max_sessions)

        return sessions[:max_sessions]

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
