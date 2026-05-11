"""
多平台支持模块
支持: kimi (kimi.moonshot.cn), deepseek (chat.deepseek.com), chatgpt (chatgpt.com)
"""

from .base import BasePlatform
from .kimi import KimiPlatform
from .deepseek import DeepSeekPlatform
from .chatgpt import ChatGPTPlatform

PLATFORMS = {
    "kimi": KimiPlatform,
    "deepseek": DeepSeekPlatform,
    "chatgpt": ChatGPTPlatform,
}


def get_platform(name: str) -> BasePlatform:
    """获取指定平台的实例。"""
    name = name.lower().strip()
    if name not in PLATFORMS:
        raise ValueError(f"Unknown platform: {name}. Supported: {', '.join(PLATFORMS.keys())}")
    return PLATFORMS[name]()
