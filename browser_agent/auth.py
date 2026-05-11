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
        打开有界面的浏览器让用户手动登录，登录后保存状态。
        此方法会阻塞直到用户关闭浏览器。
        """
        print("=" * 60)
        print("KimiReader 登录")
        print("=" * 60)
        print(f"即将打开浏览器，请在 {self.LOGIN_URL} 完成登录。")
        print("登录成功后，请关闭浏览器窗口以继续。")
        print("=" * 60)

        with pw.sync_playwright() as p:
            browser_cls = getattr(p, browser_type)
            browser = browser_cls.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(self.LOGIN_URL)

            # 等待浏览器被用户关闭
            try:
                while True:
                    # 每秒检查一次浏览器是否还在
                    page.wait_for_timeout(1000)
                    # 如果页面关闭了，break
                    if page.is_closed():
                        break
            except Exception:
                pass
            finally:
                # 保存storage state（包含cookies、localStorage等）
                context.storage_state(path=str(self.storage_state_file))
                browser.close()

        print("浏览器已关闭，登录状态已保存。")

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
