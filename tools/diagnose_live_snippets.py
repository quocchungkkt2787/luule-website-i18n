#!/usr/bin/env python3
"""Read-only, anonymous diagnostic of PUBLIC search and related snippets.

Does not log in, submit forms, alter website content, or collect customer data.
Prints public browser/runtime/CDN state to the GitHub Actions log.
"""
import json
from playwright.sync_api import sync_playwright

URLS = [
    'https://vantailuule.vn/search?type=article&q=v%E1%BA%ADn+t%E1%BA%A3i+%C4%91%C6%B0%E1%BB%9Dng+s%E1%BA%AFt',
    'https://vantailuule.vn/blogs/chinh-sach-cong-ty/thanh-toan'
]
NEEDLES = [
    'Bạn có biết rằng vận chuyển đường sắt',
    'Công ty TNHH Vận Tải Lưu Lê tôn trọng quyền riêng tư',
]
ROUTES = [
    '/blogs/van-chuyen-bac-nam/van-chuyen-duong-sat-bac-nam',
    '/blogs/chinh-sach-cong-ty/bao-mat-thong-tin'
]
GET_STATE = """async ({needles,routes})=>{
  const plugin=window.LLGlobalI18N;
  const state=plugin&&plugin.state?plugin.state():null;
  let pack=null,previewData=null;
  if(state&&state.base){
    try{
      const url=state.base+'/i18n/previews.json';
      const response=await fetch(url,{mode:'cors',credentials:'omit',cache:'no-store'});
      if(response.ok){
        const data=await response.json();
        previewData=data;
        pack={status:response.status,version:data.version,routeCount:Object.keys(data.routes||{}).length,
          selected:routes.map(route=>({route,found:!!(data.routes||{})[route],
            count:Object.keys((data.routes||{})[route]||{}).length}))};
      }else pack={status:response.status};
    }catch(e){pack={error:String(e).slice(0,160)};}
  }
  const hits=[];
  const all=Array.from(document.querySelectorAll('main p,main div,section p,.related-articles p,.related-posts p,.blog-item p'));
  for(const needle of needles){
    const candidate=all.filter(el=>el.textContent.includes(needle))
      .sort((a,b)=>a.textContent.length-b.textContent.length)[0];
    if(!candidate){hits.push({needle,found:false});continue;}
    let chain=[],holder=candidate;
    for(let k=0;k<12&&holder;k++,holder=holder.parentElement){
      if(!holder.tagName)break;
      const links=Array.from(holder.querySelectorAll('a[href*="/blogs/"]'));
      chain.push({tag:holder.tagName,cls:String(holder.className||'').slice(0,80),
        chars:holder.textContent.length,images:holder.querySelectorAll('img').length,
        articleLinks:[...new Set(links.map(a=>a.getAttribute('href')))].slice(0,3)});
    }
    hits.push({needle,found:true,tag:candidate.tagName,
      cls:String(candidate.className||'').slice(0,80),display:candidate.textContent.slice(0,380),
      chain:chain.slice(0,8)});
  }
  let audit=null;
  try{audit=plugin&&plugin.auditRelatedExcerpts?plugin.auditRelatedExcerpts():null;}
  catch(e){audit={error:String(e).slice(0,140)};}
  const canon=value=>String(value||'').trim().toLocaleLowerCase('vi')
    .replace(/[\\u200B-\\u200D\\u2060\\uFEFF]/gu,'')
    .replace(/[\\s.,;:!?…'"“”‘’\\-–—()[\\]{}\\/\\\\]+/gu,'');
  if(audit&&Array.isArray(audit.missing))audit.missing=audit.missing.slice(0,10)
    .map(row=>{
      const source=String(row.source||''),k=canon(source);
      const scope=previewData&&previewData.routes&&previewData.routes[row.linkedRoute]||{};
      const ranked=Object.keys(scope).map(candidate=>{
        const c=canon(candidate);let overlap=0;
        while(overlap<Math.min(c.length,k.length)&&c[overlap]===k[overlap])overlap++;
        return {source:String(candidate).slice(0,200),
          sourceLength:c.length,visibleLength:k.length,sharedPrefix:overlap,
          prefixRatio:Math.round(100*overlap/Math.min(c.length,k.length))};
      }).sort((a,b)=>b.sharedPrefix-a.sharedPrefix).slice(0,3);
      return {source:source.slice(0,520),sourceLength:k.length,
        linkedRoute:row.linkedRoute,ranked};
    });
  const summaries=[];
  for(const targetRoute of routes){
    const anchors=Array.from(document.querySelectorAll('a[href*="/blogs/"]')).filter(a=>{
      try{return new URL(a.href,location.href).pathname===targetRoute;}catch(e){return false;}
    });
    for(const anchor of anchors.slice(0,2)){
      let holder=anchor;
      for(let depth=0;holder&&depth<12;depth++,holder=holder.parentElement){
        const p=holder.querySelector('p,[class*="excerpt" i],[class*="description" i]');
        if(p&&holder.querySelector('img')&&holder.textContent.length<2200){
          summaries.push({targetRoute,holder:holder.tagName,depth,
            className:String(holder.className||'').slice(0,90),
            paragraph:p.textContent.slice(0,650),paragraphHtml:p.innerHTML.slice(0,750)});
          break;
        }
      }
    }
  }
  return {state,pack,hits,audit,summaries,htmlLang:document.documentElement.lang,
    active:document.documentElement.getAttribute('data-ll-i18n-active'),
    imageI18N:window.LLImageI18N&&window.LLImageI18N.state&&window.LLImageI18N.state()};
}"""
def main():
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            for address in URLS:
                ctx=browser.new_context(locale='en-US',viewport={'width':1440,'height':900})
                ctx.add_init_script("""try{localStorage.setItem('ll_website_lang_v3','en')}catch(e){}""")
                page=ctx.new_page()
                errors=[]
                page.on('pageerror',lambda e: errors.append(str(e)[:180]))
                try:
                    response=page.goto(address,wait_until='domcontentloaded',timeout=45000)
                    page.wait_for_timeout(9000)
                    snapshot=page.evaluate(GET_STATE,{'needles':NEEDLES,'routes':ROUTES})
                    result={'url':address,'http':response.status if response else None,
                            'finalUrl':page.url,'snapshot':snapshot,'pageErrors':errors[:5]}
                except Exception as error:
                    result={'url':address,'error':str(error)[:260]}
                print('PUBLIC_SNIPPET_DIAG='+json.dumps(result,ensure_ascii=False),flush=True)
                ctx.close()
        finally:
            browser.close()
if __name__=='__main__':
    main()
