#!/usr/bin/env python3
"""Build public-site translation packs for LL Haravan v3.10 (no private data).

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
import heapq
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
# Shared PUBLIC page titles/breadcrumb labels found during crawl.
SHARED_NAV_LABELS = set()
# Also share excerpts from cards showing related articles on other pages.
SHARED_RELATED_SNIPPETS = set()
USER_AGENT = 'LuuLePublicI18NBuilder/3.0 (+https://vantailuule.vn)'
SCOPE = ('/blogs/', '/pages/', '/products/', '/collections/')
# Important public tools can be absent from the sitemap or from normal HTML links.
# This is a discovery list only: no private/account/quote/tracking pages are fetched.
REQUIRED_PUBLIC_ROUTES = (
    '/pages/tra-cuu-gia-cuoc-van-chuyen',
    '/blogs/van-chuyen-bac-nam',
    '/blogs/van-chuyen-tphcm-mien-trung',
    '/blogs/xe-tai-cho-hang-di-tinh',
)

REJECT = ('/pages/customer', '/pages/customer/', '/account', '/admin', '/cart', '/checkout', '/apps/', '/search', '/api/', '/cdn/', '/pages/ll-customer')
SKIP_TAGS = {'style', 'script', 'noscript', 'template', 'svg', 'canvas', 'iframe', 'pre', 'code', 'textarea'}
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


def crawl_priority(url):
    """Prioritize *all* missing packs before already-published pages.

    The earlier (tier, missing) ordering always placed every blog after
    service/product pages; with a 450-page budget, missing blog packs could
    remain unreachable indefinitely. Do not change existing pack content.
    """
    tier, route = priority(url)
    if tier <= 1:
        return (0, tier, route)
    existing = (PUBLIC / (route_id(urlsplit(url).path) + '.json')).exists()
    return (2 if existing else 1, tier, route)


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


def collect_text_from_html(content, route=None):
    soup=BeautifulSoup(content,'html.parser')
    root=soup.body
    if not root:return set(),set()
    # Harvest public article summaries before deleting body widgets. Haravan
    # related cards may show meta-description or a shortened first paragraph.
    # These are PUBLIC copy only; never include tracking/customer forms.
    if route and route.startswith('/blogs/'):
        for meta in soup.select('head meta[name="description"],head meta[property="og:description"]'):
            desc=norm(meta.get('content',''))
            if 30<=len(desc)<=1200 and translatable(desc):
                SHARED_RELATED_SNIPPETS.add(desc)
        article_root=root.select_one('article .article-content, article .content, '
                                     '.article-content, .blog-article, '
                                     '.article-body, [itemprop="articleBody"]')
        if article_root:
            for para in article_root.select('p')[:3]:
                snippet=norm(para.get_text(' ',strip=True))
                if 60<=len(snippet)<=1400 and translatable(snippet):
                    SHARED_RELATED_SNIPPETS.add(snippet)
    for q in root.select(SKIP_SELECTOR):q.decompose()
    for q in root.find_all(SKIP_TAGS):q.decompose()
    strings=set()
    # A page's breadcrumb often contains titles from *other* URLs. Build an
    # incremental navigation pack so any page can translate these labels.
    for item in root.select(
        '.breadcrumb,.breadcrumbs,.breadcrumb-wrap,.breadcrumb-wrapper,'
        '.breadcrumb-area,[aria-label="breadcrumb"],h1'
    ):
        label=norm(item.get_text(' ',strip=True))
        if label and len(label)<=160 and translatable(label):
            SHARED_NAV_LABELS.add(label)
        if item.name!='h1':
            for sub in item.stripped_strings:
                label=norm(str(sub))
                if label and len(label)<=160 and translatable(label):
                    SHARED_NAV_LABELS.add(label)
    # Related cards and all public article links may show on many other routes.
    # Add short visible titles to shared.json (never article bodies, forms or
    # customer/account data). Exact matches only in the browser.
    for link in root.select('a[href^="/blogs/"],a[href^="https://vantailuule.vn/blogs/"]'):
        title=norm(link.get_text(' ',strip=True))
        if 2 < len(title) <= 180 and translatable(title):
            SHARED_NAV_LABELS.add(title)
    # Related-article cards are cross-page content and often lazy-loaded.
    # They may not exist in the current route's pack even after that page
    # has been translated. Keep only short public visitor-facing excerpts.
    for block in root.select(
        '[class*="related" i], [id*="related" i],'
        '[class*="recommend" i], [id*="recommend" i]'
    ):
        for n in block.find_all(string=True):
            if isinstance(n, Comment) or n.parent.name in SKIP_TAGS:
                continue
            label=norm(str(n))
            if 2 < len(label) <= 450 and translatable(label):
                SHARED_RELATED_SNIPPETS.add(label)
    # Templates can call their carousel "list-article", "blog-item",
    # "owl-item" etc., rather than "related". Include visible excerpts from
    # PUBLIC article cards identified by a blog link plus a thumbnail.
    for card in root.select(
        '[class*="article" i], [class*="blog" i], [class*="post" i],'
        '[class*="news" i], [class*="owl-item" i], [class*="swiper-slide" i]'
    ):
        if not card.find('img'):
            continue
        if not card.find('a', href=lambda h: h and '/blogs/' in h):
            continue
        if len(norm(card.get_text(' ',strip=True)))>1000:
            continue
        for text in card.find_all(string=True):
            if isinstance(text,Comment) or not text.parent or text.parent.name in SKIP_TAGS:
                continue
            if text.parent.name in ('a','h1','h2','h3','h4','h5','h6'):
                continue
            snippet=norm(str(text))
            if 35<=len(snippet)<=500 and translatable(snippet):
                SHARED_RELATED_SNIPPETS.add(snippet)
    for n in root.find_all(string=True):
        if isinstance(n, Comment):continue
        if n.parent and n.parent.name not in {'script','style','textarea'} and translatable(str(n)):
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

    # Process public pages and important tools first. Discover all sitemap URLs
    # but do not quietly claim that URLs beyond the configured limit are done.
    # The workflow can process more in future batches; previous packs remain.
    budget=max(1,min(max_pages,1500))
    # Carry over previously discovered but unvisited routes, including
    # linked blog pages absent from the sitemap. coverage.json contains only
    # public routes collected by previous successful crawling.
    previous=cached_json(PUBLIC/'coverage.json', {})
    known_unvisited=set()
    for path in previous.get('unvisited_examples', []):
        url=canonical(BASE+str(path))
        if valid_url(url):known_unvisited.add(url)
    initial={BASE+'/'} | seeds | required_urls | known_unvisited
    # A priority heap matters: newly discovered *missing* links must jump
    # ahead of already-published URLs, not wait at the end of a 940-URL queue.
    queue=[(crawl_priority(url),url) for url in initial]
    heapq.heapify(queue)
    queued=set(initial)
    visited=set(); result={}; errors=[]
    browser=None;playwright=None;context=None
    if use_browser:
        from playwright.sync_api import sync_playwright
        playwright=sync_playwright().start()
        browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(locale='vi-VN',viewport={'width':1380,'height':900})
    try:
        while queue and len(visited)<budget:
            _, candidate=heapq.heappop(queue)
            url=canonical(candidate)
            if url in visited or not valid_url(url):
                continue
            visited.add(url)
            texts=set();links=set();issues=[]
            request_ok=False; browser_ok=False

            # Haravan can sometimes reject Python HTTP clients even when the
            # public webpage opens in Chrome. The browser MUST get a chance
            # to fetch the page even if the HTTP request raises an exception.
            try:
                html,final=fetch(session,url)
                if not valid_url(final) or page_key(final)!=page_key(url):
                    raise ValueError('HTTP redirected to '+final)
                html_texts,html_links=collect_text_from_html(html,route=page_key(url))
                if not html_texts:
                    raise ValueError('HTTP page has no readable public text')
                texts |= html_texts
                links |= html_links
                request_ok=True
            except Exception as ex:
                issues.append('HTTP: '+str(ex)[:160])

            # Render key interactive pages fully; for other pages, use the
            # browser only when the normal HTTP fetch failed. This prevents
            # long 850-page crawls from spending an hour on every static blog.
            route=page_key(url)
            render_needed=(route=='/' or route.startswith('/pages/') or
                           route.startswith('/collections/') or not request_ok)
            if context and render_needed:
                page=context.new_page()
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=35000)
                    if not valid_url(page.url) or page_key(page.url)!=route:
                        raise ValueError('browser redirected to '+page.url)
                    page.wait_for_timeout(1400)
                    browser_texts,browser_links=collect_text_from_html(page.content(),route=page_key(url))
                    if not browser_texts:
                        raise ValueError('browser page has no readable public text')
                    # Do not treat bot challenges or not-found pages as copy.
                    probe=' '.join(browser_texts).lower()
                    if ('just a moment' in probe and 'verify you are human' in probe):
                        raise ValueError('browser reached a bot challenge')
                    texts |= browser_texts
                    links |= browser_links
                    browser_ok=True
                except Exception as ex:
                    issues.append('Browser: '+str(ex)[:160])
                finally:
                    page.close()

            if texts:
                result[route]=texts
                print(f'{len(result):>3} {route}: {len(texts)} public segments'+
                      (' (browser fallback)' if browser_ok and not request_ok else ''),
                      flush=True)
                for link in sorted(links,key=crawl_priority):
                    if link not in visited and link not in queued and valid_url(link):
                        heapq.heappush(queue,(crawl_priority(link),link))
                        queued.add(link)
                # Log degraded collection separately without marking a public
                # page as missing when its browser fallback succeeded.
                if issues:
                    print('Fetch note:',url,'; '.join(issues),flush=True)
            else:
                details='; '.join(issues) or 'no public text extracted'
                print('Page skipped:',url,details,flush=True)
                errors.append({'url':url,'error':details[:350]})
            time.sleep(rate)
    finally:
        if browser:browser.close()
        if playwright:playwright.stop()

    missing_required=sorted(path for path in REQUIRED_PUBLIC_ROUTES if path not in result)
    unvisited=sorted(queued-visited,key=crawl_priority)
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
        'unvisited_without_existing_pack':sum(
            not (PUBLIC / (route_id(urlsplit(u).path)+'.json')).exists()
            for u in unvisited),
    }
    print('CRAWL COVERAGE:',json.dumps({k:v for k,v in crawl_pages.last_stats.items()
                                       if k!='skipped_or_failed'},ensure_ascii=False),flush=True)
    if missing_required:
        # Report missing pages explicitly but retain successful work, instead
        # of discarding an hour of translations and failing before git commit.
        print('WARNING: required public pages not crawled:',
              ', '.join(missing_required),flush=True)
        print('Review coverage.json for HTTP/browser errors; missing pages '
              'are NOT counted as translated or covered.',flush=True)
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
    # Cross-page breadcrumbs and RELATED CARD EXCERPTS must be translated even
    # when the visible snippet comes from <meta> or a truncated lazy carousel
    # and therefore is not a normal text node on the current article page.
    public_shared=SHARED_NAV_LABELS | SHARED_RELATED_SNIPPETS
    all_candidates={s for group in pages.values() for s in group} | public_shared
    missing_set={s for s in all_candidates if s not in cache or
                 not isinstance(cache[s],dict) or
                 not all(cache[s].get(k) for k in ('en','zh'))}
    # Prioritize completing the homepage, then pages closest to full coverage.
    # Unlike lexical sorting of 19k strings, this can publish complete packs
    # early without requiring every page to be finished first.
    route_order=sorted(pages, key=lambda r: (0 if r=='/' else 1,
                     sum(x in missing_set for x in pages[r]),r))
    missing=[]; scheduled=set()
    # Homepage first, then *shared* excerpts/navigation (the same excerpts
    # appear across many articles), then the remaining page-specific strings.
    for r in ['/']:
        for item in sorted(pages.get(r,())):
            if item in missing_set and item not in scheduled:
                missing.append(item);scheduled.add(item)
    for item in sorted(public_shared):
        if item in missing_set and item not in scheduled:
            missing.append(item);scheduled.add(item)
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
    # Incrementally publish a PUBLIC navigation/related-snippet fallback pack.
    # Use previously verified entries when the 450-page crawl budget excludes
    # other URLs. Never include private forms, full article text or credentials.
    shared_path=PUBLIC/'shared.json'
    previous_shared=cached_json(shared_path,{})
    shared_texts=dict(previous_shared.get('texts') or {}) if isinstance(previous_shared,dict) else {}
    for key in (SHARED_NAV_LABELS | SHARED_RELATED_SNIPPETS):
        row=cache.get(key)
        if isinstance(row,dict) and all(isinstance(row.get(code),str) and row[code].strip()
                                        for code in ('en','zh')):
            shared_texts[key]={'en':row['en'],'zh':row['zh']}
    # Do not publish an empty map if the crawl was temporarily degraded.
    if shared_texts:
        save_json(shared_path,{'version':3,'route':'*','texts':shared_texts})
        print('Shared public titles, breadcrumbs and related snippets:',len(shared_texts),flush=True)
    released=0;partial=0;pending_report=[]
    for route,items in pages.items():
        missing_entries=[x for x in items if x not in cache or not all(cache[x].get(y) for y in ('en','zh'))]
        old_file=PUBLIC/(route_id(route)+'.json')
        old_pack=cached_json(old_file,{})
        # Publish available translated segments on EVERY successful batch,
        # not only when the last untranslated text on this route is finished.
        # Otherwise a site with 51 pending pages can show no visible progress
        # despite multiple green GitHub workflow runs.
        mapping=dict(old_pack.get('texts') or {}) if isinstance(old_pack,dict) and old_pack.get('version')==3 and old_pack.get('route')==route else {}
        mapping.update({k:cache[k] for k in sorted(items) if k in cache and
                        isinstance(cache[k],dict) and
                        all(isinstance(cache[k].get(y),str) and cache[k][y].strip()
                            for y in ('en','zh'))})
        if missing_entries:
            partial+=1
            pending_report.append({'route':route,'missing_count':len(missing_entries),
                                   'examples':sorted(missing_entries)[:4]})
            print('PARTIAL (incrementally published):',route,
                  'translated',len(mapping),'missing',len(missing_entries),flush=True)
        if mapping:
            out={'version':3,'route':route,'texts':mapping,
                 'complete':not bool(missing_entries),
                 'missing_count':len(missing_entries)}
            save_json(old_file,out)
            released+=1
        else:
            print('NO TRANSLATED STRINGS YET:',route,flush=True)
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
        sample_related='<html><body><section class="related-articles"><h3>BÀI VIẾT LIÊN QUAN</h3><p>Đây là đoạn mô tả bài viết có ích.</p></section></body></html>'
        collect_text_from_html(sample_related)
        assert 'Đây là đoạn mô tả bài viết có ích.' in SHARED_RELATED_SNIPPETS
        no_related_class='<html><body><div class="blog-item"><a href="/blogs/goc-tu-van/mau"><img src="/a.jpg"/>Tieu de</a><p>Đây là đoạn giới thiệu đầy đủ về dịch vụ vận chuyển đường sắt cho khách hàng.</p></div></body></html>'
        collect_text_from_html(no_related_class)
        assert 'Đây là đoạn giới thiệu đầy đủ về dịch vụ vận chuyển đường sắt cho khách hàng.' in SHARED_RELATED_SNIPPETS
        sample_meta='<html><head><meta name="description" content="Bài viết hướng dẫn vận chuyển hàng hóa an toàn từ Hà Nội vào Sài Gòn theo quy trình rõ ràng và tiết kiệm chi phí."></head><body><article><p>Nội dung minh họa.</p></article></body></html>'
        collect_text_from_html(sample_meta,route='/blogs/van-chuyen/mau')
        assert 'Bài viết hướng dẫn vận chuyển hàng hóa an toàn từ Hà Nội vào Sài Gòn theo quy trình rõ ràng và tiết kiệm chi phí.' in SHARED_RELATED_SNIPPETS
        assert translatable('Vận chuyển hàng hóa Bắc Nam')
        key=route_id('/pages/tra-cuu-gia-cuoc-van-chuyen')
        assert key=='pages__tra-cuu-gia-cuoc-van-chuyen', key
        assert priority(BASE+'/pages/tra-cuu-gia-cuoc-van-chuyen') < priority(BASE+'/blogs/x/y')
        missing_blog=BASE+'/blogs/ll-i18n-missing-pack-selftest-never-published'
        assert crawl_priority(missing_blog)[0] == 1
        assert crawl_priority(BASE+'/blogs/van-chuyen-tphcm-mien-trung')[0] == 0
        assert valid_url(BASE+'/pages/tra-cuu-gia-cuoc-van-chuyen')
        assert not valid_url(BASE+'/pages/customer')
        assert all(y in {'en','zh'} for y in ('en','zh'))
        assert max(1,min(450,1500)) == 450
        print('SELF-TEST PASS: public parsing, required route, output filename and crawl priority. No output published.')
        return
    session=requests.Session();session.headers.update({'User-Agent':USER_AGENT})
    pages=crawl_pages(session,args.max_pages,use_browser=args.browser)
    if not pages:raise RuntimeError('No public pages found. Check sitemap and network first; not publishing empty data.')
    released,pending=build(pages,args.max_new)
    stats=getattr(crawl_pages,'last_stats',{})
    # Distinguish pages processed this batch from packs published over all
    # successful batches; this also keeps the scheduled backlog gate accurate.
    known_urls=set(BASE+r for r in pages)
    missing_pages=set()
    for url in known_urls:
        if not (PUBLIC / (route_id(page_key(url))+'.json')).exists():
            missing_pages.add(page_key(url))
    for url in (BASE+path for path in REQUIRED_PUBLIC_ROUTES):
        if not (PUBLIC / (route_id(page_key(url))+'.json')).exists():
            missing_pages.add(page_key(url))
    for failure in stats.get('skipped_or_failed',[]):
        u=failure['url']
        if not (PUBLIC / (route_id(page_key(u))+'.json')).exists():
            missing_pages.add(page_key(u))
    # Because the crawler always starts with sitemap URLs, unvisited missing
    # packs can be counted without claiming they have already been translated.
    missing_count=len(missing_pages)+int(stats.get('unvisited_without_existing_pack',0))
    stats['missing_packs_in_discovered_routes']=missing_count
    stats['published_pack_files_total']=sum(1 for f in PUBLIC.glob('*.json')
        if f.name not in ('audit.json','coverage.json','manifest.json','shared.json'))
    save_json(PUBLIC/'coverage.json',stats)
    manifest=cached_json(PUBLIC/'manifest.json',{})
    manifest['discovered_public_urls']=stats.get('discovered_public_urls',len(pages))
    manifest['uncrawled_public_urls']=stats.get('unvisited_count',0)
    manifest['crawl_failures']=len(stats.get('skipped_or_failed',[]))
    manifest['required_pages_found']=stats.get('required_pages_found',[])
    manifest['published_pack_files_total']=stats['published_pack_files_total']
    manifest['pages_pending']=missing_count
    manifest['site_coverage_complete']=(missing_count==0)
    save_json(PUBLIC/'manifest.json',manifest)
    print(f'Done. Full-language pages: {released}; incomplete pages held: {pending}.')

if __name__=='__main__':main()
