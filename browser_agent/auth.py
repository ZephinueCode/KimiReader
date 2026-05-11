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
        """检测是否已保存有效登录状态。"""
        if not self.storage_state_file.exists():
            return False

        url = login_url or self._get_default_login_url()

        try:
            with pw.sync_playwright() as p:
                browser_cls = getattr(p, browser_type)
                browser = browser_cls.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(self.storage_state_file)
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)

                # 通用登录检测
                url_now = page.url
                if "/login" in url_now or "/auth" in url_now or "/signin" in url_now:
                    browser.close()
                    return False

                # 检查用户相关元素
                has_user = page.locator(
                    '[class*="avatar"], [class*="user"], [class*="profile"], '
                    'img[alt*="头像"], img[alt*="avatar"], img[alt*="User"], '
                    'button:has-text("退出"), button:has-text("Log out"), '
                    '[class*="logout"], [class*="account"]'
                ).count() > 0

                token = page.evaluate(
                    "() => localStorage.getItem('token') || "
                    "localStorage.getItem('access_token') || "
                    "sessionStorage.getItem('token') || "
                    "localStorage.getItem('refresh_token') || ''"
                )

                browser.close()
                return has_user or bool(token)
        except Exception:
            return False

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
            browser = browser_cls.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # QoL: 自动点击登录按钮
            self._auto_click_login_button(page)

            # QoL: 自动检测登录成功并关闭
            self._wait_for_login_and_close(page, browser, context)

        print("登录状态已保存。")

    def _auto_click_login_button(self, page: pw.Page):
        """自动检测并点击页面上的登录按钮。"""
        login_selectors = [
            'button:has-text("登录")',
            'button:has-text("Log in")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("立即登录")',
            'a:has-text("登录")',
            'a:has-text("Log in")',
            'a:has-text("Login")',
            'a:has-text("Sign in")',
            'div:has-text("登录"):visible',
            '[class*="login"]',
            '[class*="signin"]',
            '[class*="sign-in"]',
            '[data-testid*="login"]',
            'header [class*="login"]',
            'nav [class*="login"]',
        ]

        for selector in login_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1500):
                    btn.click(timeout=5000)
                    print("已自动点击登录按钮，请完成登录...")
                    page.wait_for_timeout(2000)
                    return
            except Exception:
                continue

        print("未检测到登录按钮，如果页面已显示登录表单，请直接操作。")

    def _wait_for_login_and_close(self, page: pw.Page, browser, context,
                                   timeout_seconds: int = 120):
        """轮询检测登录状态，登录成功后自动关闭浏览器。"""
        start_time = time.time()
        check_interval = 2.0
        last_status = ""

        try:
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    print(f"\n登录检测超时（{timeout_seconds}秒）。")
                    break

                is_logged_in = self._check_login_indicators(page)

                if is_logged_in:
                    print("\n检测到登录成功！正在保存状态并关闭浏览器...")
                    page.wait_for_timeout(2000)
                    break

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
            try:
                context.storage_state(path=str(self.storage_state_file))
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    def _check_login_indicators(self, page: pw.Page) -> bool:
        """综合多种指标判断当前页面是否已登录。"""
        try:
            url = page.url
            if "/login" in url or "/auth" in url or "/signin" in url:
                return False

            token = page.evaluate(
                "() => localStorage.getItem('token') || "
                "localStorage.getItem('access_token') || "
                "sessionStorage.getItem('token') || "
                "localStorage.getItem('refresh_token') || ''"
            )
            if token and len(str(token)) > 10:
                return True

            has_user = page.locator(
                '[class*="avatar"], [class*="user-name"], [class*="profile"], '
                'img[alt*="头像"], img[alt*="avatar"], img[alt*="User"], '
                '[class*="logout"], button:has-text("退出"), button:has-text("Log out"), '
                '[class*="account"]'
            ).count() > 0
            if has_user:
                return True

            has_chat_ui = page.locator(
                '[class*="chat-input"], [class*="message-input"], '
                'textarea[placeholder], [class*="conversation-list"]'
            ).count() > 0
            has_login_btn = page.locator(
                'button:has-text("登录"), a:has-text("登录"), '
                'button:has-text("Log in"), a:has-text("Log in"), '
                '[class*="login-btn"]'
            ).count() > 0
            if has_chat_ui and not has_login_btn:
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
            "kimi": "https://kimi.moonshot.cn",
            "deepseek": "https://chat.deepseek.com",
            "chatgpt": "https://chatgpt.com",
        }
        return urls.get(self.platform, f"https://{self.platform}.com")
