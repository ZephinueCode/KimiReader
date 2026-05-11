document.getElementById('exportBtn').addEventListener('click', async () => {
  const status = document.getElementById('status');
  const btn = document.getElementById('exportBtn');
  
  btn.disabled = true;
  status.textContent = '正在提取...';
  status.className = '';

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab.url.includes('kimi.moonshot.cn')) {
      status.textContent = '错误：请在 kimi.moonshot.cn 页面使用';
      status.className = 'error';
      btn.disabled = false;
      return;
    }

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractAndExport
    });

    const result = results[0].result;
    if (result.error) {
      status.textContent = '错误：' + result.error;
      status.className = 'error';
    } else {
      status.textContent = `成功导出 ${result.count} 条消息`;
      status.className = 'success';
    }
  } catch (err) {
    status.textContent = '错误：' + err.message;
    status.className = 'error';
  }

  btn.disabled = false;
});

function extractAndExport() {
  function extractMessages() {
    const messages = [];
    let container = document.querySelector('.chat-container, .conversation-container, [class*="chat-list"], [class*="message-list"]');
    if (!container) container = document.body;
    
    const allElements = container.querySelectorAll('*');
    const seen = new Set();
    
    for (const el of allElements) {
      let parent = el.parentElement;
      let skip = false;
      while (parent) {
        if (seen.has(parent)) { skip = true; break; }
        parent = parent.parentElement;
      }
      if (skip) continue;
      
      const text = el.innerText || '';
      if (text.length < 2) continue;
      
      const className = el.className || '';
      let role = null;
      
      if (/user|human|我|发送|right|self|own/i.test(className)) {
        role = 'user';
      } else if (/assistant|ai|kimi|bot|model|left|agent/i.test(className)) {
        role = 'assistant';
      }
      
      const style = window.getComputedStyle(el);
      if (style.alignSelf === 'flex-end' || (style.marginLeft && style.marginLeft !== '0px')) {
        role = role || 'user';
      } else if (style.alignSelf === 'flex-start') {
        role = role || 'assistant';
      }
      
      if (role && text.length > 0) {
        const cleanText = text.replace(/\s+/g, ' ').trim();
        if (cleanText.length > 1) {
          messages.push({ role, content: cleanText });
          seen.add(el);
        }
      }
    }
    
    // Fallback: try window globals
    if (messages.length === 0) {
      for (const key of Object.keys(window)) {
        try {
          const val = window[key];
          if (val && typeof val === 'object' && Array.isArray(val.messages)) {
            val.messages.forEach(m => {
              if (m.content) messages.push({ role: m.role || 'unknown', content: m.content });
            });
          }
        } catch(e) {}
      }
    }
    
    return messages;
  }
  
  function getChatTitle() {
    const titleEl = document.querySelector('h1, [class*="title"], [class*="chat-title"]');
    if (titleEl) return titleEl.innerText.trim();
    return document.title.replace(' - Kimi', '').trim() || 'kimi_chat';
  }
  
  const messages = extractMessages();
  if (messages.length === 0) {
    return { error: '未检测到聊天记录。请确保消息已加载完成。' };
  }
  
  const title = getChatTitle();
  const exportData = {
    title: title,
    source: 'kimi.moonshot.cn',
    export_time: new Date().toISOString(),
    url: location.href,
    message_count: messages.length,
    messages: messages
  };
  
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'kimi_chat_' + title.replace(/[^\w\u4e00-\u9fa5]/g, '_').substring(0, 30) + '_' + Date.now() + '.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  
  return { count: messages.length, title: title };
}
