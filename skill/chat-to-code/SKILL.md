---
name: chat-to-code
description: 从网页版Kimi/DeepSeek/ChatGPT自动拉取聊天记录，总结并生成代码方案框架
type: flow
---

# Chat to Code Flow

从网页版聊天平台自动拉取聊天记录，提炼需求并生成结构化的代码方案框架。

## 支持平台

- **kimi** (默认): kimi.moonshot.cn
- **deepseek**: chat.deepseek.com
- **chatgpt**: chatgpt.com

## 使用方式

```
/flow:chat-to-code
```

或在 VSCode Kimi Code 面板中输入。

## 流程

```mermaid
flowchart TD
    A([BEGIN]) --> B[检查登录状态]
    B --> C{已登录?}
    C -->|否| D[执行登录: 自动打开浏览器→点击登录按钮→用户扫码/输密码→自动检测关闭]
    D --> B
    C -->|是| E[列出历史对话: 自动展开全部+滚动加载]
    E --> F{是否找到对话?}
    F -->|否| G[提示用户先在网页版进行一些对话]
    G --> H([END])
    F -->|是| I[展示对话列表让用户选择]
    I --> J[导入指定对话]
    J --> K[启动子Agent分析]
    K --> L[输出代码方案框架]
    L --> M[保存到 docs/chat-to-code-plan.md]
    M --> H
```

## 子Agent分析提示模板

```
你是一位资深软件架构师。请分析以下从网页版导出的聊天记录，生成代码方案框架。

## 聊天记录
{chat_full_text}

## 输出要求

1. 需求摘要（2-3句话）
2. 功能模块列表（P0/P1/P2优先级）
3. 推荐技术栈
4. 核心数据模型
5. 关键API/接口设计
6. 推荐目录结构（文本树形图）
7. 实现步骤（按依赖排序的待办清单）
8. 风险与注意点

使用Markdown格式输出。
```

## 最佳实践

- **切换平台**: 默认使用 kimi，如需导入 DeepSeek 或 ChatGPT，在调用时指定 platform 参数
- **长对话处理**: 超过50轮的建议先在网页版整理关键轮次
- **登录持久化**: 各平台登录态独立保存，互不影响
- **与Plan模式结合**: 先生成此框架，再使用 `/plan` 做详细设计
