#!/usr/bin/env python3
"""Build public-site translation packs for LL Haravan v3 (no private data).

Only requests public pages and only publishes site copy. Does not access
customer accounts, tracking records, quote data, or input values.
Requires network access when executed in GitHub Actions (not in the ChatGPT sandbox).
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import deque
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup, Comment

BASE = 'https://vantailuule.vn'
ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / 'translation-cache.json'
PUBLIC = ROOT / 'public' / 'i18n'
USER_AGENT = 'LuuLePublicI18NBuilder/3.0 (+https://vantailuule.vn)'
SCOPE = ('/blogs/', '/pages/', '/products/', '/collections/')
# Important public tools can be absent from the sitemap or from normal HTML links.
# This is a discovery list only: no private/account/quote/tracking pages are fetched.
REQUIRED_PUBLIC_ROUTES = ('/pages/tra-cuu-gia-cuoc-van-chuyen',)

REJECT = ('/pages/customer', '/pages/customer/', '/account', '/admin', '/cart', '/checkout', '/apps/', '/search', '/api/', '/cdn/', '/pages/ll-customer')
SKIP_TAGS = {'style', 'script', 'noscript', 'template', 'svg', 'canvas', 'iframe', 'pre', 'code', 'textarea', 'option'}
SKIP_SELECTOR = '[data-ll-private], [data-ll-no-translate], #ll-ai-chat, #ll-language-v3, #ll-language-v3-notice, .subiz-widget, #fb-root, #at4-share, #at4-soc, #at4-share2, #at4-soc2, [id^="subiz"], [translate="no"]'
ATTRS = ('placeholder', 'title', 'aria-label', 'alt')
LETTER = re.compile(r'[a-zA-Z\u00C0-\u024F\u1E00-\u1EFF\u3400-\u9FFF]')


def norm(value):
    return ' '.join(unicodedata.normalize('NFC', value or '').split())


def translatable(s):
    v = norm(s)
    # Internal URL paths and asset paths are identifiers, not translatable copy.
    # Previously strings such as /blogs/goc-tu-van/... were marked untranslated
    # and could prevent an otherwise complete page from being published.
    if re.fullmatch(r'/[^\s<>]+', v):
        return False
    # Proper-noun addresses and website references from the public audit report
    # are identifiers, not prose. Preserve them as written across languages.
    if re.fullmatch(r'Website:\s*(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}', v, re.I):
        return False
    if re.fullmatch(r'Airport Blvd,\s*Singapore', v, re.I):
        return False
    if re.match(r'^Parkway Parade:\s*\d+\s+Marine Parade\b', v, re.I):
        return False
    return (len(v) > 1 and bool(LETTER.search(v))
        and not re.match(r'^(https?://|www\.|mailto:|tel:)', v, re.I)
        and not re.fullmatch(r'[\w.+-]+@[\w.-]+\.[a-z]{2,}', v, re.I)
        and not re.fullmatch(r'(VẬN TẢI LƯU LÊ|Vận Tải Lưu Lê|Lưu Lê|LL|VNĐ)', v, re.I))


def valid_url(url):
    p=urlsplit(url)
    if p.netloc.lower().removeprefix('www.') != 'vantailuule.vn':
        return False
    path=p.path or '/'
    if path=='/':return True
    return path.startswith(SCOPE) and not path.startswith(REJECT)


def canonical(url):
    p=urlsplit(urljoin(BASE+'/',url))
    path=p.path.rstrip('/') or '/'
    return BASE+path


def route_id(path):
    path=unquote(path).strip('/') or 'home'
    return re.sub(r'[^a-zA-Z0-9_-]','_',path.replace('/','__'))


def priority(url):
    """Put real site tools, pricing, and service pages before long blog lists."""
    path = urlsplit(url).path
    if path == '/':
        return (0, path)
    if path in REQUIRED_PUBLIC_ROUTES:
        return (1, path)
    if path.startswith('/pages/'):
        return (2, path)
    if path.startswith('/collections/'):
        return (3, path)
    if path.startswith('/products/'):
        return (4, path)
    return (5, path)


def page_key(url):
    return (urlsplit(url).path.rstrip('/') or '/')


def cached_json(path, default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return default


def save_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp.replace(path)


def fetch(session,url):
    r=session.get(url,timeout=25,headers={'Accept':'text/html,application/xml;q=0.9,*/*;q=0.8'})
    r.raise_for_status()
    return r.text,r.url


def get_sitemap_urls(session, max_depth=3):
    found=set(); visited=set(); queue=deque([(BASE+'/sitemap.xml',0)])
    while queue:
        uri,depth=queue.popleft()
        if uri in visited or depth>max_depth:continue
        visited.add(uri)
        try:
            raw,_=fetch(session,uri)
            root=ElementTree.fromstring(raw)
        except Exception as ex:
            print('sitemap skipped:',uri,str(ex)[:80]);continue
        locs=[norm(n.text) for n in root.iter() if n.tag.lower().endswith('loc') and n.text]
        if root.tag.lower().endswith('sitemapindex'):
            for x in locs:
                if x.startswith(BASE) and ('sitemap' in x):queue.append((x,depth+1))
        else:
            for x in locs:
                if valid_url(x):found.add(canonical(x))
    return found


def collect_text_from_html(content):
    soup=BeautifulSoup(content,'html.parser')
    root=soup.body
    if not root:return set(),set()
    for q in root.select(SKIP_SELECTOR):q.decompose()
    for q in root.find_all(SKIP_TAGS):q.decompose()
    strings=set()
    for n in root.find_all(string=True):
        if isinstance(n, Comment):continue
        if n.parent and n.parent.name not in {'script','style','textarea','option'} and translatable(str(n)):
            strings.add(norm(str(n)))
    for el in root.find_all(True):
        for a in ATTRS:
            if el.has_attr(a) and translatable(str(el[a])): strings.add(norm(str(el[a])))
        if el.name=='input' and el.get('type','').lower() in ('submit','button','reset'):
            if translatable(el.get('value','')):strings.add(norm(el['value']))
    links=set()
    for el in root.find_all('a',href=True):
        href=str(el['href']).strip()
        if href.startswith(('#','javascript:','mailto:','tel:')):continue
        link=canonical(href)
        if valid_url(link):links.add(link)
    return strings,links


def crawl_pages(session,max_pages,rate=0.3,use_browser=False):
    seeds=get_sitemap_urls(session)
    print('Public URLs in sitemap:',len(seeds), flush=True)
    required_urls={canonical(BASE+path) for path in REQUIRED_PUBLIC_ROUTES}
    for url in required_urls:
        if not valid_url(url):
            raise ValueError('Unsafe required URL: '+url)

    # Keep the existing workflow's page budget, but always reserve sufficient
    # capacity for every sitemap URL plus the homepage and the required tool(s).
    # An extra 30 slots make room for public links absent from the sitemap.
    budget=max(max_pages,len(seeds)+len(required_urls)+31)
    # A hard safety bound avoids unintentional extremely long GitHub runs.
    if budget>1500:
        print('WARNING: page discovery exceeds safety budget 1500; '
              'the audit will report unvisited URLs.',flush=True)
        budget=1500

    initial={BASE+'/'} | seeds | required_urls
    queue=deque(sorted(initial,key=priority))
    queued=set(queue)
    visited=set(); result={}; errors=[]
    browser=None;playwright=None;context=None
    if use_browser:
        from playwright.sync_api import sync_playwright
        playwright=sync_playwright().start()
        browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(locale='vi-VN',viewport={'width':1380,'height':900})
    try:
        while queue and len(visited)<budget:
            url=canonical(queue.popleft())
            if url in visited or not valid_url(url):
                continue
            visited.add(url)
            try:
                html,final=fetch(session,url)
                # Do not publish home-page text under an unrelated page URL
                # after a redirect (e.g. a page deleted from Haravan).
                if not valid_url(final) or page_key(final)!=page_key(url):
                    raise ValueError('redirected to '+final)
                texts,links=collect_text_from_html(html)
                if use_browser and context:
                    page=context.new_page()
                    try:
                        page.goto(url,wait_until='domcontentloaded',timeout=35000)
                        page.wait_for_timeout(1700)
                        br_texts,br_links=collect_text_from_html(page.content())
                        texts |= br_texts
                        links |= br_links
                    except Exception as ex:
                        print('Browser render skipped:',url,str(ex)[:110],flush=True)
                    finally:
                        page.close()
                if not texts:
                    raise ValueError('public page had no readable text')
                result[page_key(url)]=texts
                print(f'{len(result):>3} {page_key(url)}: {len(texts)} public segments',flush=True)
                for link in sorted(links,key=priority):
                    if link not in visited and link not in queued and valid_url(link):
                        queue.append(link)
                        queued.add(link)
            except Exception as ex:
                print('Page skipped:',url,str(ex)[:140],flush=True)
                errors.append({'url':url,'error':str(ex)[:200]})
            time.sleep(rate)
    finally:
        if browser:browser.close()
        if playwright:playwright.stop()

    missing_required=sorted(path for path in REQUIRED_PUBLIC_ROUTES if path not in result)
    unvisited=sorted(queued-visited,key=priority)
    crawl_pages.last_stats={
        'sitemap_urls':len(seeds),
        'discovered_public_urls':len(queued),
        'successful_public_pages':len(result),
        'skipped_or_failed':errors,
        'unvisited_count':len(unvisited),
        'unvisited_examples':[urlsplit(u).path for u in unvisited[:40]],
        'required_pages_missing':missing_required,
        'required_pages_found':[r for r in REQUIRED_PUBLIC_ROUTES if r in result],
        'page_budget':budget,
    }
    print('CRAWL COVERAGE:',json.dumps({k:v for k,v in crawl_pages.last_stats.items()
                                       if k!='skipped_or_failed'},ensure_ascii=False),flush=True)
    if missing_required:
        # Missing core pages must NEVER be reported as "448/448 success".
        raise RuntimeError('Required public page(s) not crawled: '+', '.join(missing_required))
    return result


def init_argos():
    import argostranslate.package as pkg
    import argostranslate.translate as translator
    installed={(x.from_code,x.to_code) for x in pkg.get_installed_packages()}
    for source,target in [('vi','en'),('en','zh')]:
        if (source,target) in installed:continue
        pkg.update_package_index()
        available=pkg.get_available_packages()
        m=next((x for x in available if x.from_code==source and x.to_code==target),None)
        if not m:raise RuntimeError(f'No free Argos language model for {source}->{target}.')
        print('Installing open-source model',source,target,flush=True)
        pkg.install_from_path(m.download())
    return translator


def build(pages,max_new=100000,demo=False):
    cache=cached_json(STORE,{})
    if not isinstance(cache,dict):cache={}
    missing_set={s for group in pages.values() for s in group if s not in cache or not all(cache[s].get(k) for k in ('en','zh'))}
    # Prioritize completing the homepage, then pages closest to full coverage.
    # Unlike lexical sorting of 19k strings, this can publish complete packs
    # early without requiring every page to be finished first.
    route_order=sorted(pages, key=lambda r: (0 if r=='/' else 1,
                     sum(x in missing_set for x in pages[r]),r))
    missing=[]; scheduled=set()
    for r in route_order:
        for item in sorted(pages[r]):
            if item in missing_set and item not in scheduled:
                missing.append(item);scheduled.add(item)
    print('All unique strings:',len({s for group in pages.values() for s in group}))
    print('Missing translations:',len(missing))
    engine=None
    if missing and not demo:engine=init_argos()
    created=0
    for source in missing:
        if created>=max_new:break
        try:
            if demo:
                en='[EN] '+source
                zh='[ZH] '+source
            else:
                en=engine.translate(source,'vi','en').strip()
                zh=engine.translate(en,'en','zh').strip()
            if not en or not zh:
                print('Empty translation:',source[:50]);continue
            # Do not ship obviously unchanged Vietnamese paragraphs, excluding proper names.
            if len(source)>22 and (norm(en)==source or norm(zh)==source):
                print('Untranslated paragraph:',source[:50]);continue
            cache[source]={'en':en,'zh':zh}
            created+=1
            if created%100==0:
                print('translated:',created,'/',len(missing),flush=True)
                save_json(STORE,cache)
        except Exception as ex:
            print('Translation failed:',source[:45],str(ex)[:70])
    save_json(STORE,cache)
    released=0;partial=0;pending_report=[]
    for route,items in pages.items():
        missing_entries=[x for x in items if x not in cache or not all(cache[x].get(y) for y in ('en','zh'))]
        if missing_entries:
            partial+=1
            # Never serve an outdated pack if the same page was rebuilt incomplete.
            old_file=PUBLIC/(route_id(route)+'.json')
            if old_file.exists():old_file.unlink()
            # Only PUBLIC website snippets appear in this report; no private data.
            pending_report.append({'route':route,'missing_count':len(missing_entries),
                                   'examples':sorted(missing_entries)[:4]})
            print('HOLD (incomplete):',route,len(missing_entries));continue
        mapping={k:cache[k] for k in sorted(items)}
        out={'version':3,'route':route,'texts':mapping}
        save_json(PUBLIC/(route_id(route)+'.json'),out)
        released+=1
    save_json(PUBLIC/'audit.json',{
        'version':3,'pages_seen':len(pages),'pages_published':released,
        'pages_pending':partial,'missing_unique_texts':len({x for p in pages.values()
           for x in p if x not in cache or not all(cache[x].get(k) for k in ('en','zh'))}),
        'pending_pages':sorted(pending_report,key=lambda x:(x['missing_count'],x['route']))
    })
    save_json(PUBLIC/'manifest.json',{
        'version':3,
        'site':BASE,
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'pages_seen':len(pages),'pages_published':released,
        'pages_pending':partial,'unique_public_texts':len({s for group in pages.values() for s in group}),
        'engine':'Argos Translate (free offline open source)',
        'note':'Public Haravan text only; translations are machine-generated and require editorial review. Image text and external apps excluded.'
    })
    return released,partial


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--max-pages',type=int,default=int(os.environ.get('LL_MAX_PAGES',500)))
    ap.add_argument('--max-new',type=int,default=int(os.environ.get('LL_MAX_NEW',100000)))
    ap.add_argument('--browser',action='store_true')
    ap.add_argument('--self-test',action='store_true',help='Validate parsing only; does not write any translation pack')
    args=ap.parse_args()
    PUBLIC.mkdir(parents=True,exist_ok=True)
    if args.self_test:
        sample='<html><body><div id="wrapper"><nav>Trang chủ</nav><h1>Vận chuyển hàng hóa Bắc Nam</h1><p>Chúng tôi vận chuyển hàng hóa bằng đường sắt và đường bộ.</p><input placeholder="Nhập mã vận đơn"/><script>doNotRead()</script></div></body></html>'
        texts,_=collect_text_from_html(sample)
        assert 'Trang chủ' in texts and 'Nhập mã vận đơn' in texts
        assert 'doNotRead()' not in texts
        assert not translatable('/blogs/goc-tu-van/bien-so-56-o-dau')
        assert not translatable('Website: vantaibacnamgiare.com')
        assert not translatable('Website: vantaihuonglan.vn')
        assert not translatable('Airport Blvd, Singapore')
        assert not translatable('Parkway Parade: 80 Marine Parade,')
        assert translatable('Vận chuyển hàng hóa Bắc Nam')
        key=route_id('/pages/tra-cuu-gia-cuoc-van-chuyen')
        assert key=='pages__tra-cuu-gia-cuoc-van-chuyen', key
        assert priority(BASE+'/pages/tra-cuu-gia-cuoc-van-chuyen') < priority(BASE+'/blogs/x/y')
        assert valid_url(BASE+'/pages/tra-cuu-gia-cuoc-van-chuyen')
        assert not valid_url(BASE+'/pages/customer')
        print('SELF-TEST PASS: public parsing, required route, output filename and crawl priority. No output published.')
        return
    session=requests.Session();session.headers.update({'User-Agent':USER_AGENT})
    pages=crawl_pages(session,args.max_pages,use_browser=args.browser)
    if not pages:raise RuntimeError('No public pages found. Check sitemap and network first; not publishing empty data.')
    released,pending=build(pages,args.max_new)
    stats=getattr(crawl_pages,'last_stats',{})
    # Separate coverage of the real website from the subset that was crawled.
    # Do not count pages omitted from the crawl as published/completed.
    save_json(PUBLIC/'coverage.json',stats)
    manifest=cached_json(PUBLIC/'manifest.json',{})
    manifest['discovered_public_urls']=stats.get('discovered_public_urls',len(pages))
    manifest['uncrawled_public_urls']=stats.get('unvisited_count',0)
    manifest['crawl_failures']=len(stats.get('skipped_or_failed',[]))
    manifest['required_pages_found']=stats.get('required_pages_found',[])
    manifest['site_coverage_complete']=(not stats.get('unvisited_count')
         and not stats.get('skipped_or_failed') and pending==0)
    save_json(PUBLIC/'manifest.json',manifest)
    print(f'Done. Full-language pages: {released}; incomplete pages held: {pending}.')

if __name__=='__main__':main()
