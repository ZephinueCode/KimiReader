"""
ChatGPT 平台实现 (chatgpt.com / chat.openai.com)
"""

from typing import List
import playwright.sync_api as pw

from .base import BasePlatform, ChatMessage


class ChatGPTPlatform(BasePlatform):
    name = "chatgpt"
    domain = "chatgpt.com"
    login_url = "https://chatgpt.com"

    login_button_selectors = [
        'button:has-text("Log in")',
        'button:has-text("Login")',
        'button:has-text("Sign in")',
        'button:has-text("Get started")',
        'a:has-text("Log in")',
        'a:has-text("Login")',
        'a:has-text("Sign in")',
        '[data-testid*="login"]',
        '[class*="login"]',
    ]

    user_indicator_selectors = [
        '[class*="avatar"]',
        'img[alt*="User"]',
        'img[alt*="Profile"]',
        '[class*="account"]',
        '[aria-label*="settings"]',
        '[aria-label*="Settings"]',
        'button[data-testid*="profile"]',
    ]

    session_list_selectors = [
        'nav a[href*="/c/"]',
        'nav a[href*="/g/"]',
        '[class*="history"] a',
        '[class*="conversation"] a',
        '[class*="chat-list"] a',
        'li a',
        '[class*="group"] a',
        'nav > div > div > a',
        '[class*="sidebar"] a',
    ]

    expand_all_selectors = [
        'text=Show more',
        'text=View all',
        'text=Load more',
        'text=更多',
        'text=显示更多',
        'button:has-text("Show more")',
        'button:has-text("Load more")',
    ]

    sidebar_selectors = [
        'nav',
        '[class*="sidebar"]',
        'aside',
    ]

    message_container_selectors = [
        '[class*="conversation-content"]',
        '[class*="messages"]',
        'main',
        'article',
        '[data-testid*="conversation"]',
        'body',
    ]

    message_item_selectors = [
        '[data-testid*="message"]',
        '[class*="message"]',
        '> div',
        '[class*="group"]',
    ]

    api_url_patterns = ["conversation", "chat", "history", "backend-api"]

    def extract_messages(self, page: pw.Page) -> List[ChatMessage]:
        """ChatGPT 消息提取。ChatGPT 的消息结构比较规范，有 data-testid。"""
        messages = []

        # 策略1: ChatGPT 特有的 data-testid 结构
        try:
            items = page.locator('[data-testid^="conversation-turn-"]').all()
            if not items:
                # 备用选择器
                items = page.locator('[data-testid*="message"], [class*="group"]').all()

            for item in items:
                try:
                    text = item.inner_text(timeout=1500).strip()
                    if len(text) < 2:
                        continue

                    # ChatGPT 中用户消息通常在右侧，有特定的 class/data-testid
                    cls = item.get_attribute("class") or ""
                    testid = item.get_attribute("data-testid") or ""

                    role = "unknown"
                    if "user" in testid.lower() or "human" in cls.lower():
                        role = "user"
                    elif "assistant" in testid.lower() or "model" in cls.lower() or "gpt" in cls.lower():
                        role = "assistant"
                    else:
                        # 通过位置判断：右侧为用户
                        box = item.bounding_box()
                        if box:
                            viewport = item.page().viewport_size
                            if viewport and box["x"] > viewport["width"] * 0.25:
                                role = "user"
                            else:
                                role = "assistant"

                    messages.append(ChatMessage(role=role, content=text))
                except Exception:
                    continue
        except Exception:
            pass

        # 策略2: 通用提取
        if not messages:
            messages = self._generic_message_extract(page)

        # 策略3: 全局状态
        if not messages:
            messages = self._extract_from_state(page)

        # ChatGPT 经常有 system prompt 或重复内容，额外过滤
        cleaned = []
        seen = set()
        for msg in messages:
            c = msg.content.strip()
            # 过滤掉常见的 system 提示
            if c.startswith("You are ChatGPT") or c.startswith("You are a helpful"):
                continue
            if len(c) < 2 or c in seen:
                continue
            seen.add(c)
            cleaned.append(msg)

        return cleaned
