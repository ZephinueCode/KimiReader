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
        print(f"[extractor] Starting list_sessions for platform={self.platform.name}, headless={headless}", flush=True)

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
                # Kimi 新 UI：直接访问 history 页面获取全部会话（更高效）
                if self.platform.name == "kimi":
                    target_url = getattr(self.platform, "history_url", self.platform.login_url)
                    print(f"[extractor] Kimi: navigating directly to {target_url}", flush=True)
                else:
                    target_url = self.platform.login_url
                    print(f"[extractor] Navigating to {target_url}", flush=True)

                try:
                    page.goto(target_url, wait_until="load", timeout=30000)
                except Exception as e:
                    print(f"[extractor] Page load warning (continuing): {e}", flush=True)
                print(f"[extractor] Page loaded, url={page.url}", flush=True)
                page.wait_for_timeout(5000)
                print(f"[extractor] Waited 5s, checking sidebar...", flush=True)

                # 非 Kimi 平台才需要点击展开+滚动
                if self.platform.name != "kimi":
                    self._expand_all_sessions(page)
                    self._scroll_sidebar_to_load_more(page)
                    page.wait_for_timeout(2000)

                print(f"[extractor] API sessions captured: {len(api_sessions)}", flush=True)
                if api_sessions:
                    sessions = api_sessions[:max_sessions]

                if not sessions:
                    print(f"[extractor] Falling back to DOM extraction...", flush=True)
                    sessions = self.platform.extract_sessions_from_dom(page, max_sessions)
                    print(f"[extractor] DOM extraction returned: {len(sessions)} sessions", flush=True)
                    for s in sessions[:3]:
                        print(f"  - {s.session_id}: {s.title}", flush=True)

            except Exception as e:
                print(f"[extractor] Error in list_sessions: {e}", flush=True)
            finally:
                browser.close()

        return sessions

    def _expand_all_sessions(self, page: pw.Page):
        """尝试点击'展开全部'按钮。使用 JS 直接查找更灵活。"""
        # 策略1：Playwright 选择器
        for selector in self.platform.get_expand_all_selectors():
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    print(f"[extractor] Clicked expand button via selector: {selector}", flush=True)
                    page.wait_for_timeout(3000)
                    return
            except Exception:
                continue

        # 策略2：JS 直接遍历所有按钮和可点击元素，按文字匹配
        try:
            clicked = page.evaluate("""
                () => {
                    const keywords = ['全部聊天记录','查看全部','全部对话','展开全部',
                                      '显示更多','加载更多','查看更多','更多',
                                      'More','All chats','View all','Show more',
                                      'Load more','查看历史','历史记录'];
                    const elements = document.querySelectorAll('button, a, div[role="button"], span[role="button"]');
                    for (const el of elements) {
                        const text = el.innerText.trim();
                        if (keywords.some(k => text.includes(k))) {
                            if (el.offsetParent !== null) {  // 可见
                                el.click();
                                return text;
                            }
                        }
                    }
                    return null;
                }
            """)
            if clicked:
                print(f"[extractor] Clicked expand button via JS: '{clicked}'", flush=True)
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[extractor] JS expand button error: {e}", flush=True)

    def _scroll_sidebar_to_load_more(self, page: pw.Page, max_scrolls: int = 15):
        """滚动侧边栏触发懒加载。支持多种滚动容器检测。"""
        for sb_selector in self.platform.get_sidebar_selectors():
            try:
                sidebar = page.locator(sb_selector).first
                if not sidebar.is_visible(timeout=1500):
                    continue

                print(f"[extractor] Scrolling sidebar via selector: {sb_selector}", flush=True)
                for i in range(max_scrolls):
                    items_before = sidebar.locator('> div, > a, > li, [class*="item"]').count()
                    sidebar.evaluate("(el) => { el.scrollTo(0, el.scrollHeight); }")
                    page.wait_for_timeout(1200)
                    items_after = sidebar.locator('> div, > a, > li, [class*="item"]').count()
                    print(f"[extractor] Scroll {i+1}: {items_before} -> {items_after} items", flush=True)
                    if items_after <= items_before:
                        break
                return
            except Exception as e:
                print(f"[extractor] Sidebar scroll error with {sb_selector}: {e}", flush=True)
                continue

        # Fallback: 如果所有选择器都没找到 sidebar，直接滚动 window
        try:
            print("[extractor] Fallback: scrolling window", flush=True)
            for i in range(max_scrolls):
                before = page.evaluate("""() => document.querySelectorAll('a[href*="/chat/"], a[href*="/c/"], a[href*="/share/"]').length""")
                page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1200)
                after = page.evaluate("""() => document.querySelectorAll('a[href*="/chat/"], a[href*="/c/"], a[href*="/share/"]').length""")
                print(f"[extractor] Window scroll {i+1}: {before} -> {after} links", flush=True)
                if after <= before:
                    break
        except Exception as e:
            print(f"[extractor] Window scroll error: {e}", flush=True)

    def extract_session(self, session_id: Optional[str] = None, url: Optional[str] = None,
                        headless: bool = True) -> dict:
        """提取特定会话的完整聊天记录。"""
        target_url = url or self.platform.get_session_url(session_id)

        messages: List[ChatMessage] = []
        title = "Unknown Chat"

        with pw.sync_playwright() as p:
            browser, context = self._create_browser_context(p, headless=headless)
            page = context.new_page()
            try:
                print(f"[extractor] Navigating to session URL: {target_url}", flush=True)
                try:
                    page.goto(target_url, wait_until="load", timeout=30000)
                except Exception as e:
                    print(f"[extractor] Page load warning (continuing): {e}", flush=True)
                page.wait_for_timeout(5000)

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
