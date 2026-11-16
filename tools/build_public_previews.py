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

def build(directory=PUBLIC):
    # Keep published routes between batches when a page cannot be crawled.
    previous = read(directory / 'previews.json', {})
    routes = dict(previous.get('routes') or {}) if isinstance(previous, dict) else {}
    count = 0
    for path in directory.glob('blogs__*.json'):
        pack = read(path, {})
        route = pack.get('route')
        if not isinstance(route, str) or not ARTICLE.fullmatch(route):
            continue
        entries = pack.get('texts') or {}
        sources = pack.get('preview_sources') or []
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
    return {'version':3, 'route':'*previews', 'routes':routes,
            'route_count':len(routes), 'refreshed_route_count':count,
            'note':'Only PUBLIC first paragraphs/SEO descriptions, not search input or customer data.'}

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
    print('PASS: public route-keyed preview index and private exclusion')

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
              'routes, refreshed:',value['refreshed_route_count'])
