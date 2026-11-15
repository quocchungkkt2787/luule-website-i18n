/* Luu Le public image localization runtime v1.
 * Works with the existing Haravan LL Language V3.8.6 selection and Cloudflare
 * Pages static files. Does not change layout or download private/customer data.
 * Only APPROVED image variants listed in images/manifest.json are substituted.
 */
(function(){
  'use strict';
  if(window.__LL_IMAGE_I18N_V1__)return;
  window.__LL_IMAGE_I18N_V1__=true;
  var base=String(window.LL_I18N_BASE||'').trim().replace(/\/+$/,'');
  if(!/^https:\/\//i.test(base))return;
  var pairs=Object.create(null),ready=false,mutating=false,pending=false,changed=0,missing=0;
  var originals=new WeakMap(),backgrounds=new WeakMap();
  var knownHosts=/^(?:www\.)?vantailuule\.vn$|^(?:cdn|theme|file|product|media)\.hstatic\.net$/i;
  function key(url){
    if(!url||/^data:|^blob:/i.test(url))return null;
    try{
      var u=new URL(url,location.href);
      if(!/^https?:$/.test(u.protocol)||!knownHosts.test(u.hostname))return null;
      return u.origin+u.pathname;
    }catch(e){return null;}
  }
  function language(){
    var lang=document.documentElement.getAttribute('data-ll-i18n-active');
    if(lang==='en'||lang==='zh')return lang;
    try{
      var state=window.LLGlobalI18N&&window.LLGlobalI18N.state&&window.LLGlobalI18N.state();
      if(state&&/^(vi|en|zh)$/.test(state.lang))return state.lang;
    }catch(e){}
    return 'vi';
  }
  function urlOf(value){
    if(typeof value!=='string'||!/^(?:images\/assets\/)[\w./-]+$/.test(value))return null;
    if(value.indexOf('..')!==-1)return null;
    return base+'/i18n/'+value;
  }
  function firstSrcSet(srcset){
    return (srcset||'').split(',')[0].trim().split(/\s+/)[0];
  }
  function skip(node){
    return node.closest&&node.closest('[data-ll-private],#llai-root,#ll-ai-chat,[data-ll-image-keep],#ll-language-v3');
  }
  function applyImage(el,lang){
    if(skip(el))return;
    var rec=originals.get(el);
    var src=el.getAttribute('src')||'';
    var srcset=el.getAttribute('srcset')||'';
    var lazy=el.getAttribute('data-src')||'';
    if(!rec){
      rec={src:src,srcset:srcset,lazy:lazy,applied:null,changed:false};
      originals.set(el,rec);
    }else if(rec.applied && src && src!==rec.applied && src!==rec.src){
      // A lazy loader replaced this image after an earlier switch.
      rec.src=src;rec.srcset=srcset;rec.lazy=lazy;rec.applied=null;rec.changed=false;
    }
    var source=key(rec.lazy||rec.src||firstSrcSet(rec.srcset));
    var row=source&&pairs[source];
    var translated=lang!=='vi'&&row&&urlOf(row[lang]);
    if(translated){
      if(el.getAttribute('src')!==translated){
        if(el.hasAttribute('srcset'))el.removeAttribute('srcset');
        if(el.hasAttribute('data-src'))el.setAttribute('data-src',translated);
        el.setAttribute('src',translated);
        rec.applied=translated;rec.changed=true;changed++;
      }
    }else if(rec.changed){
      if(rec.src)el.setAttribute('src',rec.src);else el.removeAttribute('src');
      if(rec.srcset)el.setAttribute('srcset',rec.srcset);else el.removeAttribute('srcset');
      if(rec.lazy)el.setAttribute('data-src',rec.lazy);else el.removeAttribute('data-src');
      rec.changed=false;rec.applied=null;
    }
  }
  function applySource(el,lang){
    if(skip(el))return;
    var rec=originals.get(el);
    if(!rec){rec={srcset:el.getAttribute('srcset')||'',applied:null,changed:false}; originals.set(el,rec);}
    var source=key(firstSrcSet(rec.srcset)),row=source&&pairs[source];
    var variant=lang!=='vi'&&row&&urlOf(row[lang]);
    if(variant){
      if(el.getAttribute('srcset')!==variant){
        el.setAttribute('srcset',variant);rec.applied=variant;rec.changed=true;changed++;
      }
    }else if(rec.changed){
      if(rec.srcset)el.setAttribute('srcset',rec.srcset);else el.removeAttribute('srcset');
      rec.applied=null;rec.changed=false;
    }
  }
  var backgroundSelector='[style*="background"],[data-background],[data-bg],.hero,.banner,.slideshow,.slider-banner';
  function applyBackground(el,lang){
    if(skip(el))return;
    var rec=backgrounds.get(el);
    if(!rec){
      var css=el.style.backgroundImage||getComputedStyle(el).backgroundImage;
      var match=css&&css.match(/url\(["']?([^"')]+)/i);
      if(!match)return;
      rec={origStyle:el.style.backgroundImage,source:key(match[1]),changed:false};
      backgrounds.set(el,rec);
    }
    var row=rec.source&&pairs[rec.source],variant=lang!=='vi'&&row&&urlOf(row[lang]);
    if(variant){
      var cssNew='url("'+variant.replace(/"/g,'')+'")';
      if(el.style.backgroundImage!==cssNew){
        el.style.backgroundImage=cssNew;rec.changed=true;changed++;
      }
    }else if(rec.changed){
      el.style.backgroundImage=rec.origStyle;rec.changed=false;
    }
  }
  function apply(){
    pending=false;if(!ready||mutating)return;
    mutating=true;
    try{
      var lang=language();
      document.querySelectorAll('picture source[srcset]').forEach(function(el){applySource(el,lang);});
      document.querySelectorAll('img').forEach(function(el){applyImage(el,lang);});
      document.querySelectorAll(backgroundSelector).forEach(function(el){applyBackground(el,lang);});
    }finally{mutating=false;}
  }
  function schedule(){
    if(pending||!ready)return;
    pending=true;setTimeout(apply,100);
  }
  function init(){
    if(!document.body)return;
    fetch(base+'/i18n/images/manifest.json',{cache:'no-store',mode:'cors'})
      .then(function(response){if(!response.ok)throw Error('HTTP '+response.status);return response.json();})
      .then(function(data){
        if(!data||data.version!==1||!data.assets||typeof data.assets!=='object')throw Error('Invalid image manifest');
        Object.keys(data.assets).forEach(function(orig){
          var row=data.assets[orig];
          if(key(orig)===orig&&row&&urlOf(row.en)&&urlOf(row.zh))pairs[orig]=row;
        });
        ready=true;
        apply();
        var observer=new MutationObserver(function(records){
          if(mutating)return;
          if(records.some(function(r){
            var el=r.target&&r.target.nodeType===1?r.target:r.target.parentElement;
            return el&&(!skip(el));
          }))schedule();
        });
        observer.observe(document.body,{childList:true,subtree:true,attributes:true,
          attributeFilter:['src','srcset','data-src','style','data-background','data-bg']});
        new MutationObserver(schedule).observe(document.documentElement,{
          attributes:true,attributeFilter:['data-ll-i18n-active']});
        window.addEventListener('pageshow',schedule);
      })
      .catch(function(error){console.warn('[LL Image I18N] Reviewed-image manifest unavailable:',error.message);});
  }
  window.LLImageI18N={state:function(){return {version:'1.0',ready:ready,approvedPairs:Object.keys(pairs).length,
      lang:language(),applied:changed,description:'Only reviewed public image variants are switched.'};},
    refresh:schedule};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
