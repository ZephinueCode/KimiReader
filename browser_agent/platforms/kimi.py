"""
Kimi 平台实现 (kimi.moonshot.cn)
"""

from typing import List
import playwright.sync_api as pw

from .base import BasePlatform, ChatMessage, ChatSession


class KimiPlatform(BasePlatform):
    name = "kimi"
    domain = "www.kimi.com"
    login_url = "https://www.kimi.com"

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
        'a[href*="/share/"]',
    ]

    expand_all_selectors = [
        'text=全部聊天记录',
        'text=查看全部',
        'text=全部对话',
        'text=展开全部',
        'text=显示更多',
        'text=查看更多',
        'text=更多',
        'text=More',
        'text=All chats',
        'text=View all',
        'text=Show more',
        'text=Load more',
        '[class*="all-chat"]',
        '[class*="view-all"]',
        '[class*="show-more"]',
        '[class*="expand"]',
        'button:has-text("查看")',
        'button:has-text("更多")',
    ]

    sidebar_selectors = [
        '[class*="sidebar"]',
        '[class*="chat-list"]',
        '[class*="session-list"]',
        '[class*="conversation-list"]',
        '[class*="history-list"]',
        'nav',
        'aside',
        # Kimi 新 UI 可能是普通的 div 作为侧边栏
        'div:has(> a[href*="/chat/"])',
        'div:has(> a[href*="/c/"])',
        'div:has(a[href*="/chat/"])',
        'div:has(a[href*="/c/"])',
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
    history_url = "https://www.kimi.com/chat/history"

    def extract_sessions_from_dom(self, page: pw.Page, max_sessions: int = 30) -> List[ChatSession]:
        """Kimi 新 UI 提取：适配 www.kimi.com/chat/history 页面结构。"""
        sessions = []
        seen_ids = set()
        import re

        # 如果当前不是 history 页面，尝试直接跳转
        if "/chat/history" not in page.url:
            try:
                print(f"[kimi] Redirecting to history page...", flush=True)
                page.goto(self.history_url, wait_until="load", timeout=15000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print(f"[kimi] History page redirect warning: {e}", flush=True)

        # 滚动加载更多（如果有懒加载）
        try:
            for i in range(5):
                before = page.evaluate("""() => document.querySelectorAll('a.history-link').length""")
                page.evaluate("""() => window.scrollTo(0, document.body.scrollHeight)""")
                page.wait_for_timeout(1000)
                after = page.evaluate("""() => document.querySelectorAll('a.history-link').length""")
                print(f"[kimi] History scroll {i+1}: {before} -> {after} items", flush=True)
                if after <= before:
                    break
        except Exception as e:
            print(f"[kimi] Scroll error: {e}", flush=True)

        # JS 提取所有历史会话
        try:
            raw_data = page.evaluate("""
                () => {
                    const results = [];
                    const links = document.querySelectorAll('a.history-link');
                    links.forEach(a => {
                        const href = a.getAttribute('href') || '';
                        // 标题：在 .title-wrapper 或直接的 .title 里
                        const titleEl = a.querySelector('.title-wrapper .title') || a.querySelector('.title');
                        const title = titleEl ? titleEl.innerText.trim() : '';
                        // 内容摘要
                        const contentEl = a.querySelector('.content');
                        const content = contentEl ? contentEl.innerText.trim().substring(0, 200) : '';
                        // 日期
                        const dateEl = a.querySelector('.date');
                        const date = dateEl ? dateEl.innerText.trim() : '';
                        // 分组（今天/本周/本月/今年）
                        let group = '';
                        const groupList = a.closest('.group-list');
                        if (groupList) {
                            const prev = groupList.previousElementSibling;
                            if (prev && prev.classList.contains('group-name')) {
                                group = prev.innerText.trim();
                            }
                        }
                        results.push({href, title, content, date, group});
                    });
                    return results;
                }
            """)

            print(f"[kimi] Extracted {len(raw_data)} raw items from history page", flush=True)
            for item in raw_data[:3]:
                print(f"  [{item.get('group','')}] {item.get('title','')[:50]} | {item.get('href','')[:50]}", flush=True)

            for item in raw_data:
                href = item.get("href", "")
                title = item.get("title", "")
                match = re.search(r"/chat/([a-f0-9-]+)", href)
                sid = match.group(1) if match else ""
                # 去掉查询参数，构造干净的 URL
                clean_href = href.split("?")[0] if "?" in href else href
                url = f"https://{self.domain}{clean_href}" if clean_href.startswith("/") else clean_href

                if sid and title and sid not in seen_ids:
                    seen_ids.add(sid)
                    sessions.append(ChatSession(
                        session_id=sid,
                        title=title,
                        url=url,
                        updated_at=item.get("date", ""),
                    ))
        except Exception as e:
            print(f"[kimi] DOM extract error: {e}", flush=True)

        if not sessions:
            print("[kimi] Falling back to base extract_sessions_from_dom", flush=True)
            sessions = super().extract_sessions_from_dom(page, max_sessions)

        return sessions[:max_sessions]

    def extract_messages(self, page: pw.Page) -> List[ChatMessage]:
        """Kimi 消息提取。"""
        messages = self._generic_message_extract(page)
        if not messages:
            messages = self._extract_from_state(page)
        return messages
