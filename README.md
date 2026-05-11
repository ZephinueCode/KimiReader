# KimiReader

从网页版 **Kimi / DeepSeek / ChatGPT** 自动拉取聊天记录，总结并生成代码方案框架的 Kimi Code CLI 插件套件。

## 更新日志

- **2026-5-12 v0.3 Beta**：部分支持 DeepSeek 和 ChatGPT 多平台；修复 list_sessions 和登陆的部分 BUG
- **2026-5-12 v0.2 Beta**：支持读取更多聊天记录；修复中文乱码和编码问题
- **2026-5-11 v0.1 Beta**：支持基础功能

## 核心特性

- **三平台支持**：Kimi (kimi.moonshot.cn)、DeepSeek (chat.deepseek.com)、ChatGPT (chatgpt.com)
- **浏览器自动化**：基于 Playwright，自动点击登录按钮、保存 Cookie、后台拉取记录
- **自动检测关闭**：登录成功后浏览器自动关闭，无需手动操作
- **自动展开加载**：自动点击"全部聊天记录"并滚动加载，最多返回 30 条
- **VSCode 支持**：同时支持 Kimi Code CLI 命令行版和 VSCode 扩展版
- **一键导入**：通过 `/skill:导入聊天记录` 或 `/flow:chat-to-code` 触发全流程
- **代码方案生成**：自动启动子 Agent 总结需求，输出技术架构和实现步骤

## 项目结构

```
KimiReader/
├── browser_agent/              # Playwright 浏览器自动化核心
│   ├── auth.py                 # 多平台登录状态管理
│   ├── extractor.py            # 聊天记录提取
│   ├── platforms/              # 平台适配器
│   │   ├── base.py             # 平台抽象基类
│   │   ├── kimi.py             # Kimi 适配
│   │   ├── deepseek.py         # DeepSeek 适配
│   │   └── chatgpt.py          # ChatGPT 适配
│   └── requirements.txt
├── plugin/                     # Kimi Code CLI 插件
│   ├── plugin.json             # 声明 7 个工具（含 platform 参数）
│   └── scripts/
│       ├── kimireader_browser.py   # 浏览器自动化入口
│       └── read_chat.py            # 本地文件读取（兼容模式）
├── skill/
│   ├── chat-to-code/           # Flow Skill（全自动）
│   └── import-chat/            # 普通 Skill（手动/半自动）
├── install/
│   ├── install-windows.ps1
│   └── install-linux.sh
├── browser/                    # 浏览器端备用工具（书签/扩展）
└── README.md
```

## 快速开始

### 1. 安装

**Windows（PowerShell）：**

```powershell
.\install\install-windows.ps1
```

**Linux / macOS（Bash）：**

```bash
bash install/install-linux.sh
```

安装脚本会自动完成：检测 Python → 安装 Playwright → 下载 Chromium → 安装 CLI 插件 → 安装 Skills。

### 2. 首次登录

```
/skill:导入聊天记录
```

默认使用 **Kimi** 平台。如果未登录，系统会：
1. 自动打开浏览器访问对应平台
2. **自动点击登录按钮**
3. 你在弹出的表单/二维码中完成验证
4. **登录成功后浏览器自动关闭**，状态保存到 `~/.kimireader/kimi/`

### 3. 切换平台

所有工具都支持 `platform` 参数：

```
→ kimi_login (platform: "deepseek")        # 登录 DeepSeek
→ list_chat_sessions (platform: "chatgpt")  # 列出 ChatGPT 对话
→ import_chat_history (platform: "deepseek", index: 0)
```

各平台登录态**相互独立**，首次使用每个平台都需要分别登录一次。

### 4. 导入聊天记录

```
/skill:导入聊天记录
```

AI 会自动：检查登录 → 列出历史对话（自动展开+滚动加载）→ 让你选择 → 拉取完整记录。

### 5. 生成代码方案（全自动）

```
/flow:chat-to-code
```

自动完成：检查登录 → 列出并选择对话 → 导入记录 → 启动 `plan` 子 Agent 分析 → 生成方案 → 保存到 `docs/chat-to-code-plan.md`

## 插件工具说明

| 工具名 | 说明 |
|--------|------|
| `kimi_login_status` | 检查指定平台的登录状态 |
| `kimi_login` | 打开浏览器交互式登录（自动点击按钮+自动关闭） |
| `kimi_logout` | 清除指定平台的登录状态 |
| `list_chat_sessions` | 列出平台历史对话（自动展开，最多30条） |
| `import_chat_history` | 导入指定对话的完整聊天记录 |
| `list_chat_files` | （兼容模式）查找本地导出的聊天记录文件 |
| `read_chat_file` | （兼容模式）读取本地聊天记录文件 |

**所有工具均支持 `platform` 参数**：`kimi`（默认）/ `deepseek` / `chatgpt`

## VSCode 版本使用说明

VSCode 的 Kimi Code 扩展底层使用的是同一个 CLI，插件和 Skill 安装后在 VSCode 中同样可用。

在 VSCode 的 Kimi Code 聊天面板中直接输入：

```
/flow:chat-to-code
```

或

```
/skill:导入聊天记录
```

## 手动调用示例

```bash
# 检查 Kimi 登录状态
→ kimi_login_status

# 登录 DeepSeek
→ kimi_login (platform: "deepseek")

# 列出 ChatGPT 历史对话
→ list_chat_sessions (platform: "chatgpt")

# 导入 DeepSeek 第0个对话
→ import_chat_history (platform: "deepseek", index: 0)

# 半自动模式：先列出，再导入
→ list_chat_sessions (platform: "kimi")
→ import_chat_history (platform: "kimi", index: 2)
```

## 浏览器端备用方案

如果浏览器自动化因网络/环境原因无法使用，还提供了：

- **书签脚本**：`browser/bookmarklet.js`，复制 minified 代码到浏览器书签栏
- **浏览器扩展**：`browser/extension/`，支持 Chrome/Edge

这两个工具将网页版聊天记录导出为 JSON 文件，然后通过 `list_chat_files` / `read_chat_file` 读取。

## 注意事项

- **依赖**：需要 Python 3.8+ 和 Playwright
- **浏览器**：默认使用 Chromium，支持 headless 和 headed 模式
- **登录持久化**：各平台 Cookie 和 storage state 独立保存在 `~/.kimireader/{platform}/`，通常有效数月
- **隐私**：登录状态和聊天记录仅保存在本地，不会上传
- **DOM 兼容性**：如果网页结构大幅变更，可能需要更新对应平台的适配器 `browser_agent/platforms/{platform}.py`

## License

MIT
