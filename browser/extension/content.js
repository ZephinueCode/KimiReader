// Content script for kimi.moonshot.cn
// Provides a fallback message extraction method accessible from the page context

(function() {
  'use strict';
  
  // Expose a helper for debugging/testing in console
  window.__kimiReader = {
    export: function() {
      const messages = [];
      const container = document.querySelector('.chat-container, .conversation-container, [class*="chat-list"], [class*="message-list"]') || document.body;
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
        
        if (/user|human|我|发送|right|self|own/i.test(className)) role = 'user';
        else if (/assistant|ai|kimi|bot|model|left|agent/i.test(className)) role = 'assistant';
        
        const style = window.getComputedStyle(el);
        if (style.alignSelf === 'flex-end' || (style.marginLeft && style.marginLeft !== '0px')) role = role || 'user';
        else if (style.alignSelf === 'flex-start') role = role || 'assistant';
        
        if (role) {
          const cleanText = text.replace(/\s+/g, ' ').trim();
          if (cleanText.length > 1) {
            messages.push({ role, content: cleanText });
            seen.add(el);
          }
        }
      }
      
      const title = document.querySelector('h1, [class*="title"], [class*="chat-title"]')?.innerText?.trim() 
        || document.title.replace(' - Kimi', '').trim() 
        || 'kimi_chat';
      
      return {
        title,
        messages,
        export_time: new Date().toISOString()
      };
    }
  };
})();
