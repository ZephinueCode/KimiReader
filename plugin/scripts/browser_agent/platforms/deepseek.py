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
        # DeepSeek 侧边栏可能是普通的 div，通过包含大量 a[href*="/a/chat/s/"] 来识别
        'div:has(> a[href*="/a/chat/s/"])',
        'div:has(a[href*="/a/chat/s/"])',
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
    session_url_template = "/a/chat/s/{session_id}"

    def extract_sessions_from_dom(self, page: pw.Page, max_sessions: int = 30) -> List[ChatSession]:
        """DeepSeek 特定的 DOM 提取：通过 JS 遍历，不依赖哈希 class。"""
        sessions = []
        seen_ids = set()
        import re

        # 调试：先看看页面上有多少符合条件的链接
        link_count = page.evaluate("""() => document.querySelectorAll('a[href*="/a/chat/s/"]').length""")
        print(f"[deepseek] Found {link_count} sidebar links with href pattern", flush=True)

        # 调试：打印第一个匹配的 a 标签的 outerHTML（用于确认结构）
        if link_count > 0:
            sample_html = page.evaluate("""
                () => {
                    const a = document.querySelector('a[href*="/a/chat/s/"]');
                    return a ? a.outerHTML.substring(0, 500) : 'none';
                }
            """)
            print(f"[deepseek] Sample link HTML: {sample_html}", flush=True)

        try:
            raw_data = page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href*="/a/chat/s/"]');
                    return Array.from(links).map(a => {
                        const href = a.getAttribute('href') || '';
                        // 找标题：遍历子 div，排除含 SVG 的、按钮类的，取第一个有意义的文本
                        const divs = a.querySelectorAll('div');
                        let title = '';
                        for (const div of divs) {
                            const text = div.innerText.trim();
                            // 过滤条件：长度合理、不包含 SVG 坐标数据、不是按钮
                            if (text.length > 2 && text.length < 200 &&
                                !text.includes('M4.') &&
                                !div.querySelector('svg') &&
                                !div.querySelector('button')) {
                                title = text;
                                break;
                            }
                        }
                        // fallback: 直接取 a 标签的纯文本（去掉子元素后）
                        if (!title) {
                            const clone = a.cloneNode(true);
                            // 移除 svg 和 button 区域
                            clone.querySelectorAll('svg, button, [role="button"]').forEach(el => el.remove());
                            title = clone.innerText.trim().substring(0, 200);
                        }
                        return { href, title };
                    }).filter(x => x.title);
                }
            """)

            print(f"[deepseek] JS extracted {len(raw_data)} raw items", flush=True)
            for item in raw_data[:3]:
                print(f"  raw: href={item.get('href','')[:40]} title={item.get('title','')[:50]}", flush=True)

            for item in raw_data:
                href = item.get("href", "")
                title = item.get("title", "")
                match = re.search(r"/a/chat/s/([a-f0-9-]+)", href)
                sid = match.group(1) if match else ""
                url = f"https://{self.domain}{href}" if href.startswith("/") else href

                if sid and title and len(title) > 0 and sid not in seen_ids:
                    seen_ids.add(sid)
                    sessions.append(ChatSession(
                        session_id=sid,
                        title=title,
                        url=url,
                    ))
        except Exception as e:
            print(f"[deepseek] DOM extract error: {e}", flush=True)

        print(f"[deepseek] Final sessions from DOM: {len(sessions)}", flush=True)
        if not sessions:
            print(f"[deepseek] Falling back to base extract_sessions_from_dom", flush=True)
            sessions = super().extract_sessions_from_dom(page, max_sessions)

        return sessions[:max_sessions]

    def extract_messages(self, page: pw.Page) -> List[ChatMessage]:
        """DeepSeek 消息提取：处理虚拟列表 + ds-message 语义 class。"""
        messages = []

        # 步骤1：滚动加载所有消息（DeepSeek 使用虚拟列表，只渲染可见区域）
        print("[deepseek] Scrolling to load all messages in virtual list...", flush=True)
        self._scroll_to_load_all_messages(page)

        # 步骤2：通过 JS 提取所有 ds-message 元素
        try:
            raw_messages = page.evaluate("""
                () => {
                    const results = [];
                    const msgElements = document.querySelectorAll('.ds-message');
                    
                    for (const msgEl of msgElements) {
                        // 判断角色：有 assistant-message-main-content 或 think-content 的是 AI
                        let role = 'unknown';
                        const hasAssistant = msgEl.querySelector('.ds-assistant-message-main-content, [class*="assistant-message"]');
                        const hasThink = msgEl.querySelector('.ds-think-content, [class*="think-content"]');
                        
                        if (hasAssistant || hasThink) {
                            role = 'assistant';
                        } else {
                            role = 'user';
                        }
                        
                        let content = '';
                        if (role === 'assistant') {
                            // AI 消息：优先提取 assistant-message-main-content（实际回复，不含思考过程）
                            const contentEl = msgEl.querySelector('.ds-assistant-message-main-content');
                            if (contentEl) {
                                content = contentEl.innerText.trim();
                            } else {
                                // fallback: 整个消息文本，排除 think-content
                                const clone = msgEl.cloneNode(true);
                                clone.querySelectorAll('.ds-think-content, [class*="think"]').forEach(el => el.remove());
                                content = clone.innerText.trim();
                            }
                        } else {
                            // 用户消息：clone 后移除按钮/SVG/图标
                            const clone = msgEl.cloneNode(true);
                            clone.querySelectorAll('svg, button, [role="button"], .ds-icon, .ds-icon-button, .ds-focus-ring').forEach(el => el.remove());
                            content = clone.innerText.trim();
                        }
                        
                        // 过滤掉太短的或纯空格的内容
                        if (content.length > 0) {
                            results.push({role, content});
                        }
                    }
                    return results;
                }
            """)

            print(f"[deepseek] Extracted {len(raw_messages)} messages from DOM", flush=True)
            for item in raw_messages:
                if item.get("content"):
                    messages.append(ChatMessage(role=item["role"], content=item["content"]))
        except Exception as e:
            print(f"[deepseek] Message extract error: {e}", flush=True)

        # 去重
        seen = set()
        cleaned = []
        for msg in messages:
            key = msg.role + "|" + msg.content[:100]
            if key not in seen:
                seen.add(key)
                cleaned.append(msg)

        if not cleaned:
            print("[deepseek] Falling back to generic extract...", flush=True)
            cleaned = self._generic_message_extract(page)

        if not cleaned:
            print("[deepseek] Falling back to state extract...", flush=True)
            cleaned = self._extract_from_state(page)

        return cleaned

    def _scroll_to_load_all_messages(self, page: pw.Page, max_scrolls: int = 30):
        """DeepSeek 虚拟列表需要多次滚动才能加载全部消息。"""
        for i in range(max_scrolls):
            before_count = page.evaluate("""() => document.querySelectorAll('.ds-message').length""")
            # 尝试多种滚动方式
            page.evaluate("""
                () => {
                    // 方式1：找到虚拟列表的滚动容器
                    const virtualList = document.querySelector('.ds-virtual-list-visible-items');
                    if (virtualList) {
                        const container = virtualList.parentElement;
                        if (container && container.scrollHeight > container.clientHeight) {
                            container.scrollTo(0, container.scrollHeight);
                            return;
                        }
                    }
                    // 方式2：找 main 区域
                    const main = document.querySelector('main');
                    if (main && main.scrollHeight > main.clientHeight) {
                        main.scrollTo(0, main.scrollHeight);
                        return;
                    }
                    // 方式3：window 滚动
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)
            page.wait_for_timeout(1200)
            after_count = page.evaluate("""() => document.querySelectorAll('.ds-message').length""")
            if after_count <= before_count:
                print(f"[deepseek] Scroll complete after {i+1} scrolls, {after_count} messages total", flush=True)
                break
        else:
            final_count = page.evaluate("""() => document.querySelectorAll('.ds-message').length""")
            print(f"[deepseek] Scroll maxed out, {final_count} messages total", flush=True)
