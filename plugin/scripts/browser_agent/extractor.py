"""
聊天记录提取模块（多平台支持）
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import playwright.sync_api as pw

from .auth import AuthManager
from .platforms import get_platform, BasePlatform, ChatSession, ChatMessage


class ChatExtractor:
    """使用Playwright从各平台提取聊天记录。"""

    def __init__(self, platform: str = "kimi", auth_manager: Optional[AuthManager] = None,
                 browser_type: str = "chromium"):
        self.platform = get_platform(platform)
        self.auth = auth_manager or AuthManager(platform=platform)
        self.browser_type = browser_type

    def _create_browser_context(self, p: pw.Playwright, headless: bool = True):
        browser_cls = getattr(p, self.browser_type)
        browser = browser_cls.launch(headless=headless)
        context = browser.new_context(**self.auth.get_context_args())
        return browser, context

    def list_sessions(self, headless: bool = True, max_sessions: int = 30) -> List[ChatSession]:
        """
        获取历史对话列表。
        会尝试点击"全部聊天记录"并滚动加载更多，最多返回 max_sessions 条。
        """
        sessions = []
        api_sessions = []

        with pw.sync_playwright() as p:
            browser, context = self._create_browser_context(p, headless=headless)
            page = context.new_page()

            # 网络请求拦截
            def handle_response(response):
                try:
                    url = response.url
                    if any(pattern in url for pattern in self.platform.api_url_patterns) and response.status == 200:
                        content_type = response.headers.get("content-type", "")
                        if "json" in content_type:
                            data = response.json()
                            self.platform.extract_sessions_from_api(data, api_sessions)
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                page.goto(self.platform.login_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                self._expand_all_sessions(page)
                self._scroll_sidebar_to_load_more(page)
                page.wait_for_timeout(2000)

                if api_sessions:
                    sessions = api_sessions[:max_sessions]

                if not sessions:
                    sessions = self.platform.extract_sessions_from_dom(page, max_sessions)

            finally:
                browser.close()

        return sessions

    def _expand_all_sessions(self, page: pw.Page):
        """尝试点击'展开全部'按钮。"""
        for selector in self.platform.get_expand_all_selectors():
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1500):
                    btn.click(timeout=5000)
                    page.wait_for_timeout(2500)
                    return
            except Exception:
                continue

    def _scroll_sidebar_to_load_more(self, page: pw.Page, max_scrolls: int = 10):
        """滚动侧边栏触发懒加载。"""
        for sb_selector in self.platform.get_sidebar_selectors():
            try:
                sidebar = page.locator(sb_selector).first
                if not sidebar.is_visible(timeout=1000):
                    continue

                for i in range(max_scrolls):
                    items_before = sidebar.locator('> div, [class*="item"], a, li').count()
                    sidebar.evaluate("(el) => el.scrollTo(0, el.scrollHeight)")
                    page.wait_for_timeout(800)
                    items_after = sidebar.locator('> div, [class*="item"], a, li').count()
                    if items_after <= items_before:
                        break
                return
            except Exception:
                continue

    def extract_session(self, session_id: Optional[str] = None, url: Optional[str] = None,
                        headless: bool = True) -> dict:
        """提取特定会话的完整聊天记录。"""
        target_url = url or f"{self.platform.login_url}/c/{session_id}"

        messages: List[ChatMessage] = []
        title = "Unknown Chat"

        with pw.sync_playwright() as p:
            browser, context = self._create_browser_context(p, headless=headless)
            page = context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)

                # 获取标题
                try:
                    title_el = page.locator('h1, [class*="title"], [class*="chat-title"]').first
                    if title_el.is_visible(timeout=2000):
                        title = title_el.inner_text(timeout=2000).strip()
                except Exception:
                    pass

                if not title or title == "Unknown Chat":
                    title = session_id or f"{self.platform.name}_chat"

                messages = self.platform.extract_messages(page)

            finally:
                browser.close()

        return {
            "title": title,
            "source": self.platform.domain,
            "platform": self.platform.name,
            "session_id": session_id,
            "url": target_url,
            "export_time": datetime.now().isoformat(),
            "message_count": len(messages),
            "messages": [m.to_dict() for m in messages],
        }
