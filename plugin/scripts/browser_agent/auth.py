"""
登录状态管理模块
负责：
- Cookie的保存和加载
- 登录状态检测
- 首次登录时打开浏览器让用户手动登录
"""

import json
import os
from pathlib import Path
from typing import Optional

import playwright.sync_api as pw


class AuthManager:
    """管理Kimi网页版的登录状态。"""

    KIMI_DOMAIN = "kimi.moonshot.cn"
    LOGIN_URL = "https://kimi.moonshot.cn"

    def __init__(self, state_dir: Optional[Path] = None):
        """
        Args:
            state_dir: 存储认证状态的目录，默认使用用户主目录下的 .kimireader/
        """
        if state_dir is None:
            state_dir = Path.home() / ".kimireader"
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file = self.state_dir / "cookies.json"
        self.storage_state_file = self.state_dir / "storage_state.json"

    def is_logged_in(self, browser_type: str = "chromium") -> bool:
        """检测是否已保存有效登录状态。"""
        if not self.storage_state_file.exists():
            return False

        # 尝试用storage state打开一个无痕页面验证
        try:
            with pw.sync_playwright() as p:
                browser_cls = getattr(p, browser_type)
                browser = browser_cls.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(self.storage_state_file)
                )
                page = context.new_page()
                page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)

                # 检测登录状态：未登录通常会重定向到登录页或显示登录按钮
                # 已登录则能看到聊天界面或用户头像
                url = page.url
                if "/login" in url or "/auth" in url:
                    browser.close()
                    return False

                # 检查是否有用户相关元素（如头像、用户名、设置按钮等）
                has_user_indicator = page.locator(
                    '[class*="avatar"], [class*="user"], [class*="profile"], '
                    'img[alt*="头像"], button:has-text("退出"), [class*="logout"]'
                ).count() > 0

                # 也检查localStorage中是否有token
                token = page.evaluate("() => localStorage.getItem('token') || localStorage.getItem('access_token') || sessionStorage.getItem('token') || ''")

                browser.close()
                return has_user_indicator or bool(token)
        except Exception:
            return False

    def login_interactive(self, browser_type: str = "chromium"):
        """
        打开有界面的浏览器，自动点击登录按钮，并在登录成功后自动关闭。
        QoL优化：自动触发登录流程，用户只需完成扫码/输密码，无需手动找登录入口。
        """
        print("=" * 60)
        print("KimiReader 登录")
        print("=" * 60)
        print(f"正在打开浏览器...")
        print("系统将自动点击登录按钮，请在新窗口中完成扫码或密码登录。")
        print("登录成功后浏览器会自动关闭。")
        print("=" * 60)

        with pw.sync_playwright() as p:
            browser_cls = getattr(p, browser_type)
            browser = browser_cls.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # QoL 1: 自动点击登录按钮（如果存在）
            self._auto_click_login_button(page)

            # QoL 2: 自动检测登录成功并关闭浏览器
            self._wait_for_login_and_close(page, browser, context)

        print("登录状态已保存。")

    def _auto_click_login_button(self, page: pw.Page):
        """自动检测并点击页面上的登录按钮。"""
        login_button_selectors = [
            # 通过文本内容匹配（中英文常见写法）
            'button:has-text("登录")',
            'button:has-text("登入")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("立即登录")',
            'a:has-text("登录")',
            'a:has-text("登入")',
            'a:has-text("Login")',
            'a:has-text("Sign in")',
            'div:has-text("登录"):visible',
            # 通过 class/name 特征匹配
            '[class*="login"]',
            '[class*="signin"]',
            '[class*="sign-in"]',
            'button[type="button"]:has-text("登录")',
            # 右上角/导航栏常见的登录入口
            'header [class*="login"]',
            'nav [class*="login"]',
        ]

        for selector in login_button_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1500):
                    btn.click(timeout=5000)
                    print("已自动点击登录按钮，请完成登录...")
                    page.wait_for_timeout(2000)  # 等待登录弹窗/页面出现
                    return
            except Exception:
                continue

        print("未检测到登录按钮，如果页面已显示登录表单，请直接操作。")

    def _wait_for_login_and_close(self, page: pw.Page, browser, context,
                                   timeout_seconds: int = 120):
        """
        轮询检测登录状态，登录成功后自动关闭浏览器。
        检测指标：URL变化、token出现、用户头像出现、登录按钮消失。
        """
        import time
        start_time = time.time()
        check_interval = 2.0  # 每2秒检查一次
        last_status = ""

        try:
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    print(f"\n登录检测超时（{timeout_seconds}秒）。")
                    print("将保存当前页面状态，如果已登录则可用，否则请重新运行登录。")
                    break

                # 多种指标综合判断登录状态
                is_logged_in = self._check_login_indicators(page)

                if is_logged_in:
                    print("\n检测到登录成功！正在保存状态并关闭浏览器...")
                    # 再稍等片刻让cookie等状态稳定
                    page.wait_for_timeout(2000)
                    break

                # 打印状态更新（避免用户觉得卡死）
                status = f"等待登录中... ({int(elapsed)}s/{timeout_seconds}s)"
                if status != last_status:
                    print(status, end="\r", flush=True)
                    last_status = status

                # 检查浏览器是否已被用户手动关闭
                if page.is_closed():
                    print("\n浏览器已被手动关闭。")
                    break

                page.wait_for_timeout(int(check_interval * 1000))

        except Exception as e:
            print(f"\n检测过程出错: {e}")
        finally:
            # 无论是否检测到登录成功，都保存当前storage state
            # 因为用户可能已经登录了但检测逻辑没命中
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
            # 指标1: URL 不在登录相关路径
            url = page.url
            if "/login" in url or "/auth" in url:
                return False

            # 指标2: localStorage / sessionStorage 中有 token
            token = page.evaluate(
                "() => localStorage.getItem('token') || "
                "localStorage.getItem('access_token') || "
                "sessionStorage.getItem('token') || "
                "localStorage.getItem('refresh_token') || ''"
            )
            if token and len(str(token)) > 10:
                return True

            # 指标3: 页面上出现用户头像/用户名/退出按钮
            has_user_element = page.locator(
                '[class*="avatar"], [class*="user-name"], [class*="profile"], '
                'img[alt*="头像"], [class*="logout"], button:has-text("退出")'
            ).count() > 0
            if has_user_element:
                return True

            # 指标4: 页面主内容区出现对话列表或输入框（已登录特征）
            has_chat_ui = page.locator(
                '[class*="chat-input"], [class*="message-input"], '
                'textarea[placeholder], [class*="conversation-list"]'
            ).count() > 0
            # 但同时要确认没有登录按钮
            has_login_button = page.locator(
                'button:has-text("登录"), a:has-text("登录"), [class*="login-btn"]'
            ).count() > 0
            if has_chat_ui and not has_login_button:
                return True

            return False
        except Exception:
            return False

    def ensure_login(self, browser_type: str = "chromium", force_relogin: bool = False):
        """
        确保已登录。如果未登录或force_relogin=True，则触发交互式登录。
        """
        if not force_relogin and self.is_logged_in(browser_type):
            print("已检测到有效登录状态。")
            return

        if force_relogin:
            print("强制重新登录...")
        else:
            print("未检测到登录状态，需要手动登录。")

        self.login_interactive(browser_type)

    def get_context_args(self) -> dict:
        """返回用于创建browser context的参数（包含登录状态）。"""
        args = {}
        if self.storage_state_file.exists():
            args["storage_state"] = str(self.storage_state_file)
        return args

    def logout(self):
        """清除保存的登录状态。"""
        for f in [self.cookie_file, self.storage_state_file]:
            if f.exists():
                f.unlink()
        print("已清除登录状态。")

    def get_status(self) -> dict:
        """返回当前认证状态的摘要信息。"""
        return {
            "state_dir": str(self.state_dir),
            "has_cookies": self.cookie_file.exists(),
            "has_storage_state": self.storage_state_file.exists(),
            "is_logged_in": self.is_logged_in(),
        }
