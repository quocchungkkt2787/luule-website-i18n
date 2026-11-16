#!/usr/bin/env python3
"""Build a route-specific index of PUBLIC blog previews already translated.

A Haravan search card may display a short HTML-stripped article paragraph.
Its source may be split across nested tags, so exact DOM string matching misses
the translation. Index a small number of canonical public article first
paragraphs by the corresponding linked blog URL, never by visitor search text.
No online AI calls, no private account data, no image edits.
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public' / 'i18n'
DEST = PUBLIC / 'previews.json'
ARTICLE = re.compile(r'^/blogs/[^/]+/[^/]+$')

def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def normalize_search(value):
    value=unicodedata.normalize('NFKD',str(value).lower())
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in value if not unicodedata.combining(c))).strip()


def fallback_sources(route, entries, limit=6):
    """Use existing PUBLIC long paragraphs while the live crawl is queued.

    Limit each blog route to a handful of likely introductory prose segments,
    to avoid downloading entire article dictionaries on every mobile page.
    """
    slug_tokens=set(normalize_search(route.rsplit('/',1)[-1]).split())
    slug_tokens={w for w in slug_tokens if len(w)>3 and w not in
                 {'chuyen','hang','gui','dich','vu','cong','ty','van','tai','sai','gon','trong','giao'}}
    intros=('hiện nay','nằm trong','để đáp ứng','nếu quý khách',
            'bạn đang','công ty','dịch vụ','với','ga ','nhu cầu',
            'dưới đây','khi ','trong những năm','đối với','vận tải')
    candidates=[]
    for source,row in entries.items():
        if not isinstance(source,str) or not 110<=len(source)<=1250:
            continue
        if not isinstance(row,dict) or not all(
            isinstance(row.get(lang),str) and row[lang].strip()
            for lang in ('en','zh')):
            continue
        leading=source.strip().lower()
        if source.count('\n')>2 or '<' in source or '>' in source:
            continue
        words=set(normalize_search(source).split())
        overlap=len(slug_tokens & words)
        score=min(overlap,5)*7
        if leading.startswith(intros):score+=12
        if 170<=len(source)<=600:score+=7
        if any(p in source for p in ('. ', '? ', '! ')):score+=4
        if source.endswith(('...', '…')):score-=3
        candidates.append((score, -abs(len(source)-360), source))
    candidates.sort(reverse=True)
    return [source for _,_,source in candidates[:limit]]


def compact_preview_key(source):
    """Match the browser's public excerpt normalization without ambiguous regex escapes."""
    text=unicodedata.normalize('NFC', str(source)).casefold()
    punctuation=set('.,;:!?…' + chr(39) + chr(34) + '“”‘’-–—()[]{}')
    return ''.join(char for char in text
        if not char.isspace() and char not in punctuation and
        ord(char) not in (47,92,0x200b,0x200c,0x200d,0x2060,0xfeff))

def choose_visible_variant(group):
    """Equivalent HTML spacing variants must not conflict in the browser.

    The rendered visitor text normally has spaces around strong/inline tags.
    Keep the more legible, naturally spaced Vietnamese source for translation.
    Do not merge NON-equivalent strings, even from the same article.
    """
    return max(group,key=lambda pair:(
        len(pair[0].split()),
        sum(c.isspace() for c in pair[0]),
        len(pair[0])
    ))


def dedupe_preview_rows(rows):
    groups={}
    for key,row in rows.items():
        groups.setdefault(compact_preview_key(key),[]).append((key,row))
    result={}
    removed=0
    for group in groups.values():
        source,translated=choose_visible_variant(group)
        result[source]=translated
        removed+=len(group)-1
    return result,removed


def build(directory=PUBLIC):
    # Keep published routes between batches when a page cannot be crawled.
    previous = read(directory / 'previews.json', {})
    routes = dict(previous.get('routes') or {}) if isinstance(previous, dict) else {}
    count = 0
    removed = 0
    for path in directory.glob('blogs__*.json'):
        pack = read(path, {})
        route = pack.get('route')
        if not isinstance(route, str) or not ARTICLE.fullmatch(route):
            continue
        entries = pack.get('texts') or {}
        sources = pack.get('preview_sources') or fallback_sources(route, entries)
        if not isinstance(entries, dict) or not isinstance(sources, list):
            continue
        # Preview variants are stored by the public article crawler; this is
        # intentionally NOT all prose or 933 full article translation packs.
        result = {}
        for source in sources[:24]:
            if not isinstance(source, str) or not 40 <= len(source) <= 1400:
                continue
            row = entries.get(source)
            if isinstance(row, dict) and all(
                isinstance(row.get(lang), str) and row[lang].strip()
                for lang in ('en', 'zh')
            ):
                result[source] = {'en':row['en'], 'zh':row['zh']}
        if result:
            routes[route] = result
            count += 1
    # Existing preview routes from earlier builds can already contain the
    # same source with/without HTML inline spaces. Clean ALL routes, not only
    # those refreshed during this particular crawler batch.
    for route,rows in list(routes.items()):
        if not ARTICLE.fullmatch(route) or not isinstance(rows,dict):
            del routes[route]
            continue
        unique,pruned=dedupe_preview_rows(rows)
        routes[route]=unique
        removed+=pruned
    return {'version':3, 'route':'*previews', 'routes':routes,
            'route_count':len(routes), 'refreshed_route_count':count,
            'equivalent_duplicates_removed':removed,
            'note':'Only PUBLIC first paragraphs/SEO descriptions. Equivalent HTML spacing variants are deduplicated; no private data.'}

def self_test():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        dest = Path(tmp)
        source = 'Hiện nay, nhu cầu vận chuyển hàng hóa qua đường sắt đang tăng rất nhanh ở Việt Nam.'
        (dest / 'blogs__a__b.json').write_text(json.dumps({
            'version':3, 'route':'/blogs/a/b',
            'texts':{source:{'en':'Rail freight demand is rising.',
                           'zh':'铁路货运需求正在增长。'}},
            'preview_sources':[source]
        }, ensure_ascii=False),encoding='utf-8')
        data=build(dest)
        assert data['route_count']==1 and data['routes']['/blogs/a/b'][source]['en']
        (dest / 'blogs__a__private.json').write_text(json.dumps({
            'route':'/account/private',
            'preview_sources':[source],
            'texts':{source:{'en':'private','zh':'private'}}
        },ensure_ascii=False),encoding='utf-8')
        assert build(dest)['route_count']==1
        (dest / 'blogs__a__old.json').write_text(json.dumps({
            'route':'/blogs/a/old',
            'texts':{'Hiện nay, nhu cầu vận chuyển hàng hóa đường sắt qua Việt Nam đang tăng nhanh. '+
                     'Vận tải đường sắt là giải pháp chi phí hợp lý cho các doanh nghiệp.':
                     {'en':'Rail demand is increasing in Vietnam.','zh':'越南铁路需求不断增长。'}}
        }, ensure_ascii=False), encoding='utf-8')
        assert build(dest)['route_count']==2
        clean='Bạn có biết rằng vận chuyển đường sắt là phương thức vận chuyển hàng hóa tiết kiệm và an toàn cho doanh nghiệp.'
        joined='Bạn có biết rằngvận chuyển đường sắtlà phương thức vận chuyển hàng hóa tiết kiệm và an toàn cho doanh nghiệp.'
        assert compact_preview_key(clean)==compact_preview_key(joined)
        kept,pruned=dedupe_preview_rows({
            joined:{'en':'Badly joined rail translation.','zh':'错误译文。'},
            clean:{'en':'Rail freight is efficient.','zh':'铁路货运高效。'}
        })
        assert pruned==1 and list(kept)==[clean]
    print('PASS: public previews and equivalent inline-HTML variants deduplicated')

if __name__ == '__main__':
    import sys
    if '--self-test' in sys.argv:
        self_test()
    else:
        value = build()
        tmp = DEST.with_suffix('.tmp')
        tmp.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',
                       encoding='utf-8')
        tmp.replace(DEST)
        print('Public translated article preview index:',value['route_count'],
              'routes, refreshed:',value['refreshed_route_count'],
              'conflicting HTML variants removed:',value['equivalent_duplicates_removed'])
