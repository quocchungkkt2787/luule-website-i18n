/* Haravan LL Language V3.8.7 image asset loader (append to existing V3.8.6).
 * Approved VI/EN/ZH image mappings are delivered by the same free Cloudflare
 * static host. This block does not change current language controls or forms.
 */
(function(){
  'use strict';
  if(window.__LL_IMAGE_I18N_LOADER__)return;
  window.__LL_IMAGE_I18N_LOADER__=true;
  function load(){
    var base=String(window.LL_I18N_BASE||'').trim().replace(/\/+$/,'');
    if(!/^https:\/\//i.test(base))return;
    if(document.querySelector('script[data-ll-image-i18n="v1"]'))return;
    var script=document.createElement('script');
    script.src=base+'/i18n/images/switcher.js?v=1';
    script.async=true;
    script.setAttribute('data-ll-image-i18n','v1');
    script.onerror=function(){console.warn('[LL Image I18N] Static image loader unavailable; original images kept.');};
    (document.head||document.documentElement).appendChild(script);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',load,{once:true});
  else load();
})();
