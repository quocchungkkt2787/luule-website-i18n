#!/usr/bin/env python3
"""Merge editorially reviewed public-site translations into stable GitHub/Pages packs.

Run AFTER build_translations.py in GitHub Actions and BEFORE git add/commit.
Only handles public display text. No access to customer/quote/tracking data.
When the builder cannot publish a complete homepage, write a clearly marked
partial pack containing ONLY reviewed public strings; never claim full coverage.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public' / 'i18n'
HOME = PUBLIC / 'home.json'
STORE = ROOT / 'translation-cache.json'
REVIEWED = ROOT / 'tools' / 'll-i18n-reviewed-translations.json'

# Whitelist of public rate-checker terms known from the live website UI.
PUBLIC_RATE_KEYS = {
    'TRA CỨU',
    'GIÁ CƯỚC VẬN CHUYỂN',
    'TRA CỨU GIÁ CƯỚC VẬN CHUYỂN',
    'CÔNG CỤ TRỰC TUYẾN',
    'THÔNG TIN HÀNG HÓA',
    'PHƯƠNG THỨC GIAO NHẬN',
    'TUYẾN VẬN CHUYỂN',
    'CƯỚC DỰ KIẾN CỦA BẠN',
    'CƯỚC DỰ KIẾN',
    'TÍNH CƯỚC NGAY',
    'Tính cước ngay',
    'TÍNH NGAY',
    'Tính ngay',
    'TÍNH CƯỚC NHANH',
    'Chọn loại hàng',
    'Chọn loại hàng hóa',
    'Chọn thông tin hàng',
    'Chọn thông tin hàng hóa',
    'Nhập thông tin hàng hóa',
    'Chọn phương thức giao nhận',
    'Chọn hình thức giao nhận',
    'Chọn tuyến vận chuyển',
    'Chọn tuyến đường vận chuyển',
    'Điền thông tin và chọn “Tính cước ngay” để xem chi tiết.',
    'Điền thông tin và chọn "Tính cước ngay" để xem chi tiết.',
    'Điền thông tin và chọn “Tính cước ngay” để xem chi tiết',
    'Phân loại hàng tự động',
    'Tách rõ cước và phụ phí',
    'VAT 8% là mặc định',
    'VAT 8% là mặc định.',
    'Kết quả là cước dự kiến. Vận Tải Lưu Lê sẽ kiểm tra và xác nhận lại mức cước trước khi vận chuyển.',
    'Bước 1',
    'Bước 2',
    'Bước 3',
    'Bước 4',
}


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace atomically so a failed write cannot leave partial JSON.
    fd, temp = tempfile.mkstemp(dir=str(path.parent), prefix='.ll-i18n-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write('\n')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    edits = read(REVIEWED)
    if not isinstance(edits, dict) or len(edits) < 353:
        raise ValueError('Reviewed translations file is missing or incomplete.')
    for source, value in edits.items():
        if not isinstance(source, str) or not source.strip() or not isinstance(value, dict):
            raise ValueError('Invalid translation mapping key or value.')
        if not all(isinstance(value.get(lang), str) and value[lang].strip() for lang in ('en','zh')):
            raise ValueError(f'Empty/invalid translation: {source[:80]}')
    # The builder can hold the homepage when a single public segment is still
    # untranslated (for example after a Haravan UI change). This is not a
    # reason to fail the entire batch and lose every other newly built pack.
    # The minimal fallback contains only human-reviewed public UI phrases and
    # is marked partial, never presented as complete coverage.
    provisional_home = not HOME.is_file()
    if provisional_home:
        pack = {
            'version': 3,
            'route': '/',
            'texts': {},
            'partial': True,
            'coverage_status': 'reviewed-only-fallback',
        }
        print('WARNING: complete home.json unavailable; publishing a clearly '
              'marked reviewed-only partial homepage pack. Other pages may '
              'still be published normally.', flush=True)
    else:
        pack = read(HOME)
    if pack.get('version') != 3 or pack.get('route') != '/' or not isinstance(pack.get('texts'), dict):
        raise ValueError('Unexpected homepage translation pack format; refusing unsafe patch.')
    existing = len(pack['texts'])

    # Store approved translations in the cache so the next Argos build also
    # prefers these over its old or unreliable machine-generated entries.
    cache = read(STORE) if STORE.is_file() else {}
    if not isinstance(cache, dict):
        raise ValueError('translation-cache.json must be a JSON object')
    cache.update(edits)
    atomic_write(STORE, cache)

    # Explicitly include the complete list collected from the browser DOM,
    # even when the crawler did not see it because it was lazy-loaded.
    pack['texts'].update(edits)
    atomic_write(HOME, pack)
    home_added = len(pack['texts']) - existing

    # Where the same public wording appears in other already-published pages,
    # correct it there too; do NOT inject homepage-only copy into other routes.
    patched_files = 0
    corrected_others = 0
    for path in PUBLIC.glob('*.json'):
        if path.name in ('home.json', 'audit.json', 'manifest.json'):
            continue
        other = read(path)
        if not isinstance(other, dict) or other.get('version') != 3 or not isinstance(other.get('texts'), dict):
            continue
        corrections = {key for key in other['texts'] if key in edits}
        # The rate-checker can be rendered as an interactive widget after
        # crawling.  Safely include its known PUBLIC UI copy in that page pack,
        # even if its DOM was not fully rendered during the crawl.
        if other.get('route') == '/pages/tra-cuu-gia-cuoc-van-chuyen':
            corrections.update(key for key in PUBLIC_RATE_KEYS if key in edits)
        if corrections:
            for key in corrections:
                other['texts'][key] = edits[key]
            atomic_write(path, other)
            patched_files += 1
            corrected_others += len(corrections)

    # A fallback pack contains reviewed strings, not complete page coverage.
    # Keep manifest truthfulness: never declare the whole site 100% complete.
    if provisional_home:
        manifest_path = PUBLIC / 'manifest.json'
        manifest = read(manifest_path) if manifest_path.is_file() else {}
        if not isinstance(manifest, dict):
            manifest = {}
        manifest['homepage_pack_reviewed_only'] = True
        manifest['site_coverage_complete'] = False
        manifest['pages_pending'] = max(1, int(manifest.get('pages_pending', 0)))
        manifest['published_pack_files_total'] = sum(
            1 for path in PUBLIC.glob('*.json')
            if path.name not in ('audit.json', 'coverage.json', 'manifest.json'))
        atomic_write(manifest_path, manifest)

    # Public Haravan /search is intentionally excluded from the crawler.
    # Build its safe, stable translation pack from reviewed search UI,
    # public navigation and already-published blog prose. Visitor queries,
    # login forms and personalized results are never collected.
    search_source = PUBLIC / 'pages__customer.json'
    search_source_pack = read(search_source) if search_source.is_file() else {}
    if search_source_pack.get('route') != '/pages/customer':
        raise ValueError('Public site-shell translation pack is unavailable.')
    search_texts = dict(search_source_pack.get('texts') or {})
    article_source = PUBLIC / 'blogs__van-chuyen-bac-nam__van-chuyen-duong-sat-bac-nam.json'
    if article_source.is_file():
        article_pack = read(article_source)
        if article_pack.get('route') == '/blogs/van-chuyen-bac-nam/van-chuyen-duong-sat-bac-nam':
            # Public search currently features this railway article; translated
            # snippets and short fragments are composed by the Haravan template.
            search_texts.update(article_pack.get('texts') or {})
    search_keys = {
        'SEARCH', 'Tìm kiếm', 'TÌM KIẾM', 'Kết quả tìm kiếm',
        'Kết quả tìm kiếm cho',
        'Kết quả tìm kiếm cho "vận tải đường sắt"',
        'Dịch vụ vận chuyển đường sắt Bắc Nam giá rẻ, an toàn',
        '11 Tháng 6 2024', '0Bình luận', '0 Bình luận',
        'Xem tiếp →', 'Xem tiếp', 'Bạn có biết rằng',
        'Chính vì lẽ đó, Công ty Lưu Lê đã triển khai và cung cấp',
        'là một trong những hình thức vận chuyển hiệu quả và tiết kiệm nhất hiện nay? So với các hình thức vận chuyển khác,',
        'Với nhiều năm kinh nghiệm trong lĩnh vực vận tải, Vận Tải Lưu Lê đã trở thành địa chỉ tin cậy của nhiều khách hàng. Chúng tôi tự hào mang đến dịch vụ',
    }
    for key in search_keys:
        if key in edits:
            search_texts[key] = edits[key]
    search_path = PUBLIC / 'search.json'
    previous_search = read(search_path) if search_path.is_file() else {}
    if previous_search and previous_search.get('route') != '/search':
        raise ValueError('Unexpected preexisting search.json route.')
    # Existing reviewed keys take priority and survive rebuilds.
    search_texts.update({key: edits[key] for key in search_texts if key in edits})
    if not all(isinstance(row, dict) and all(isinstance(row.get(code), str)
            and row[code].strip() for code in ('en', 'zh'))
            for row in search_texts.values()):
        raise ValueError('Search pack includes invalid translations.')
    atomic_write(search_path, {
        'version': 3, 'route': '/search', 'complete': False,
        'scope': 'public-search-UI-and-public-article-results-only',
        'note': 'Public site labels and article snippets; visitor search terms are not stored.',
        'texts': search_texts,
    })
    print(f'Public search translation pack: {len(search_texts)} keys', flush=True)

    # Preserve original pages_seen/pages_published/unique_public_texts:
    # those describe what the crawler saw, not what this review added.
    print(f'REVIEWED PATCH OK: {len(edits)} reviewed strings; '
          f'home pack now {len(pack["texts"])} keys (+{home_added}); '
          f'corrected {corrected_others} keys in {patched_files} other published packs; '
          f'homepage status: {"PARTIAL (reviewed only)" if provisional_home else "existing pack"}.')


if __name__ == '__main__':
    main()
