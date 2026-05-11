/**
 * KimiReader Browser Bookmarklet
 * 
 * 使用方法：
 * 1. 复制下面 minified 版本的代码（从 javascript: 开始到末尾）
 * 2. 在浏览器书签栏新建一个书签，将代码粘贴到 URL/地址栏
 * 3. 在 kimi.moonshot.cn 打开任意聊天记录页面
 * 4. 点击书签，即可导出当前聊天记录为JSON文件
 * 
 * 注意：此脚本仅在 kimi.moonshot.cn 域名下有效。
 */

// ===== 完整源码（供参考和调试） =====
const KIMI_EXPORTER_SOURCE = `
(function() {
  'use strict';
  
  const DOMAIN = 'kimi.moonshot.cn';
  if (!location.hostname.includes(DOMAIN)) {
    alert('请在 kimi.moonshot.cn 页面使用此书签');
    return;
  }

  function extractMessages() {
    const messages = [];
    
    // 策略1：通过DOM结构提取（适配2025年5月kimi网页版结构）
    // 用户消息和助手消息通常有不同的class或属性
    const messageSelectors = [
      '[class*="message"]', 
      '[class*="chat-item"]',
      '[class*="bubble"]',
      '.chat-message',
      '.message-item',
      '[data-testid*="message"]'
    ];
    
    // 尝试找到消息容器
    let container = document.querySelector('.chat-container, .conversation-container, [class*="chat-list"], [class*="message-list"]');
    if (!container) {
      container = document.body;
    }
    
    // 基于常见布局特征识别消息
    const allElements = container.querySelectorAll('*');
    const seen = new Set();
    
    for (const el of allElements) {
      // 跳过已处理的元素子树
      let parent = el.parentElement;
      let skip = false;
      while (parent) {
        if (seen.has(parent)) { skip = true; break; }
        parent = parent.parentElement;
      }
      if (skip) continue;
      
      const text = el.innerText || '';
      if (text.length < 2) continue;
      
      // 判断角色：通过class名、位置、头像等特征
      const className = el.className || '';
      const html = el.innerHTML || '';
      
      let role = null;
      if (/user|human|我|发送|right|self|own/i.test(className)) {
        role = 'user';
      } else if (/assistant|ai|kimi|bot|model|left|agent/i.test(className)) {
        role = 'assistant';
      } else if (el.querySelector('img[src*="avatar"], img[class*="avatar"]')) {
        // 有头像的通常是助手
        role = 'assistant';
      }
      
      // 通过DOM位置辅助判断：右对齐一般是用户
      const style = window.getComputedStyle(el);
      const alignSelf = style.alignSelf;
      const marginLeft = style.marginLeft;
      const marginRight = style.marginRight;
      if (alignSelf === 'flex-end' || (marginLeft && marginLeft !== '0px' && marginLeft !== '0')) {
        role = role || 'user';
      } else if (alignSelf === 'flex-start') {
        role = role || 'assistant';
      }
      
      if (role && text.length > 0) {
        // 清理文本
        const cleanText = text.replace(/\\s+/g, ' ').trim();
        if (cleanText.length > 1) {
          messages.push({ role, content: cleanText });
          seen.add(el);
        }
      }
    }
    
    // 策略2：如果DOM提取失败，尝试从React/Vue状态中提取
    if (messages.length === 0) {
      try {
        const scripts = document.querySelectorAll('script');
        for (const script of scripts) {
          const text = script.textContent || '';
          if (text.includes('messages') || text.includes('conversation')) {
            const match = text.match(/messages[:\s]*(\[[\\s\\S]*?\])/);
            if (match) {
              try {
                const parsed = JSON.parse(match[1]);
                if (Array.isArray(parsed)) {
                  parsed.forEach(m => {
                    if (m.content || m.text) {
                      messages.push({
                        role: m.role || m.sender || 'unknown',
                        content: m.content || m.text || ''
                      });
                    }
                  });
                }
              } catch(e) {}
            }
          }
        }
      } catch(e) {}
    }
    
    // 策略3：尝试从window全局变量找
    if (messages.length === 0) {
      for (const key of Object.keys(window)) {
        try {
          const val = window[key];
          if (val && typeof val === 'object' && Array.isArray(val.messages)) {
            val.messages.forEach(m => {
              if (m.content) {
                messages.push({
                  role: m.role || 'unknown',
                  content: m.content
                });
              }
            });
          }
        } catch(e) {}
      }
    }
    
    return messages;
  }
  
  function getChatTitle() {
    // 尝试获取对话标题
    const titleEl = document.querySelector('h1, [class*="title"], [class*="chat-title"]');
    if (titleEl) return titleEl.innerText.trim();
    return document.title.replace(' - Kimi', '').replace(' -  Kimi', '').trim() || 'kimi_chat';
  }
  
  const messages = extractMessages();
  if (messages.length === 0) {
    alert('未检测到聊天记录。请确保当前页面是展开的对话页面，且消息已加载完成。');
    return;
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
  a.download = 'kimi_chat_' + title.replace(/[^\\w\\u4e00-\\u9fa5]/g, '_').substring(0, 30) + '_' + Date.now() + '.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  
  alert('成功导出 ' + messages.length + ' 条消息到下载目录');
})();
`;

// ===== Minified 版本（用于书签） =====
// 将下面这一行复制到浏览器书签的URL中：
const KIMI_BOOKMARKLET_MINIFIED = `javascript:(function(){'use strict';const D='kimi.moonshot.cn';if(!location.hostname.includes(D)){alert('请在 kimi.moonshot.cn 页面使用此书签');return;}function E(){const M=[];let C=document.querySelector('.chat-container,.conversation-container,[class*="chat-list"],[class*="message-list"]');if(!C)C=document.body;const A=C.querySelectorAll('*'),S=new Set();for(const el of A){let p=el.parentElement,sk=false;while(p){if(S.has(p)){sk=true;break;}p=p.parentElement;}if(sk)continue;const t=el.innerText||'';if(t.length<2)continue;const c=el.className||'';let r=null;if(/user|human|我|发送|right|self|own/i.test(c))r='user';else if(/assistant|ai|kimi|bot|model|left|agent/i.test(c))r='assistant';const s=window.getComputedStyle(el);if(s.alignSelf==='flex-end'||s.marginLeft&&s.marginLeft!=='0px')r=r||'user';else if(s.alignSelf==='flex-start')r=r||'assistant';if(r&&t.length>0){const x=t.replace(/\\s+/g,' ').trim();if(x.length>1){M.push({role:r,content:x});S.add(el);}}}if(M.length===0){try{const X=document.querySelectorAll('script');for(const sc of X){const tc=sc.textContent||'';if(tc.includes('messages')){const m=tc.match(/messages[:\\s]*(\\[[\\s\\S]*?\\])/);if(m){try{const p=JSON.parse(m[1]);if(Array.isArray(p))p.forEach(v=>{if(v.content||v.text)M.push({role:v.role||v.sender||'unknown',content:v.content||v.text||''});});}catch(e){}}}}catch(e){}}if(M.length===0){for(const k of Object.keys(window)){try{const v=window[k];if(v&&typeof v==='object'&&Array.isArray(v.messages))v.messages.forEach(m=>{if(m.content)M.push({role:m.role||'unknown',content:m.content});});}catch(e){}}}return M;}function T(){const e=document.querySelector('h1,[class*="title"],[class*="chat-title"]');if(e)return e.innerText.trim();return document.title.replace(' - Kimi','').trim()||'kimi_chat';}const m=E();if(m.length===0){alert('未检测到聊天记录。请确保当前页面是展开的对话页面，且消息已加载完成。');return;}const t=T();const d={title:t,source:'kimi.moonshot.cn',export_time:new Date().toISOString(),url:location.href,message_count:m.length,messages:m};const b=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download='kimi_chat_'+t.replace(/[^\\w\\u4e00-\\u9fa5]/g,'_').substring(0,30)+'_'+Date.now()+'.json';document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(u);alert('成功导出 '+m.length+' 条消息到下载目录');})();`;

// 输出到控制台供复制
console.log("===== KimiReader Bookmarklet =====");
console.log("复制下面这一行代码，粘贴到浏览器书签的URL栏：");
console.log(KIMI_BOOKMARKLET_MINIFIED);
console.log("\n===== 完整源码 =====");
console.log(KIMI_EXPORTER_SOURCE);
