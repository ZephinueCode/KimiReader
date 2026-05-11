---
name: chat-to-code-plan
description: 读取网页版Kimi聊天记录并生成代码方案框架（非Flow模式，作为普通Skill调用）
---

# Chat to Code Plan Skill

当你需要将网页版Kimi上的讨论转化为代码实现方案时，使用此Skill。

## 使用步骤

1. **检查并确保登录**
   - 使用 `kimi_login_status` 检查登录状态
   - 如未登录，使用 `kimi_login` 打开浏览器手动登录

2. **选择并导入对话**
   - 使用 `list_chat_sessions` 查看历史对话
   - 使用 `import_chat_history`（带index参数）导入选定对话

3. **分析并生成方案**
   - 启动 `plan` 子Agent进行深度分析
   - 将导入结果的 `full_text` 作为输入传递给子Agent

4. **保存结果**
   - 将方案保存为 `docs/chat-to-code-plan.md`

## 子Agent提示词模板

```
你是一位资深软件架构师。请分析以下聊天记录，生成代码方案框架。

## 聊天记录
{full_text}

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

## 调用方式

```sh
/skill:chat-to-code-plan
```

后面可附带额外指令，例如：
```sh
/skill:chat-to-code-plan 使用Python和FastAPI实现
```
