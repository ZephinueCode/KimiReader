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

    def list_sessions(self, headless: bool = True) -> List[ChatSession]:
        """
        获取网页版Kimi上的历史对话列表。
        返回对话列表（最近更新的排在前面）。
        """
        sessions = []
        with pw.sync_playwright() as p:
            browser, context = self._create_browser_context(p, headless=headless)
            page = context.new_page()
            try:
                page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)  # 等待列表加载

                # 策略1：通过侧边栏/历史列表的DOM结构提取
                # 常见的选择器模式
                session_selectors = [
                    '[class*="chat-list"] [class*="item"]',
                    '[class*="session"]',
                    '[class*="conversation"] [class*="title"]',
                    '[class*="history"] [class*="item"]',
                    'a[href*="/chat/"]',
                    'a[href*="/c/"]',
                ]

                for selector in session_selectors:
                    items = page.locator(selector).all()
                    for item in items:
                        try:
                            title = item.inner_text(timeout=2000).strip()
                            href = item.get_attribute("href") or ""
                            # 尝试获取session_id
                            session_id = ""
                            if href:
                                match = re.search(r"/(chat|c)/([a-zA-Z0-9_-]+)", href)
                                if match:
                                    session_id = match.group(2)
                                url = self.BASE_URL + href if href.startswith("/") else href
                            else:
                                url = page.url
                                session_id = ""

                            if title and len(title) > 0 and not any(s.title == title for s in sessions):
                                sessions.append(ChatSession(
                                    session_id=session_id or f"unknown_{len(sessions)}",
                                    title=title,
                                    url=url,
                                ))
                        except Exception:
                            continue

                    if sessions:
                        break  # 如果已经找到，不再尝试其他选择器

                # 策略2：从页面JavaScript状态中提取（React/Vue等框架）
                if not sessions:
                    try:
                        state_data = page.evaluate("""
                            () => {
                                // 尝试从window全局变量或React fiber树中提取
                                for (const key of Object.keys(window)) {
                                    try {
                                        const val = window[key];
                                        if (val && typeof val === 'object') {
                                            // 查找包含会话列表的状态
                                            if (Array.isArray(val.conversations) || Array.isArray(val.sessions) || Array.isArray(val.chatList)) {
                                                const list = val.conversations || val.sessions || val.chatList;
                                                return list.map(item => ({
                                                    id: item.id || item.sessionId || item.conversationId || '',
                                                    title: item.title || item.name || 'Untitled',
                                                    url: item.url || ''
                                                }));
                                            }
                                        }
                                    } catch(e) {}
                                }
                                return [];
                            }
                        """)
                        for item in state_data:
                            if item.get("title"):
                                sessions.append(ChatSession(
                                    session_id=item.get("id", f"unknown_{len(sessions)}"),
                                    title=item["title"],
                                    url=item.get("url") or f"{self.BASE_URL}/chat/{item.get('id', '')}",
                                ))
                    except Exception:
                        pass

            finally:
                browser.close()

        return sessions

    def extract_session(self, session_id: Optional[str] = None, url: Optional[str] = None,
                        headless: bool = True) -> dict:
        """
        提取特定会话的完整聊天记录。

        Args:
            session_id: 会话ID（如 cxxxxxx）
            url: 直接指定会话URL
            headless: 是否使用无头模式

        Returns:
            包含title、messages、metadata的字典
        """
        target_url = url or f"{self.BASE_URL}/chat/{session_id}"

        messages: List[ChatMessage] = []
        title = "Unknown Chat"

        with pw.sync_playwright() as p:
            browser, context = self._create_browser_context(p, headless=headless)
            page = context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)  # 等待消息加载

                # 获取标题
                try:
                    title_el = page.locator('h1, [class*="title"], [class*="chat-title"]').first
                    if title_el.is_visible(timeout=2000):
                        title = title_el.inner_text(timeout=2000).strip()
                except Exception:
                    pass

                # 如果没有从页面获取到标题，从URL推断
                if not title or title == "Unknown Chat":
                    title = session_id or "kimi_chat"

                # 提取消息 - 多策略
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

                # 在容器内查找消息元素
                msg_selectors = [
                    '> div',  # 直接子div
                    '[class*="message"]',
                    '[class*="bubble"]',
                    '[class*="chat-item"]',
                ]

                for msg_sel in msg_selectors:
                    items = container.locator(msg_sel).all()
                    if len(items) >= 2:  # 至少要有用户和助手各一条
                        extracted = self._parse_message_elements(items)
                        if len(extracted) > len(messages):
                            messages = extracted

            except Exception:
                continue

        # 策略2：通过aria角色或数据结构提取
        if not messages:
            try:
                extracted = page.evaluate("""
                    () => {
                        const results = [];
                        // 查找所有可能包含对话文本的元素
                        const candidates = document.querySelectorAll('div, article, section');
                        const seen = new Set();

                        for (const el of candidates) {
                            const text = el.innerText || '';
                            if (text.length < 5 || text.length > 10000) continue;
                            if (seen.has(text)) continue;

                            // 通过class判断角色
                            const cls = el.className || '';
                            let role = null;

                            if (/user|human|发送者|我|right|self|own|question/i.test(cls)) {
                                role = 'user';
                            } else if (/assistant|ai|kimi|bot|model|answer|reply|left/i.test(cls)) {
                                role = 'assistant';
                            }

                            // 通过DOM位置判断（Flexbox布局）
                            if (!role) {
                                const style = window.getComputedStyle(el);
                                if (style.alignSelf === 'flex-end') role = 'user';
                                else if (style.alignSelf === 'flex-start') role = 'assistant';
                            }

                            // 通过子元素特征判断
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

        # 策略3：从页面脚本标签或全局状态中提取
        if not messages:
            try:
                state_messages = page.evaluate("""
                    () => {
                        // 尝试找到包含messages数组的全局变量
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
            # 过滤掉太短的或纯换行的
            if len(content) < 2:
                continue
            # 去重（相邻的相同内容）
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

                # 判断角色
                cls = item.get_attribute("class") or ""
                role = None

                if any(k in cls.lower() for k in ["user", "human", "我", "发送", "right", "self", "own", "question"]):
                    role = "user"
                elif any(k in cls.lower() for k in ["assistant", "ai", "kimi", "bot", "model", "answer", "reply", "left"]):
                    role = "assistant"

                # 通过computed style辅助判断
                if not role:
                    try:
                        box = item.bounding_box()
                        if box:
                            # 获取页面宽度
                            page_width = item.page().viewport_size["width"]
                            # 如果元素偏右，可能是用户消息
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
