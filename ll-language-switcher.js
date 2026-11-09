/* LL Language Switcher v3.0 – public Haravan pages only.
   Works from complete, pre-generated translation packs; never calls paid APIs.
   No overlay, no page blur, no automatic browser-model downloads.
   With missing/invalid pack, the website remains usable in Vietnamese.
*/
(function () {
  'use strict';
  if (window.__LL_LANG_V3__) return;
  window.__LL_LANG_V3__ = true;

  var BASE = String(window.LL_I18N_BASE || '').trim().replace(/\/+$/, '');
  var PREF_KEY = 'll_website_lang_v3';
  var LANGS = {vi:'🇻🇳 Tiếng Việt', en:'🇬🇧 English', zh:'🇨🇳 简体中文'};
  var EXCLUDE = 'script,style,noscript,template,iframe,svg,canvas,pre,code,textarea,option,' +
    '[contenteditable],[translate="no"],[data-ll-no-translate],[data-ll-private],' +
    '#ll-ai-chat,#ll-language-v3,#ll-language-v3-notice,.subiz-widget,' +
    '#fb-root,#at4-share,#at4-soc,#at4-share2,#at4-soc2,[id^="subiz"]';
  var ATTRIBUTES = ['placeholder', 'title', 'aria-label', 'alt'];
  var textOriginal = new WeakMap(), attrOriginal = new WeakMap(), valueOriginal = new WeakMap();
  var lang = 'vi', desired = 'vi', activePack = null, run = 0, applying = false;
  var observer = null, refreshTimer = null, noticeTimer = null, requestController = null;
  var select = null;

  function norm(s) { return String(s == null ? '' : s).normalize('NFC').replace(/\s+/g,' ').trim(); }
  function translatable(s) {
    var t = norm(s);
    // Same identifier filter as tools/build_translations.py. Do not require
    // translated strings for internal URL paths like /blogs/goc-tu-van/...
    if (/^\/[^\s<>]+$/.test(t)) return false;
    // Keep public website references and English street addresses unchanged.
    // Must mirror tools/build_translations.py so a complete pack stays complete.
    if (/^Website:\s*(?:[a-z0-9-]+\.)+[a-z]{2,}$/i.test(t)) return false;
    if (/^Airport Blvd,\s*Singapore$/i.test(t)) return false;
    if (/^Parkway Parade:\s*\d+\s+Marine Parade\b/i.test(t)) return false;
    return t.length > 1 && /[a-zA-Z\u00C0-\u024F\u1E00-\u1EFF\u3400-\u9FFF]/u.test(t) &&
      !/^(https?:\/\/|www\.|mailto:|tel:)/i.test(t) &&
      !/^[\w.+-]+@[\w.-]+\.[a-z]{2,}$/i.test(t) &&
      !/^(VẬN TẢI LƯU LÊ|Vận Tải Lưu Lê|Lưu Lê|LL|VNĐ)$/i.test(t);
  }
  function route() { return decodeURIComponent(location.pathname).replace(/\/+$/,'') || '/'; }
  function routeKey(path) {
    return ((path || '/').replace(/^\/+|\/+$/g,'') || 'home')
      .replace(/\//g,'__').replace(/[^a-zA-Z0-9_-]/g,'_');
  }
  function originalText(n) {
    var old = textOriginal.get(n);
    return old && n.nodeValue === old.last ? old.source : n.nodeValue;
  }
  function originalAttribute(el, attr) {
    var old = attrOriginal.get(el), current = el.getAttribute(attr);
    return old && old[attr] && old[attr].last === current ? old[attr].source : current;
  }
  function originalValue(el) {
    var old = valueOriginal.get(el);
    return old && old.last === el.value ? old.source : el.value;
  }
  function excluded(el) { return !el || !!el.closest(EXCLUDE); }
  function collect() {
    var root = document.body;
    if (!root) return [];
    var result = [];
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode:function(n) {
        return n.parentElement && !excluded(n.parentElement) && translatable(originalText(n))
          ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var node;
    while ((node = walker.nextNode())) {
      var source = originalText(node);
      result.push({type:'text',node:node,source:source,key:norm(source)});
    }
    var nodes = [root].concat(Array.from(root.querySelectorAll('*')));
    nodes.forEach(function(el) {
      if (excluded(el)) return;
      ATTRIBUTES.forEach(function(attr) {
        if (!el.hasAttribute(attr)) return;
        var source = originalAttribute(el,attr);
        if (translatable(source)) result.push({type:'attribute',node:el,attr:attr,source:source,key:norm(source)});
      });
      if (el.tagName === 'INPUT' && /^(submit|button|reset)$/i.test(el.type)) {
        var source = originalValue(el);
        if (translatable(source)) result.push({type:'value',node:el,source:source,key:norm(source)});
      }
    });
    return result;
  }
  function restore() {
    var data = collect();
    applying = true;
    try {
      data.forEach(function(x) {
        if (x.type === 'text') {
          if (x.node.nodeValue !== x.source) x.node.nodeValue = x.source;
        } else if (x.type === 'attribute') {
          if (x.node.getAttribute(x.attr) !== x.source) x.node.setAttribute(x.attr,x.source);
        } else if (x.type === 'value' && x.node.value !== x.source) x.node.value = x.source;
      });
    } finally { applying = false; }
    lang = 'vi';
    document.documentElement.lang = 'vi';
    if (select) select.value = 'vi';
    return collect();
  }
  function hideNotice() {
    var el = document.getElementById('ll-language-v3-notice');
    if (el) el.hidden = true;
  }
  function notify(msg) {
    var el = document.getElementById('ll-language-v3-notice');
    if (!el) return;
    el.querySelector('.ll-notice-text').textContent = msg;
    el.hidden = false;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(hideNotice, 6500);
  }
  async function getPack(signal) {
    if (!/^https:\/\/[^\s/]+(?:\/[^\s]*)?$/i.test(BASE) && !/^\/[^/]/.test(BASE)) return null;
    var url = BASE + '/i18n/' + routeKey(route()) + '.json';
    try {
      var res = await fetch(url,{mode:'cors',cache:'no-store',signal:signal,credentials:'omit'});
      if (!res.ok) return null;
      var data = await res.json();
      if (!data || data.version !== 3 || data.route !== route() || !data.texts || typeof data.texts !== 'object') return null;
      return data;
    } catch (_e) { return null; }
  }
  function getTranslations(pack,list,target) {
    if (!pack || !pack.texts) return null;
    var values = [];
    for (var i=0; i<list.length; i++) {
      var entry = Object.prototype.hasOwnProperty.call(pack.texts,list[i].key) && pack.texts[list[i].key];
      var v = entry && entry[target];
      if (typeof v !== 'string' || !norm(v)) return null;
      values.push(v);
    }
    return values;
  }
  function putTranslations(list,values,target) {
    if (!values || list.length !== values.length) return false;
    applying = true;
    try {
      for (var i=0; i<list.length; i++) {
        var x = list[i], translated = norm(values[i]);
        if (!x.node.isConnected) throw new Error('Changed DOM while applying');
        if (x.type === 'text') {
          var prefix = (x.source.match(/^\s*/) || [''])[0];
          var suffix = (x.source.match(/\s*$/) || [''])[0];
          var next = prefix + translated + suffix;
          x.node.nodeValue = next;
          textOriginal.set(x.node,{source:x.source,last:next});
        } else if (x.type === 'attribute') {
          x.node.setAttribute(x.attr,translated);
          var old = attrOriginal.get(x.node) || {};
          old[x.attr] = {source:x.source,last:translated};
          attrOriginal.set(x.node,old);
        } else if (x.type === 'value') {
          x.node.value = translated;
          valueOriginal.set(x.node,{source:x.source,last:translated});
        }
      }
      lang = target;
      document.documentElement.lang = target === 'zh' ? 'zh-Hans' : target;
      if (select) select.value = target;
      return true;
    } catch (_e) { return false; }
    finally { applying = false; }
  }
  async function changeLanguage(target, saved) {
    if (!LANGS[target]) target = 'vi';
    var sequence = ++run;
    desired = target;
    hideNotice();
    if (requestController) requestController.abort();
    requestController = null;
    var list = restore();
    if (target === 'vi') {
      if (!saved) { try {localStorage.setItem(PREF_KEY,'vi');} catch(_e) {} }
      return;
    }
    if (!BASE || BASE.indexOf('REPLACE') !== -1) {
      notify('Chưa kết nối kho bản dịch. Website vẫn hiển thị tiếng Việt.');
      return;
    }
    var controller = new AbortController();
    requestController = controller;
    var timer = setTimeout(function(){controller.abort();}, 8000);
    var pack;
    try { pack = activePack && activePack.route === route() ? activePack : await getPack(controller.signal); }
    finally { clearTimeout(timer); }
    if (sequence !== run) return;
    activePack = pack;
    var values = getTranslations(pack,list,target);
    if (!values) {
      notify('Bản dịch đầy đủ của trang này chưa sẵn sàng. Trang đang giữ nguyên tiếng Việt.');
      return;
    }
    if (!putTranslations(list,values,target)) {
      restore();
      notify('Trang đã thay đổi nội dung trong lúc dịch. Đã trở lại tiếng Việt an toàn.');
      return;
    }
    if (!saved) { try {localStorage.setItem(PREF_KEY,target);} catch(_e) {} }
  }
  function checkDynamicChanges() {
    if (applying || lang === 'vi') return;
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function() {
      if (lang === 'vi' || !activePack) return;
      var list = collect();
      var vals = getTranslations(activePack,list,lang);
      // Only translate nodes newly injected by page scripts; do not repeatedly rewrite
      // nodes that are already translated (prevents MutationObserver loops).
      var pending = [], pendingValues = [];
      if (vals) list.forEach(function(x,i) {
        var state = x.type === 'text' ? textOriginal.get(x.node)
          : x.type === 'attribute' ? (attrOriginal.get(x.node) || {})[x.attr]
          : valueOriginal.get(x.node);
        var displayed = x.type === 'text' ? x.node.nodeValue
          : x.type === 'attribute' ? x.node.getAttribute(x.attr) : x.node.value;
        if (!state || state.last !== displayed) { pending.push(x); pendingValues.push(vals[i]); }
      });
      // Whole-page consistency: if newly inserted material has no translation, roll back all.
      if (!vals || (pending.length && !putTranslations(pending,pendingValues,lang))) {
        ++run;
        restore();
        notify('Trang vừa cập nhật nội dung chưa có bản dịch. Đã chuyển về tiếng Việt để tránh trộn ngôn ngữ.');
      }
    }, 320);
  }
  function init() {
    if (!document.body) return;
    // No configured translation repository: deliberately DO NOT activate a broken UI.
    if (!BASE || BASE.indexOf('REPLACE') !== -1) {
      console.info('[LL Languages V3] Chưa cấu hình LL_I18N_BASE; website tiếng Việt hoạt động bình thường.');
      return;
    }
    var css = document.createElement('style');
    css.textContent = '#ll-language-v3{position:fixed;z-index:1095;right:15px;top:78px;background:#fff;border:1px solid #cfe2d7;border-radius:10px;box-shadow:0 4px 14px #0002;padding:7px 9px;display:flex;align-items:center;gap:5px;font:14px Arial,sans-serif}' +
      '#ll-language-v3 select{font:14px Arial,sans-serif;color:#13643b;background:#fff;border:0;max-width:148px;cursor:pointer;padding:4px;outline-color:#f58220}' +
      '#ll-language-v3-notice{position:fixed;left:15px;bottom:18px;z-index:1096;background:#fffaf0;color:#65430c;border:1px solid #efc785;border-radius:10px;box-shadow:0 3px 14px #0002;padding:11px 14px;font:14px Arial,sans-serif;max-width:min(420px,calc(100% - 35px))}' +
      '#ll-language-v3-notice[hidden]{display:none!important}#ll-language-v3-notice button{margin-left:12px;border:0;background:transparent;cursor:pointer;font:18px Arial}' +
      '@media(max-width:767px){#ll-language-v3{top:10px;right:9px;padding:5px 6px}#ll-language-v3 select{font-size:12px;max-width:128px}}';
    document.head.appendChild(css);
    var box = document.createElement('div');
    box.id = 'll-language-v3';
    box.setAttribute('data-ll-no-translate','');
    box.setAttribute('aria-label','Chọn ngôn ngữ trang web');
    var globe = document.createElement('span'); globe.textContent='🌐'; globe.setAttribute('aria-hidden','true');
    select = document.createElement('select'); select.setAttribute('aria-label','Chọn ngôn ngữ / Language / 语言');
    Object.keys(LANGS).forEach(function(key){var o=document.createElement('option');o.value=key;o.textContent=LANGS[key];select.appendChild(o);});
    select.value = 'vi';
    select.addEventListener('change',function(){changeLanguage(select.value,false);});
    box.appendChild(globe);box.appendChild(select);document.body.appendChild(box);
    var notice = document.createElement('div'); notice.id='ll-language-v3-notice';notice.hidden=true;
    notice.setAttribute('role','status');notice.setAttribute('data-ll-no-translate','');
    var message=document.createElement('span');message.className='ll-notice-text';
    var close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Đóng');close.onclick=hideNotice;
    notice.appendChild(message);notice.appendChild(close);document.body.appendChild(notice);
    var root=document.body;
    observer=new MutationObserver(checkDynamicChanges);
    observer.observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:ATTRIBUTES});
    try{ var saved=localStorage.getItem(PREF_KEY);if(LANGS[saved])desired=saved;}catch(_e){}
    if (desired !== 'vi') changeLanguage(desired,true);
    window.LLGlobalI18N={
      state:function(){return {version:'3.0',lang:lang,route:route(),base:BASE,packLoaded:!!activePack};},
      changeLanguage:function(code){return changeLanguage(code,false);},
      reset:function(){return changeLanguage('vi',false);}
    };
  }
  if (document.readyState === 'complete') init();
  else window.addEventListener('load',function(){setTimeout(init,150);},{once:true});
})();
