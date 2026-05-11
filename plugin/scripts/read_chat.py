#!/usr/bin/env python3
"""
KimiReader Plugin - Chat History Reader
读取从网页版Kimi导出的聊天记录文件，支持JSON和Markdown格式。
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime


def find_chat_files():
    """在常见位置查找聊天记录文件。"""
    candidates = []
    
    # 搜索路径：Downloads、桌面、当前工作目录、用户主目录
    search_dirs = [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path.home() / "桌面",
        Path.cwd(),
        Path.home(),
    ]
    
    # 常见文件名模式
    patterns = [
        "kimi_chat_*.json",
        "kimi_chat_*.md",
        "kimi_export_*.json",
        "kimi_export_*.md",
        "chat_history*.json",
        "chat_history*.md",
    ]
    
    for directory in search_dirs:
        if not directory.exists():
            continue
        for pattern in patterns:
            for file_path in directory.glob(pattern):
                if file_path.is_file():
                    stat = file_path.stat()
                    candidates.append({
                        "path": str(file_path),
                        "name": file_path.name,
                        "size": stat.st_size,
                        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
    
    # 按修改时间倒序
    candidates.sort(key=lambda x: x["mtime"], reverse=True)
    return candidates


def read_json_chat(file_path):
    """读取JSON格式的聊天记录。"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 支持多种JSON结构
    messages = []
    
    if isinstance(data, list):
        # 直接是消息列表
        for item in data:
            if isinstance(item, dict):
                role = item.get("role", item.get("sender", "unknown"))
                content = item.get("content", item.get("text", item.get("message", "")))
                if content:
                    messages.append({"role": role, "content": content})
    elif isinstance(data, dict):
        # 可能是包装对象
        if "messages" in data:
            for item in data["messages"]:
                role = item.get("role", item.get("sender", "unknown"))
                content = item.get("content", item.get("text", item.get("message", "")))
                if content:
                    messages.append({"role": role, "content": content})
        elif "data" in data:
            return read_json_chat_from_raw(data["data"])
    
    return {
        "format": "json",
        "title": data.get("title", Path(file_path).stem) if isinstance(data, dict) else Path(file_path).stem,
        "messages": messages,
        "message_count": len(messages),
    }


def read_json_chat_from_raw(data):
    """从原始数据结构解析。"""
    messages = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                role = item.get("role", item.get("sender", "unknown"))
                content = item.get("content", item.get("text", item.get("message", "")))
                if content:
                    messages.append({"role": role, "content": content})
    return {
        "format": "json",
        "title": "exported_chat",
        "messages": messages,
        "message_count": len(messages),
    }


def read_markdown_chat(file_path):
    """读取Markdown格式的聊天记录。"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    lines = content.split("\n")
    messages = []
    current_role = None
    current_content = []
    
    for line in lines:
        stripped = line.strip()
        
        # 检测角色标题：## User / ## Assistant / ## Kimi / ## 用户 / ## 助手
        if stripped.startswith("## ") or stripped.startswith("### "):
            if current_role and current_content:
                messages.append({
                    "role": current_role,
                    "content": "\n".join(current_content).strip()
                })
            
            header = stripped.lstrip("# ")
            header_lower = header.lower()
            if any(x in header_lower for x in ["user", "用户", "human", "我"]):
                current_role = "user"
            elif any(x in header_lower for x in ["assistant", "助手", "kimi", "ai", "model"]):
                current_role = "assistant"
            else:
                current_role = header
            
            current_content = []
        elif stripped.startswith("---") or stripped.startswith("***"):
            # 分隔线，保存当前消息
            if current_role and current_content:
                messages.append({
                    "role": current_role,
                    "content": "\n".join(current_content).strip()
                })
                current_role = None
                current_content = []
        else:
            if current_role is not None:
                current_content.append(line)
    
    # 保存最后一条消息
    if current_role and current_content:
        messages.append({
            "role": current_role,
            "content": "\n".join(current_content).strip()
        })
    
    return {
        "format": "markdown",
        "title": Path(file_path).stem,
        "messages": messages,
        "message_count": len(messages),
    }


def read_chat_file(file_path):
    """读取聊天记录文件，自动检测格式。"""
    path = Path(file_path)
    
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    
    suffix = path.suffix.lower()
    
    try:
        if suffix == ".json":
            return read_json_chat(file_path)
        elif suffix in (".md", ".markdown"):
            return read_markdown_chat(file_path)
        else:
            # 尝试JSON，失败则按Markdown处理
            try:
                return read_json_chat(file_path)
            except json.JSONDecodeError:
                return read_markdown_chat(file_path)
    except Exception as e:
        return {"error": str(e)}


def main():
    params = json.load(sys.stdin)
    action = params.get("action", "read")
    
    if action == "list":
        files = find_chat_files()
        result = {
            "files": files,
            "count": len(files),
            "note": "Found recent chat export files. Use 'read' action with a file_path to load one."
        }
    elif action == "read":
        file_path = params.get("file_path", "")
        if not file_path:
            # 如果没有指定路径，尝试找到最新的
            files = find_chat_files()
            if files:
                file_path = files[0]["path"]
            else:
                result = {
                    "error": "No file_path provided and no chat files found in common locations."
                }
                print(json.dumps(result, ensure_ascii=False))
                return
        
        result = read_chat_file(file_path)
        if "error" not in result:
            # 将消息拼接为完整文本，方便直接阅读
            full_text = []
            for msg in result.get("messages", []):
                role = msg["role"]
                content = msg["content"]
                full_text.append(f"**{role}**: {content}")
            result["full_text"] = "\n\n".join(full_text)
    else:
        result = {"error": f"Unknown action: {action}. Supported: list, read"}
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
