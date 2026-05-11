"""
KimiReader Browser Agent
使用Playwright自动化kimi.moonshot.cn的聊天记录提取。
"""

from .auth import AuthManager
from .extractor import ChatExtractor

__all__ = ["AuthManager", "ChatExtractor"]
