"""
平台抽象基类
定义各平台需要实现的接口和通用默认行为。
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import playwright.sync_api as pw


class ChatSession:
    """通用会话摘要。"""
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
    """通用消息结构。"""
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


class BasePlatform(ABC):
    """聊天平台抽象基类。"""

    # 平台标识
    name: str = ""
    domain: str = ""
    login_url: str = ""

    # --- 登录相关选择器 ---
    login_button_selectors: List[str] = []
    user_indicator_selectors: List[str] = []
    logout_button_selectors: List[str] = []

    # --- 会话列表相关 ---
    session_list_selectors: List[str] = []
    expand_all_selectors: List[str] = []
    sidebar_selectors: List[str] = []

    # --- 消息提取相关 ---
    message_container_selectors: List[str] = []
    message_item_selectors: List[str] = []

    # --- API 拦截相关 ---
    api_url_patterns: List[str] = []

    def __init__(self):
        pass

    # ==================== 登录 ====================

    def is_logged_in(self, page: pw.Page) -> bool:
        """检测当前页面是否已登录。"""
        url = page.url
        if any(path in url for path in ["/login", "/auth", "/signin"]):
            return False

        # 检查用户指示器
        for selector in self.user_indicator_selectors:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        # 检查 token
        token = page.evaluate(
            "() => localStorage.getItem('token') || "
            "localStorage.getItem('access_token') || "
            "sessionStorage.getItem('token') || "
            "localStorage.getItem('refresh_token') || ''"
        )
        if token and len(str(token)) > 10:
            return True

        return False

    def get_login_button_selectors(self) -> List[str]:
        """返回登录按钮的选择器列表。"""
        return self.login_button_selectors

    # ==================== 会话列表 ====================

    def get_expand_all_selectors(self) -> List[str]:
        """返回'展开全部'按钮的选择器。"""
        return self.expand_all_selectors

    def get_sidebar_selectors(self) -> List[str]:
        """返回侧边栏选择器。"""
        return self.sidebar_selectors

    def extract_sessions_from_dom(self, page: pw.Page, max_sessions: int = 30) -> List[ChatSession]:
        """从 DOM 提取会话列表。通用实现，平台可覆盖。"""
        sessions = []
        seen_ids = set()

        for selector in self.session_list_selectors:
            try:
                items = page.locator(selector).all()
                for item in items:
                    try:
                        title = item.inner_text(timeout=1500).strip()
                        href = item.get_attribute("href") or ""

                        # 提取 session_id
                        sid = ""
                        if href:
                            # 常见格式: /chat/xxx, /c/xxx, /g/xxx
                            import re
                            match = re.search(r"/(chat|c|g)/s?/([a-f0-9-]+|[a-zA-Z0-9_-]+)", href)
                            if match:
                                sid = match.group(2)
                            url = f"https://{self.domain}{href}" if href.startswith("/") else href
                        else:
                            url = page.url
                            # 尝试从 data 属性获取 id
                            sid = item.get_attribute("data-id") or item.get_attribute("data-session-id") or ""

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

    def extract_sessions_from_api(self, data: dict, output_list: List[ChatSession]):
        """从 API 响应 JSON 解析会话列表。通用实现。"""
        if not isinstance(data, dict):
            return

        candidates = []
        for key in ["data", "list", "items", "sessions", "conversations", "chats", "history"]:
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    candidates = val
                    break
                elif isinstance(val, dict):
                    for subkey in ["sessions", "conversations", "chats", "list", "items"]:
                        if subkey in val and isinstance(val[subkey], list):
                            candidates = val[subkey]
                            break
                    if candidates:
                        break

        for item in candidates:
            if not isinstance(item, dict):
                continue
            sid = (item.get("id") or item.get("session_id") or item.get("conversation_id")
                   or item.get("sessionId") or item.get("conversationId") or "")
            title = item.get("title") or item.get("name") or item.get("topic") or "Untitled"
            url = item.get("url") or f"https://{self.domain}/chat/{sid}" if sid else ""
            updated = item.get("updated_at") or item.get("updateTime") or item.get("created_at")
            if title:
                output_list.append(ChatSession(
                    session_id=sid,
                    title=title,
                    url=url,
                    updated_at=updated,
                ))

    # ==================== 消息提取 ====================

    @abstractmethod
    def extract_messages(self, page: pw.Page) -> List[ChatMessage]:
        """从页面提取消息列表。每个平台必须实现自己的逻辑。"""
        pass

    def _generic_message_extract(self, page: pw.Page) -> List[ChatMessage]:
        """通用消息提取：基于常见 DOM 结构的 fallback 实现。"""
        messages = []

        for container_sel in self.message_container_selectors:
            try:
                container = page.locator(container_sel).first
                if not container.is_visible(timeout=2000):
                    continue

                for msg_sel in self.message_item_selectors:
                    items = container.locator(msg_sel).all()
                    if len(items) < 2:
                        continue

                    for item in items:
                        try:
                            text = item.inner_text(timeout=1000).strip()
                            if len(text) < 2:
                                continue

                            cls = item.get_attribute("class") or ""
                            role = self._detect_role(item, cls)
                            messages.append(ChatMessage(role=role, content=text))
                        except Exception:
                            continue

            except Exception:
                continue

        # 去重过滤
        cleaned = []
        seen = set()
        for msg in messages:
            c = msg.content.strip()
            if len(c) < 2 or c in seen:
                continue
            seen.add(c)
            cleaned.append(msg)

        return cleaned

    def _detect_role(self, item: pw.Locator, cls: str) -> str:
        """检测消息角色。通用启发式。"""
        cls_lower = cls.lower()

        # 通过 class 名
        if any(k in cls_lower for k in ["user", "human", "发送", "right", "self", "own", "question", "prompt"]):
            return "user"
        if any(k in cls_lower for k in ["assistant", "ai", "bot", "model", "answer", "reply", "left", "kimi", "deepseek", "gpt"]):
            return "assistant"

        # 通过 computed style
        try:
            style = item.evaluate("(el) => { const s = window.getComputedStyle(el); return {alignSelf: s.alignSelf, marginLeft: s.marginLeft, marginRight: s.marginRight, textAlign: s.textAlign}; }")
            if style:
                if style.get("alignSelf") == "flex-end" or style.get("textAlign") == "right":
                    return "user"
                if style.get("alignSelf") == "flex-start" or style.get("textAlign") == "left":
                    return "assistant"
        except Exception:
            pass

        # 通过 DOM 位置
        try:
            box = item.bounding_box()
            if box:
                viewport = item.page().viewport_size
                if viewport and box["x"] > viewport["width"] * 0.35:
                    return "user"
                else:
                    return "assistant"
        except Exception:
            pass

        return "unknown"

    def _extract_from_state(self, page: pw.Page) -> List[ChatMessage]:
        """从 window 全局状态提取消息。通用 fallback。"""
        messages = []
        try:
            state = page.evaluate("""
                () => {
                    for (const key of Object.keys(window)) {
                        try {
                            const val = window[key];
                            if (val && typeof val === 'object') {
                                const msgs = val.messages || val.chatMessages || val.conversation || val.conversations;
                                if (Array.isArray(msgs) && msgs.length > 0) {
                                    const first = msgs[0];
                                    if (first && (first.content || first.text || first.message)) {
                                        return msgs.map(m => ({
                                            role: m.role || m.sender || m.type || 'unknown',
                                            content: m.content || m.text || m.message || ''
                                        }));
                                    }
                                }
                            }
                        } catch(e) {}
                    }
                    return [];
                }
            """)
            for item in state:
                if item.get("content"):
                    messages.append(ChatMessage(
                        role=item["role"],
                        content=item["content"],
                    ))
        except Exception:
            pass
        return messages
