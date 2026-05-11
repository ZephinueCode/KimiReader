---
name: 导入聊天记录
description: 从网页版Kimi自动拉取指定对话的聊天记录，支持登录管理和对话选择
---

# 导入聊天记录

从网页版Kimi（kimi.moonshot.cn）自动拉取聊天记录到当前对话上下文。

## 使用流程

### 步骤1：检查登录状态

调用 `kimi_login_status` 检查是否已保存有效的登录状态。

### 步骤2：登录（如需要）

如果未登录，调用 `kimi_login` 打开浏览器窗口。用户需要：
1. 在打开的浏览器中访问 kimi.moonshot.cn
2. 完成登录（扫码/密码/手机号等方式）
3. 关闭浏览器窗口

登录状态会自动保存到 `~/.kimireader/`，后续无需重复登录。

### 步骤3：列出历史对话

调用 `list_chat_sessions` 获取网页版上的历史对话列表。

### 步骤4：导入指定对话

使用 `import_chat_history` 导入对话。可以通过以下方式指定：
- `index`: 从list结果中的序号（最推荐，如 `index: 0` 表示第一个对话）
- `session_id`: 会话ID
- `url`: 完整URL

### 步骤5：展示结果

将导入的聊天记录 `full_text` 展示给用户，或启动子Agent进行进一步分析。

## 快捷命令

在 Kimi Code CLI 或 VSCode Kimi Code 中输入：

```
/skill:导入聊天记录
```

或带参数指定对话：

```
/skill:导入聊天记录 导入最新的对话
/skill:导入聊天记录 导入第2个对话
```

## 注意事项

- 首次使用必须先登录
- 登录状态通常持久数月，但cookie过期后需要重新登录
- 导入的长对话会占用上下文token，建议对过长的对话先做筛选
- 如果网页版DOM结构大幅变更，可能需要更新browser_agent模块
