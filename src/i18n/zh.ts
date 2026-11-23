const zh = {
  // Header
  "app.title": "OpenAI Agents Starter",
  "app.subtitle": "运行于 EdgeOne Makers",

  // Empty state
  "empty.title": "OpenAI Agents Starter",
  "empty.hint": "我是运行在 EdgeOne 环境中的 OpenAI Agents，支持自定义工具、会话记忆，并帮助你完成天气查询、穿衣建议、翻译和文本统计。",
  "empty.features": "EdgeOne Store · Session Memory · Agent Tools",

  // Chat input
  "chat.placeholder": "发消息…  ⏎ 发送 · Shift+⏎ 换行",
  "chat.hint": "由 OpenAI Agents SDK + EdgeOne Makers 驱动 · 仅供演示",

  // Preset questions
  "preset.1": "现在北京天气怎么样，有什么穿衣建议吗？",
  "preset.2": "帮我翻译英文\"你好，欢迎来到北京！\"，并统计翻译字符数。",

  // Tool indicators
  "tool.weather": "天气",
  "tool.clothing": "穿衣",
  "tool.walk": "步行",
  "tool.cycling": "骑行",
  "tool.driving": "驾车",
  "tool.translate": "翻译",
  "tool.statistics": "统计",

  // Status & errors
  "status.error": "⚠️ 请求失败，请检查后端服务是否启动。",
  "status.stopped": "⏹ *已停止生成*",
  "status.backendError": "⚠️ 后端中断请求失败，服务端可能仍在运行。",

  // Debug panel
  "debug.title": "传输流",
  "debug.events": "事件",
  "debug.clear": "清除",
  "debug.empty": "等待 SSE 事件...",
  "debug.emptyHint": "发送消息后，所有原始后端数据将在此处显示。",

  // Conversation sidebar
  "sidebar.label": "会话列表",
  "sidebar.title": "会话",
  "sidebar.newChat": "新建聊天",
  "sidebar.loading": "正在加载会话...",
  "sidebar.loadMore": "加载更多",
  "sidebar.loadingMore": "加载中...",
  "sidebar.emptyTitle": "暂无会话",
  "sidebar.emptyHint": "点击「新建聊天」开始第一段对话。",
  "sidebar.delete": "删除会话",
  "sidebar.deleteConfirm": "确定要永久删除这个会话吗？此操作不可恢复。",

  // Aria labels (button hover/screen-reader)
  "aria.send": "发送",
  "aria.clearHistory": "清除历史",
  "aria.stopGeneration": "停止生成",

  // Language toggle
  "lang.switch": "English",

  // Right-side inspector toggle
  "panel.show": "显示面板",
  "panel.hide": "隐藏面板",

  // ─── Floating bottom-right action badges ─────────────────────────────
  "floatingLink.deploy": "一键部署",
  "floatingLink.github": "GitHub",
} as const;

export default zh;
