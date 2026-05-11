"""
聊天记录提取模块
负责：
- 获取网页版上的对话列表
- 选择特定对话
- 提取对话中的消息内容
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import playwright.sync_api as pw

from .auth import AuthManager


class ChatSession:
    """代表一个聊天会话的摘要信息。"""
    def __init__(self, session_id: str, title: str, url: str, updated_at: Optional[str] = None):
        self.session_id = session_id
        self.title = title
        self.url = url
        self.updated_at = updated_at

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "title": self.title,
            "url": self.url,
            "updated_at": self.updated_at,
        }


class ChatMessage:
    """代表一条聊天消息。"""
    def __init__(self, role: str, content: str, timestamp: Optional[str] = None):
        self.role = role
        self.content = content
        self.timestamp = timestamp

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }


class ChatExtractor:
    """使用Playwright从kimi.moonshot.cn提取聊天记录。"""

    BASE_URL = "https://kimi.moonshot.cn"

    def __init__(self, auth_manager: Optional[AuthManager] = None, browser_type: str = "chromium"):
        self.auth = auth_manager or AuthManager()
        self.browser_type = browser_type

    def _create_browser_context(self, p: pw.Playwright, headless: bool = True):
        """创建浏览器和上下文。"""
        browser_cls = getattr(p, self.browser_type)
        browser = browser_cls.launch(headless=headless)
        context = browser.new_context(**self.auth.get_context_args())
        return browser, context

    def list_sessions(self, headless: bool = True, max_sessions: int = 30) -> List[ChatSession]:
        """
        获取网页版Kimi上的历史对话列表。
        会尝试点击"全部聊天记录"并滚动加载更多，最多返回 max_sessions 条。
        """
        sessions = []
        api_sessions = []  # 从网络请求拦截获取的列表

        with pw.sync_playwright() as p:
            browser, context = self._create_browser_context(p, headless=headless)
            page = context.new_page()

            # 设置网络请求拦截，尝试捕获对话列表API
            def handle_response(response):
                try:
                    url = response.url
                    if ("session" in url or "conversation" in url or "chat" in url or "history" in url) and response.status == 200:
                        content_type = response.headers.get("content-type", "")
                        if "json" in content_type:
                            data = response.json()
                            self._try_parse_api_sessions(data, api_sessions)
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                # QoL: 尝试点击"全部聊天记录"按钮展开完整列表
                self._expand_all_sessions(page)

                # QoL: 滚动侧边栏加载更多（处理懒加载）
                self._scroll_sidebar_to_load_more(page)

                # 等待网络请求完成
                page.wait_for_timeout(2000)

                # 策略1: 优先使用API拦截到的数据（最完整）
                if api_sessions:
                    sessions = api_sessions[:max_sessions]

                # 策略2: 从DOM提取补充
                if not sessions:
                    sessions = self._extract_sessions_from_dom(page, max_sessions)

                # 策略3: 从JavaScript全局状态提取
                if not sessions:
                    sessions = self._extract_sessions_from_state(page, max_sessions)

            finally:
                browser.close()

        return sessions

    def _try_parse_api_sessions(self, data, output_list: List[ChatSession]):
        """尝试从API响应JSON中解析会话列表。"""
        if not isinstance(data, dict):
            return

        # 常见的API响应结构
        candidates = []
        if "data" in data and isinstance(data["data"], list):
            candidates = data["data"]
        elif "data" in data and isinstance(data["data"], dict):
            for key in ["sessions", "conversations", "chats", "list", "items"]:
                if key in data["data"] and isinstance(data["data"][key], list):
                    candidates = data["data"][key]
                    break
        elif "list" in data and isinstance(data["list"], list):
            candidates = data["list"]
        elif "items" in data and isinstance(data["items"], list):
            candidates = data["items"]
        elif "sessions" in data and isinstance(data["sessions"], list):
            candidates = data["sessions"]
        elif "conversations" in data and isinstance(data["conversations"], list):
            candidates = data["conversations"]

        for item in candidates:
            if not isinstance(item, dict):
                continue
            sid = item.get("id") or item.get("session_id") or item.get("conversation_id") or item.get("sessionId") or ""
            title = item.get("title") or item.get("name") or item.get("topic") or "Untitled"
            url = item.get("url") or f"{self.BASE_URL}/chat/{sid}" if sid else ""
            updated = item.get("updated_at") or item.get("updateTime") or item.get("last_message_time")
            if title and sid:
                output_list.append(ChatSession(
                    session_id=sid,
                    title=title,
                    url=url,
                    updated_at=updated,
                ))

    def _expand_all_sessions(self, page: pw.Page):
        """尝试点击'全部聊天记录'或类似的展开按钮。"""
        expand_selectors = [
            'text=全部聊天记录',
            'text=查看全部',
            'text=全部对话',
            'text=更多',
            'text=More',
            'text=All chats',
            'text=全部',
            '[class*="all-chat"]',
            '[class*="view-all"]',
            '[class*="more"]',
            'button:has-text("全部")',
            'a:has-text("全部")',
        ]
        for selector in expand_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1500):
                    btn.click(timeout=5000)
                    print(f"[QoL] 已点击展开按钮: {selector}")
                    page.wait_for_timeout(2500)  # 等待列表展开
                    return
            except Exception:
                continue

    def _scroll_sidebar_to_load_more(self, page: pw.Page, max_scrolls: int = 10):
        """滚动侧边栏触发懒加载。"""
        # 常见的侧边栏选择器
        sidebar_selectors = [
            '[class*="sidebar"]',
            '[class*="chat-list"]',
            '[class*="session-list"]',
            '[class*="history-list"]',
            'nav',
            'aside',
        ]

        for sb_selector in sidebar_selectors:
            try:
                sidebar = page.locator(sb_selector).first
                if not sidebar.is_visible(timeout=1000):
                    continue

                for i in range(max_scrolls):
                    # 获取当前列表项数量
                    items_before = sidebar.locator('> div, [class*="item"], a').count()

                    # 滚动到底部
                    sidebar.evaluate("(el) => el.scrollTo(0, el.scrollHeight)")
                    page.wait_for_timeout(800)

                    # 检查是否有新增
                    items_after = sidebar.locator('> div, [class*="item"], a').count()
                    if items_after <= items_before:
                        break  # 没有新内容加载了

                return
            except Exception:
                continue

    def _extract_sessions_from_dom(self, page: pw.Page, max_sessions: int) -> List[ChatSession]:
        """从DOM结构提取会话列表。"""
        sessions = []
        seen_ids = set()

        session_selectors = [
            '[class*="chat-list"] [class*="item"]',
            '[class*="session-list"] [class*="item"]',
            '[class*="conversation"] [class*="title"]',
            '[class*="history"] [class*="item"]',
            '[class*="sidebar"] a[href*="/chat/"]',
            '[class*="sidebar"] a[href*="/c/"]',
            'a[href*="/chat/"]',
            'a[href*="/c/"]',
            '[class*="session"]',
            '[class*="chat-item"]',
        ]

        for selector in session_selectors:
            try:
                items = page.locator(selector).all()
                for item in items:
                    try:
                        title = item.inner_text(timeout=1500).strip()
                        href = item.get_attribute("href") or ""
                        sid = ""
                        if href:
                            match = re.search(r"/(chat|c)/([a-zA-Z0-9_-]+)", href)
                            if match:
                                sid = match.group(2)
                            url = self.BASE_URL + href if href.startswith("/") else href
                        else:
                            url = page.url
                            sid = ""

                        # 去重
                        dedup_key = sid or title
                        if dedup_key and dedup_key not in seen_ids and title and len(title) > 0:
                            seen_ids.add(dedup_key)
                            sessions.append(ChatSession(
                                session_id=sid or f"unknown_{len(sessions)}",
                                title=title,
                                url=url,
                            ))
                    except Exception:
                        continue

                if len(sessions) >= max_sessions:
                    break
            except Exception:
                continue

        return sessions[:max_sessions]

    def _extract_sessions_from_state(self, page: pw.Page, max_sessions: int) -> List[ChatSession]:
        """从JavaScript全局状态提取会话列表。"""
        sessions = []
        try:
            state_data = page.evaluate("""
                () => {
                    // 深度搜索包含会话列表的对象
                    function findSessions(obj, depth = 0) {
                        if (depth > 5) return [];
                        const results = [];
                        for (const key of Object.keys(obj)) {
                            try {
                                const val = obj[key];
                                if (!val || typeof val !== 'object') continue;
                                if (Array.isArray(val) && val.length > 0) {
                                    const first = val[0];
                                    if (first && (first.id || first.title || first.name)) {
                                        results.push(...val);
                                    }
                                } else {
                                    results.push(...findSessions(val, depth + 1));
                                }
                            } catch(e) {}
                        }
                        return results;
                    }
                    return findSessions(window);
                }
            """)
            seen = set()
            for item in state_data:
                if not isinstance(item, dict):
                    continue
                sid = item.get("id", "")
                title = item.get("title", "") or item.get("name", "") or "Untitled"
                if sid and title and sid not in seen:
                    seen.add(sid)
                    sessions.append(ChatSession(
                        session_id=sid,
                        title=title,
                        url=f"{self.BASE_URL}/chat/{sid}",
                    ))
        except Exception:
            pass
        return sessions[:max_sessions]

    def extract_session(self, session_id: Optional[str] = None, url: Optional[str] = None,
                        headless: bool = True) -> dict:
        """
        提取特定会话的完整聊天记录。
        """
        target_url = url or f"{self.BASE_URL}/chat/{session_id}"

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
                    title = session_id or "kimi_chat"

                messages = self._extract_messages_from_page(page)

            finally:
                browser.close()

        return {
            "title": title,
            "source": "kimi.moonshot.cn",
            "session_id": session_id,
            "url": target_url,
            "export_time": datetime.now().isoformat(),
            "message_count": len(messages),
            "messages": [m.to_dict() for m in messages],
        }

    def _extract_messages_from_page(self, page: pw.Page) -> List[ChatMessage]:
        """从页面中提取消息列表，使用多种策略。"""
        messages = []

        # 策略1：基于常见的消息DOM结构
        message_container_selectors = [
            '[class*="message-list"]',
            '[class*="chat-list"]',
            '[class*="conversation-content"]',
            '[class*="messages"]',
            'main',
            'body',
        ]

        for container_selector in message_container_selectors:
            try:
                container = page.locator(container_selector).first
                if not container.is_visible(timeout=2000):
                    continue

                msg_selectors = [
                    '> div',
                    '[class*="message"]',
                    '[class*="bubble"]',
                    '[class*="chat-item"]',
                ]

                for msg_sel in msg_selectors:
                    items = container.locator(msg_sel).all()
                    if len(items) >= 2:
                        extracted = self._parse_message_elements(items)
                        if len(extracted) > len(messages):
                            messages = extracted

            except Exception:
                continue

        # 策略2：通过JavaScript遍历DOM提取
        if not messages:
            try:
                extracted = page.evaluate("""
                    () => {
                        const results = [];
                        const candidates = document.querySelectorAll('div, article, section');
                        const seen = new Set();

                        for (const el of candidates) {
                            const text = el.innerText || '';
                            if (text.length < 5 || text.length > 10000) continue;
                            if (seen.has(text)) continue;

                            const cls = el.className || '';
                            let role = null;

                            if (/user|human|发送者|我|right|self|own|question/i.test(cls)) {
                                role = 'user';
                            } else if (/assistant|ai|kimi|bot|model|answer|reply|left/i.test(cls)) {
                                role = 'assistant';
                            }

                            if (!role) {
                                const style = window.getComputedStyle(el);
                                if (style.alignSelf === 'flex-end') role = 'user';
                                else if (style.alignSelf === 'flex-start') role = 'assistant';
                            }

                            if (!role) {
                                const avatar = el.querySelector('img[src*="avatar"], img[class*="avatar"]');
                                if (avatar) role = 'assistant';
                            }

                            if (role) {
                                seen.add(text);
                                results.push({role, content: text.trim()});
                            }
                        }
                        return results;
                    }
                """)
                for item in extracted:
                    messages.append(ChatMessage(
                        role=item["role"],
                        content=item["content"],
                    ))
            except Exception:
                pass

        # 策略3：从全局状态提取
        if not messages:
            try:
                state_messages = page.evaluate("""
                    () => {
                        for (const key of Object.keys(window)) {
                            try {
                                const val = window[key];
                                if (val && typeof val === 'object') {
                                    const msgs = val.messages || val.chatMessages || val.conversation;
                                    if (Array.isArray(msgs) && msgs.length > 0 && msgs[0].content) {
                                        return msgs.map(m => ({
                                            role: m.role || m.sender || 'unknown',
                                            content: m.content || m.text || ''
                                        }));
                                    }
                                }
                            } catch(e) {}
                        }
                        return [];
                    }
                """)
                for item in state_messages:
                    if item.get("content"):
                        messages.append(ChatMessage(
                            role=item["role"],
                            content=item["content"],
                        ))
            except Exception:
                pass

        # 清理和过滤
        cleaned = []
        seen_contents = set()
        for msg in messages:
            content = msg.content.strip()
            if len(content) < 2:
                continue
            if content in seen_contents:
                continue
            seen_contents.add(content)
            cleaned.append(msg)

        return cleaned

    def _parse_message_elements(self, items: List[pw.Locator]) -> List[ChatMessage]:
        """解析一组消息元素。"""
        messages = []
        for item in items:
            try:
                text = item.inner_text(timeout=1000).strip()
                if len(text) < 2:
                    continue

                cls = item.get_attribute("class") or ""
                role = None

                if any(k in cls.lower() for k in ["user", "human", "我", "发送", "right", "self", "own", "question"]):
                    role = "user"
                elif any(k in cls.lower() for k in ["assistant", "ai", "kimi", "bot", "model", "answer", "reply", "left"]):
                    role = "assistant"

                if not role:
                    try:
                        box = item.bounding_box()
                        if box:
                            page_width = item.page().viewport_size["width"]
                            if box["x"] > page_width * 0.4:
                                role = "user"
                            else:
                                role = "assistant"
                    except Exception:
                        role = "unknown"

                messages.append(ChatMessage(role=role or "unknown", content=text))
            except Exception:
                continue

        return messages
