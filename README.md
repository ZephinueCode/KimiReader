# KimiReader

从网页版Kimi **自动拉取**聊天记录，自动总结并生成代码方案框架的Kimi Code CLI插件套件。

## 核心特性

- **浏览器自动化**：基于 Playwright，自动登录、保存 Cookie、后台拉取聊天记录
- **首次登录后免交互**：首次使用时打开浏览器手动登录，后续自动复用登录态
- **VSCode 支持**：同时支持 Kimi Code CLI 命令行版和 VSCode 扩展版
- **一键导入**：通过 `/skill:导入聊天记录` 或 `/flow:chat-to-code` 触发全流程
- **代码方案生成**：自动启动子 Agent 总结需求、输出技术架构和实现步骤

## 项目结构

```
KimiReader/
├── browser_agent/              # Playwright 浏览器自动化核心
│   ├── auth.py                 # 登录状态管理（Cookie/Storage 持久化）
│   ├── extractor.py            # 聊天记录提取（多策略容错）
│   ├── requirements.txt        # Python 依赖
│   └── __init__.py
├── plugin/                     # Kimi Code CLI 插件
│   ├── plugin.json             # 声明 7 个工具
│   ├── config.json
│   └── scripts/
│       ├── kimireader_browser.py   # 浏览器自动化入口
│       └── read_chat.py            # 本地文件读取（兼容模式）
├── skill/
│   ├── chat-to-code/           # Flow Skill（全自动）
│   │   ├── SKILL.md
│   │   └── PLAN-SKILL.md
│   └── 导入聊天记录/            # 普通 Skill（手动/半自动）
│       └── SKILL.md
├── install/                    # 安装脚本
│   ├── install-windows.ps1
│   └── install-linux.sh
├── browser/                    # 浏览器端备用工具（书签/扩展）
│   ├── bookmarklet.js
│   └── extension/
└── README.md
```

## 快速开始

### 1. 安装

**Windows（PowerShell）：**

```powershell
# 在项目根目录执行
.\install\install-windows.ps1
```

**Linux / macOS（Bash）：**

```bash
# 在项目根目录执行
bash install/install-linux.sh
```

安装脚本会自动完成：
1. 检测并安装 Python 3.8+ 依赖（playwright）
2. 下载 Playwright Chromium 浏览器
3. 安装 Kimi Code CLI 插件到 `~/.kimi/plugins/`
4. 安装 Agent Skills 到 `~/.kimi/skills/`
5. 检测 VSCode Kimi Code 扩展并给出使用提示
6. （可选）安装项目级 Skill

### 2. 首次登录

安装完成后，在 Kimi Code CLI 或 VSCode Kimi Code 面板中输入：

```
/skill:导入聊天记录
```

如果未登录，系统会自动调用 `kimi_login`，打开浏览器窗口让你手动登录 kimi.moonshot.cn：

1. 在打开的浏览器中完成登录（扫码/密码/手机号）
2. 登录成功后，**关闭浏览器窗口**
3. 登录状态会自动保存到 `~/.kimireader/`，后续无需重复登录

### 3. 导入聊天记录

登录完成后，再次执行：

```
/skill:导入聊天记录
```

AI 会自动：
1. 列出你在网页版 Kimi 上的历史对话
2. 让你选择（或自动选择最新）对话
3. 拉取完整聊天记录到当前上下文

### 4. 生成代码方案（全自动）

```
/flow:chat-to-code
```

这个 Flow 会自动完成：
1. 检查/完成登录
2. 列出历史对话并选择
3. 导入聊天记录
4. 启动 `plan` 子 Agent 分析
5. 生成包含 **需求摘要、功能模块(P0/P1/P2)、技术栈、数据模型、API 设计、目录结构、实现步骤** 的方案
6. 保存到 `docs/chat-to-code-plan.md`

## 插件工具说明

| 工具名 | 说明 |
|--------|------|
| `kimi_login_status` | 检查浏览器自动化登录状态 |
| `kimi_login` | 打开浏览器窗口进行交互式登录 |
| `kimi_logout` | 清除保存的登录状态 |
| `list_chat_sessions` | 列出网页版Kimi历史对话列表 |
| `import_chat_history` | 导入指定对话的完整聊天记录 |
| `list_chat_files` | （兼容模式）查找本地导出的聊天记录文件 |
| `read_chat_file` | （兼容模式）读取本地聊天记录文件 |

## VSCode 版本使用说明

VSCode 的 Kimi Code 扩展底层使用的是同一个 CLI，因此插件和 Skill 安装后在 VSCode 中同样可用。

在 VSCode 的 Kimi Code 聊天面板中直接输入：

```
/flow:chat-to-code
```

或

```
/skill:导入聊天记录
```

**注意**：在 VSCode 中使用 `kimi_login` 时，同样会弹出浏览器窗口，操作与 CLI 版本一致。

## 手动调用示例

```bash
# 检查登录状态
→ kimi_login_status

# 登录（首次使用）
→ kimi_login

# 列出历史对话
→ list_chat_sessions

# 导入第0个对话（最新的）
→ import_chat_history(index: 0)

# 半自动模式：先列出，再导入
→ list_chat_sessions
→ import_chat_history(index: 2)
```

## 浏览器端备用方案

如果浏览器自动化因网络/环境原因无法使用，还提供了：

- **书签脚本**：`browser/bookmarklet.js`，复制 minified 代码到浏览器书签栏
- **浏览器扩展**：`browser/extension/`，支持 Chrome/Edge

这两个工具将网页版聊天记录导出为 JSON 文件，然后通过 `list_chat_files` / `read_chat_file` 读取。

## 注意事项

- **依赖**：需要 Python 3.8+ 和 Playwright
- **浏览器**：默认使用 Chromium，支持 headless 和 headed 模式
- **登录持久化**：Cookie 和 storage state 保存在 `~/.kimireader/`，通常有效数月
- **隐私**：登录状态和聊天记录仅保存在本地，不会上传
- **DOM 兼容性**：如果 kimi.moonshot.cn 网页结构大幅变更，可能需要更新 `browser_agent/extractor.py`

## 技术栈

- **浏览器自动化**：Playwright (Python)
- **CLI 插件**：Kimi Code CLI Plugin 格式 (`plugin.json`)
- **工作流**：Agent Skills / Flow Skills
- **安装脚本**：PowerShell (Windows) / Bash (Linux/macOS)

## License

MIT
