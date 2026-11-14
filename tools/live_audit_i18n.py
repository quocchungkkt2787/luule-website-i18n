#!/usr/bin/env python3
"""Rolling EN/ZH browser QA of anonymous public Haravan routes, never user data."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public' / 'i18n'
AUDIT = PUBLIC / 'live-qa.json'
SITE = 'https://vantailuule.vn'
BATCH = max(1, min(15, int(os.getenv('LL_QA_BATCH_SIZE', '8'))))
PRIORITY = ('/', '/search', '/pages/customer')
IGNORED = {'shared.json', 'manifest.json', 'audit.json', 'coverage.json', 'live-qa.json'}
VI = re.compile('[ăâđêôơưĂÂĐÊÔƠƯàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]', re.I)

def read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)

def packs():
    found = {}
    for path in sorted(PUBLIC.glob('*.json')):
        if path.name in IGNORED:
            continue
        data = read(path, {})
        route = data.get('route')
        if (not isinstance(route, str) or not route.startswith('/') or
            route == '*' or route.startswith(('/account', '/admin', '/api', '/checkout')) or
            not isinstance(data.get('texts'), dict)):
            continue
        found[route] = (hashlib.sha256(path.read_bytes()).hexdigest()[:16], data['texts'])
    return found

def inspect(page, route, lang, entries):
    path = ('/search?type=article&q=' + quote('vận tải đường sắt')
            if route == '/search' else route)
    response = page.goto(SITE + path, wait_until='domcontentloaded', timeout=40000)
    if response is None or response.status >= 400:
        return {'ok': False, 'reason': 'HTTP '+str(response.status if response else 'none')}
    try:
        page.wait_for_function(
            "lang => document.documentElement.getAttribute('data-ll-i18n-active') === lang",
            arg=lang, timeout=30000)
    except Exception:
        return {'ok': False, 'reason': 'Language not activated',
                'active': page.evaluate("document.documentElement.getAttribute('data-ll-i18n-active')")}
    page.wait_for_timeout(850)
    text = re.sub(r'\s+', ' ', page.locator('body').inner_text(timeout=15000))
    title = page.title()
    remaining = []
    for key, row in entries.items():
        if (isinstance(key, str) and len(key) >= 40 and VI.search(key)
            and isinstance(row, dict) and row.get(lang) and key in text):
            remaining.append(key[:110])
            if len(remaining) >= 5:
                break
    if route == '/search':
        for known in ('Kết quả tìm kiếm cho', 'Bạn đang muốn tìm hiểu về Tổng công ty'):
            if known in text and known not in remaining:
                remaining.append(known)
    if route == '/' and lang == 'en' and 'Vận Tải Lưu Lê - Đơn vị vận chuyển hàng hóa Bắc Nam' in title:
        remaining.append('Homepage browser title not translated')
    return {'ok': not remaining,
            'reason': 'Visible Vietnamese public text' if remaining else 'pass',
            'examples': remaining, 'title': title[:140]}

def main():
    catalog = packs()
    old = read(AUDIT, {}).get('routes', {})
    if not isinstance(old, dict):
        old = {}
    records = {r: old.get(r, {}) for r in catalog}
    untested = [r for r in sorted(catalog) if r not in PRIORITY and
                (records[r].get('fingerprint') != catalog[r][0] or
                 records[r].get('status') not in ('pass', 'fail'))]
    failures = [r for r in sorted(catalog) if r not in PRIORITY and
                records[r].get('fingerprint') == catalog[r][0] and
                records[r].get('status') == 'fail']
    selected = list(dict.fromkeys([r for r in PRIORITY if r in catalog] +
                                  (untested + failures)[:BATCH]))
    print(f'Public live QA: {len(catalog)} routes, {len(untested)} untested, '
          f'{len(failures)} failures, checking {len(selected)}', flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            for route in selected:
                fingerprint, entries = catalog[route]
                checks = {}
                for lang in ('en', 'zh'):
                    context = browser.new_context(viewport={'width':1280,'height':800})
                    context.add_init_script("try { localStorage.setItem('ll_website_lang_v3'," +
                                            json.dumps(lang) + "); } catch(e) {}")
                    page = context.new_page()
                    try:
                        checks[lang] = inspect(page, route, lang, entries)
                    except Exception as exc:
                        checks[lang] = {'ok': False, 'reason': str(exc)[:220]}
                    finally:
                        context.close()
                passed = all(row.get('ok') for row in checks.values())
                records[route] = {'fingerprint': fingerprint,
                                  'status': 'pass' if passed else 'fail',
                                  'checked_at': datetime.now(timezone.utc).isoformat(),
                                  'languages': checks}
                print(('PASS ' if passed else 'FAIL ') + route, flush=True)
        finally:
            browser.close()
    passed = sum(row.get('status') == 'pass' and
                 row.get('fingerprint') == catalog[route][0]
                 for route, row in records.items())
    failures = [route for route, row in records.items()
                if row.get('status') == 'fail' and row.get('fingerprint') == catalog[route][0]]
    write(AUDIT, {'version': 1, 'type': 'anonymous-live-translation-check',
                  'tested_at': datetime.now(timezone.utc).isoformat(),
                  'public_routes_total': len(catalog),
                  'public_routes_verified': passed,
                  'public_routes_pending': len(catalog) - passed,
                  'public_routes_failed': len(failures),
                  'failed_examples': failures[:20],
                  'full_live_coverage_verified': bool(catalog) and passed == len(catalog),
                  'note': 'Anonymous public pages only; excludes private data, image lettering and external apps.',
                  'routes': records})
    print(f'Live QA verified {passed}/{len(catalog)}, failures {len(failures)}', flush=True)

if __name__ == '__main__':
    main()
