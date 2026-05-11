"""
登录状态管理模块（多平台支持）
负责：
- 按平台隔离的 Cookie/Storage 保存和加载
- 登录状态检测
- 首次登录时打开浏览器让用户手动登录（QoL: 自动点击登录按钮 + 自动检测关闭）
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

import playwright.sync_api as pw


class AuthManager:
    """管理各平台的登录状态。"""

    def __init__(self, platform: str = "kimi", state_dir: Optional[Path] = None):
        """
        Args:
            platform: 平台标识 (kimi/deepseek/chatgpt)
            state_dir: 存储认证状态的根目录，默认 ~/.kimireader/
        """
        self.platform = platform.lower().strip()
        if state_dir is None:
            state_dir = Path.home() / ".kimireader"
        self.state_dir = state_dir / self.platform
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.storage_state_file = self.state_dir / "storage_state.json"

    def is_logged_in(self, browser_type: str = "chromium", login_url: str = "") -> bool:
        """检测是否已保存有效登录状态。
        如果检测到无效状态，会自动清除 state 文件。"""
        if not self.storage_state_file.exists():
            return False

        # 检查文件是否为空
        try:
            stat = self.storage_state_file.stat()
            if stat.st_size < 10:
                self.storage_state_file.unlink()
                return False
        except Exception:
            return False

        url = login_url or self._get_default_login_url()
        result = False

        try:
            with pw.sync_playwright() as p:
                browser_cls = getattr(p, browser_type)
                browser = browser_cls.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(self.storage_state_file)
                )
                page = context.new_page()

                # 使用 load 等待页面加载，避免 networkidle 因 analytics 长连接超时
                try:
                    page.goto(url, wait_until="load", timeout=30000)
                except Exception:
                    pass
                page.wait_for_timeout(5000)  # 额外等待 JS 渲染

                # 通用登录检测：复用 _check_login_indicators（已包含 URL 严格检查）
                result = self._check_login_indicators(page)
                browser.close()
        except Exception as e:
            print(f"[{self.platform}] Login check warning: {e}")
            result = False

        # 如果检测失败，自动清理无效的 state 文件，避免用户卡住
        if not result:
            try:
                if self.storage_state_file.exists():
                    self.storage_state_file.unlink()
                    print(f"[{self.platform}] 检测到无效登录状态，已自动清理。")
            except Exception:
                pass

        return result

    def login_interactive(self, browser_type: str = "chromium", login_url: str = "",
                          platform_name: str = ""):
        """
        打开有界面的浏览器，自动点击登录按钮，并在登录成功后自动关闭。
        """
        platform_display = platform_name or self.platform
        url = login_url or self._get_default_login_url()

        print("=" * 60)
        print(f"KimiReader 登录 - {platform_display}")
        print("=" * 60)
        print(f"正在打开 {url} ...")
        print("系统将自动点击登录按钮，请在新窗口中完成扫码或密码登录。")
        print("登录成功后浏览器会自动关闭。")
        print("=" * 60)

        with pw.sync_playwright() as p:
            browser_cls = getattr(p, browser_type)
            # 反检测参数：隐藏自动化特征，降低被 Cloudflare 检测概率
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
            browser = browser_cls.launch(
                headless=False,
                args=launch_args,
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            # 注入脚本移除 webdriver 标志
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # QoL: 自动点击登录按钮
            self._auto_click_login_button(page)

            # QoL: 自动检测登录成功并关闭
            self._wait_for_login_and_close(page, browser, context)

        print("登录状态已保存。")

    def _auto_click_login_button(self, page: pw.Page):
        """自动检测并点击页面上的登录按钮。支持多次尝试（处理折叠菜单）。"""
        # 先等待页面完全渲染（Kimi 新 UI 可能慢）
        page.wait_for_timeout(3000)

        login_selectors = [
            # 文字按钮（中文优先）
            'button:has-text("登录")',
            'button:has-text("登 录")',
            'a:has-text("登录")',
            'div:has-text("登录"):visible',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("立即登录")',
            'a:has-text("Log in")',
            'a:has-text("Login")',
            'a:has-text("Sign in")',
            # class / data-testid
            '[class*="login"]',
            '[class*="signin"]',
            '[class*="sign-in"]',
            '[data-testid*="login"]',
            # 位置（header/nav/右上角常见区域）
            'header [class*="login"]',
            'nav [class*="login"]',
            'header button',
            'header a',
            '[class*="header"] button',
            '[class*="top-bar"] button',
            # SVG 图标旁的登录（Kimi 新 UI 可能用图标）
            'button:has(svg):has-text("登录")',
            'button:has(svg):has-text("Log")',
            'a:has(svg):has-text("登录")',
        ]

        # 第一轮：直接匹配可见的登录按钮
        for selector in login_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    print("已自动点击登录按钮，请完成登录...")
                    page.wait_for_timeout(2000)
                    return
            except Exception:
                continue

        # 第二轮：尝试点击可能是头像/用户菜单的按钮（有些 UI 登录在折叠菜单里）
        menu_selectors = [
            '[class*="avatar"]',
            '[class*="user-menu"]',
            'header img',
            'nav img',
            'button:has(img)',
            '[class*="profile"]',
        ]
        for selector in menu_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1500):
                    btn.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    # 点击后看看有没有弹出登录选项
                    for login_sel in login_selectors:
                        try:
                            login_btn = page.locator(login_sel).first
                            if login_btn.is_visible(timeout=1500):
                                login_btn.click(timeout=5000)
                                print("已通过菜单弹出登录选项...")
                                return
                        except Exception:
                            continue
            except Exception:
                continue

        print("未检测到登录按钮，如果页面已显示登录表单，请直接操作。")

    def _wait_for_login_and_close(self, page: pw.Page, browser, context,
                                   timeout_seconds: int = 120):
        """轮询检测登录状态，登录成功后自动关闭浏览器。
        包含二次验证，防止在登录跳转页误判。"""
        start_time = time.time()
        check_interval = 2.0
        last_status = ""
        login_success = False
        consecutive_success = 0

        try:
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    print(f"\n登录检测超时（{timeout_seconds}秒）。")
                    break

                is_logged_in = self._check_login_indicators(page)

                if is_logged_in:
                    # 二次验证：连续 2 次检测都成功才算真的登录成功
                    # 防止登录跳转页的瞬态误判
                    consecutive_success += 1
                    if consecutive_success >= 2:
                        # 最终确认：URL 不在登录页，且页面没有未登录提示
                        current_url = page.url.lower()
                        if any(p in current_url for p in ["/login", "/auth", "/signin", "/sso", "/passport"]):
                            consecutive_success = 0
                            continue
                        try:
                            page_text = page.locator("body").inner_text(timeout=2000)
                            if "登录以同步" in page_text or "登录以继续" in page_text or "请登录" in page_text:
                                consecutive_success = 0
                                continue
                        except Exception:
                            pass

                        login_success = True
                        print("\n检测到登录成功！等待状态稳定...")
                        page.wait_for_timeout(5000)
                        break
                else:
                    consecutive_success = 0

                status = f"等待登录中... ({int(elapsed)}s/{timeout_seconds}s)"
                if status != last_status:
                    print(status, end="\r", flush=True)
                    last_status = status

                if page.is_closed():
                    print("\n浏览器已被手动关闭。")
                    break

                page.wait_for_timeout(int(check_interval * 1000))

        except Exception as e:
            print(f"\n检测过程出错: {e}")
        finally:
            # 保存 storage state
            try:
                if login_success:
                    print("等待 cookie 同步...")
                    page.wait_for_timeout(8000)
                context.storage_state(path=str(self.storage_state_file))
                print("登录状态已保存。")
            except Exception as e:
                print(f"保存登录状态时出错: {e}")
            try:
                browser.close()
            except Exception:
                pass

    def _check_login_indicators(self, page: pw.Page) -> bool:
        """综合多种指标判断当前页面是否已登录。
        严格防止在登录跳转页误判（Kimi/ChatGPT 常见问题）。"""
        try:
            url = page.url
            url_lower = url.lower()

            # ========== 严格排除：如果 URL 明显是登录/认证页 ==========
            login_paths = ["/login", "/auth", "/signin", "/sso", "/passport", "/sign-up", "/register"]
            login_hosts = ["auth.", "passport.", "login.", "account.", "sso."]
            if any(p in url_lower for p in login_paths):
                return False
            if any(h in url_lower for h in login_hosts):
                return False

            # ========== 严格排除：页面有明显"未登录"提示 ==========
            try:
                page_text = page.locator("body").inner_text(timeout=2000)
            except Exception:
                page_text = ""

            not_logged_markers = [
                "登录以同步", "登录以继续", "请登录", "登录后",
                "sign in to", "log in to", "please sign in",
                "登录/注册", "登录账号", "扫码登录", "手机号登录",
            ]
            if any(m in page_text for m in not_logged_markers):
                return False

            # ========== 严格排除：有登录按钮且没有用户头像 ==========
            has_login_btn = page.locator(
                'button:has-text("登录"), a:has-text("登录"), '
                'button:has-text("Log in"), a:has-text("Log in"), '
                'button:has-text("Sign in"), a:has-text("Sign in"), '
                '[class*="login-btn"], [class*="login-button"]'
            ).count() > 0
            has_user_avatar = page.locator(
                '[class*="avatar"], img[alt*="avatar"], img[alt*="User"], '
                '[class*="user-menu"], [class*="profile"]'
            ).count() > 0
            if has_login_btn and not has_user_avatar:
                return False

            # ========== 正向检测1：localStorage / sessionStorage 中的有效 token ==========
            token = page.evaluate(
                "() => {"
                "  const keys = ['token','access_token','refresh_token','jwt','auth_token',"
                "    'user_token','api_key','credential','ds_token','ds_auth'];"
                "  for (const k of keys) {"
                "    const v = localStorage.getItem(k) || sessionStorage.getItem(k);"
                "    if (v && v.length > 20) return v;"
                "  }"
                "  return '';"
                "}"
            )
            if token and len(str(token)) > 20:
                return True

            # ========== 正向检测2：document.cookie 中的有效会话 cookie ==========
            # 改进：不再简单 includes，而是解析具体 cookie 名和值长度
            has_real_session = page.evaluate(
                "() => {"
                "  const cookies = document.cookie.split(';');"
                "  for (const c of cookies) {"
                "    const idx = c.indexOf('=');"
                "    if (idx < 0) continue;"
                "    const name = c.slice(0, idx).trim().toLowerCase();"
                "    const value = c.slice(idx + 1).trim();"
                "    if (value.length < 16) continue;"
                "    if (name.includes('cf_') || name.includes('_cfr') || name.includes('csrftoken')) continue;"
                "    if (name.includes('session') || name.includes('token') || name.includes('auth')) return true;"
                "  }"
                "  return false;"
                "}"
            )
            if has_real_session:
                return True

            # ========== 正向检测3：用户相关 DOM 元素 ==========
            has_user = page.locator(
                '[class*="avatar"], [class*="user-name"], [class*="profile"], '
                'img[alt*="头像"], img[alt*="avatar"], img[alt*="User"], '
                '[class*="logout"], button:has-text("退出"), button:has-text("Log out"), '
                '[class*="account"], [class*="user-menu"]'
            ).count() > 0
            if has_user:
                return True

            # ========== 正向检测4：有聊天输入框且没有登录按钮 ==========
            has_chat_ui = page.locator(
                '[class*="chat-input"], [class*="message-input"], '
                'textarea[placeholder], [class*="conversation-list"], '
                '[class*="new-chat"], button:has-text("New chat")'
            ).count() > 0
            if has_chat_ui and not has_login_btn:
                return True

            # ========== 正向检测5：页面包含已登录特有的文本 ==========
            page_text_lower = page_text.lower()
            logged_in_markers = [
                "new chat", "new conversation", "start chat",
                "退出", "log out", "logout", "settings", "设置",
            ]
            if any(m in page_text_lower for m in logged_in_markers):
                if not has_login_btn:
                    return True

            return False
        except Exception:
            return False

    def ensure_login(self, browser_type: str = "chromium", force_relogin: bool = False,
                     login_url: str = "", platform_name: str = ""):
        """确保已登录。"""
        if not force_relogin and self.is_logged_in(browser_type, login_url):
            print(f"[{self.platform}] 已检测到有效登录状态。")
            return

        if force_relogin:
            print(f"[{self.platform}] 强制重新登录...")
        else:
            print(f"[{self.platform}] 未检测到登录状态，需要手动登录。")

        self.login_interactive(browser_type, login_url, platform_name)

    def get_context_args(self) -> dict:
        """返回用于创建 browser context 的参数。"""
        args = {}
        if self.storage_state_file.exists():
            args["storage_state"] = str(self.storage_state_file)
        return args

    def logout(self):
        """清除保存的登录状态。"""
        if self.storage_state_file.exists():
            self.storage_state_file.unlink()
        print(f"[{self.platform}] 已清除登录状态。")

    def get_status(self) -> dict:
        """返回当前认证状态的摘要信息。"""
        return {
            "platform": self.platform,
            "state_dir": str(self.state_dir),
            "has_storage_state": self.storage_state_file.exists(),
            "is_logged_in": self.is_logged_in(),
        }

    def _get_default_login_url(self) -> str:
        """根据平台返回默认登录URL。"""
        urls = {
            "kimi": "https://www.kimi.com",
            "deepseek": "https://chat.deepseek.com",
            "chatgpt": "https://chatgpt.com",
        }
        return urls.get(self.platform, f"https://{self.platform}.com")
