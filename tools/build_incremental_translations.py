#!/usr/bin/env python3
"""Incremental EN/ZH updates for PUBLIC Haravan pages. No private APIs or theme edits.

Read public sitemap metadata, fetch newly published/modified URLs, and rotate
a small safety audit for websites whose sitemap does not update <lastmod>.
Unchanged page translations remain cached. A separate explicit full crawler
exists for recovery, but is not used by the scheduled workflow.
"""
import argparse
import hashlib
import json
import os
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import requests
import build_translations as base

INDEX = base.ROOT / '.ll-i18n-public-change-index.json'
MAX_PAGES = max(1, min(1200, int(os.getenv('LL_DELTA_MAX_PAGES', '150'))))
SAMPLE = max(0, min(100, int(os.getenv('LL_DELTA_SAMPLE', '30'))))
MAX_NEW = max(1, int(os.getenv('LL_MAX_NEW', '12000')))


def tag(node):
    return node.tag.rsplit('}', 1)[-1].lower()


def child_text(node, name):
    for item in node:
        if tag(item) == name and item.text:
            return item.text.strip()
    return ''


def sitemap_snapshot(session):
    """Obtain URL + lastmod hints by fetching only public sitemap XML."""
    queue = deque([(base.BASE + '/sitemap.xml', 0)])
    seen = set()
    routes = {}
    while queue:
        url, depth = queue.popleft()
        if url in seen or depth > 3:
            continue
        seen.add(url)
        xml, final = base.fetch(session, url)
        root = ET.fromstring(xml)
        if tag(root) == 'sitemapindex':
            for entry in root:
                loc = child_text(entry, 'loc')
                if loc.startswith(base.BASE) and 'sitemap' in loc:
                    queue.append((loc, depth + 1))
        elif tag(root) == 'urlset':
            for entry in root:
                loc = child_text(entry, 'loc')
                if base.valid_url(loc):
                    routes[base.page_key(base.canonical(loc))] = child_text(entry, 'lastmod')
    if not routes:
        raise RuntimeError('No public sitemap routes; preserve previous translations and retry later')
    return routes


def pack_path(route):
    return base.PUBLIC / (base.route_id(route) + '.json')


def pack_info(route):
    path = pack_path(route)
    if not path.is_file():
        return None
    data = base.cached_json(path, {})
    if data.get('route') != route or not isinstance(data.get('texts'), dict):
        return None
    return data


def source_fingerprint(segments):
    return hashlib.sha256('\n'.join(sorted(segments)).encode('utf-8')).hexdigest()[:20]


def select_routes(snapshot, state, sample=SAMPLE, cap=MAX_PAGES):
    """Select all new/changed routes before a bounded round-robin safety audit."""
    previous = dict(state.get('lastmods') or {})
    pending = set(state.get('pending') or [])
    old_audit = base.cached_json(base.PUBLIC / 'audit.json', {})
    pending.update(row.get('route') for row in old_audit.get('pending_pages', [])
                   if isinstance(row, dict) and row.get('route'))
    # One-time migration baseline: full packs already exist from the earlier
    # crawler. Do NOT fetch every old page merely because this index is new.
    if not state.get('initialized'):
        previous.update({r: m for r, m in snapshot.items() if pack_path(r).is_file()})
    important = []
    for route, modified in snapshot.items():
        pack = pack_info(route)
        new_or_incomplete = pack is None or not pack.get('complete', True)
        changed_hint = (bool(modified) and route in previous and
                        modified != previous.get(route))
        unknown_route = route not in previous
        if new_or_incomplete or changed_hint or unknown_route or route in pending:
            important.append(route)
    important = sorted(set(important), key=lambda x: (pack_path(x).is_file(), x))
    remaining = [r for r in sorted(snapshot) if r not in important and
                 pack_path(r).is_file()]
    cursor = int(state.get('cursor') or 0)
    candidates = ([remaining[(cursor + i) % len(remaining)]
                   for i in range(min(sample, len(remaining)))] if remaining else [])
    chosen = list(dict.fromkeys(important + candidates))[:cap]
    advance = min(sample, len(remaining))
    next_cursor = (cursor + advance) % len(remaining) if remaining else 0
    return chosen, next_cursor, previous, important


def update_report(snapshot, state, checked, rebuilt, failed):
    """Restore global counts: base.build() processes only a DELTA of all pages."""
    manifest_path = base.PUBLIC / 'manifest.json'
    audit_path = base.PUBLIC / 'audit.json'
    coverage_path = base.PUBLIC / 'coverage.json'
    manifest = base.cached_json(manifest_path, {})
    audit = base.cached_json(audit_path, {})
    coverage = base.cached_json(coverage_path, {})
    published = 0
    pending = []
    missing_strings = 0
    for route in snapshot:
        pack = pack_info(route)
        if pack is None:
            pending.append({'route': route, 'missing_count': None})
        else:
            published += 1
            if not pack.get('complete', True):
                count = int(pack.get('missing_count') or 0)
                pending.append({'route': route, 'missing_count': count})
                missing_strings += count
    manifest.update({
        'pages_seen': published,
        'pages_published': published,
        'pages_pending': len(pending),
        'discovered_public_urls': len(snapshot),
        'site_coverage_complete': not pending and not failed,
        'incremental_scan': True,
        'last_incremental_check': datetime.now(timezone.utc).isoformat(),
        'last_incremental_checked_routes': len(checked),
        'last_incremental_rebuilt_routes': len(rebuilt),
    })
    audit.update({'pages_seen': published, 'pages_published': published,
                  'pages_pending': len(pending), 'missing_unique_texts': missing_strings,
                  'pending_pages': pending[:250]})
    coverage.update({'discovered_public_urls': len(snapshot),
                     'unvisited_without_existing_pack': sum(pack_info(r) is None for r in snapshot),
                     'last_delta_failed': failed[:20],
                     'last_delta_checked': len(checked)})
    base.save_json(manifest_path, manifest)
    base.save_json(audit_path, audit)
    base.save_json(coverage_path, coverage)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        test_xml = ET.fromstring('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://vantailuule.vn/blogs/test/new</loc><lastmod>2026-11-21T08:00:00Z</lastmod></url></urlset>')
        assert tag(test_xml) == 'urlset'
        assert child_text(next(iter(test_xml)), 'lastmod') == '2026-11-21T08:00:00Z'
        assert source_fingerprint({'x', 'y'}) == source_fingerprint({'y', 'x'})
        assert 'only_urls' in __import__('inspect').signature(base.crawl_pages).parameters
        print('PASS: incremental sitemap parsing, stable fingerprints, bounded crawl mode')
        return
    session = requests.Session()
    session.headers['User-Agent'] = 'LuuLePublicI18NDelta/1.0'
    snapshot = sitemap_snapshot(session)
    state = base.cached_json(INDEX, {})
    selected, cursor, baseline, important = select_routes(snapshot, state)
    print('Sitemap:', len(snapshot), 'new/updated/incomplete:', len(important),
          'selected this run:', len(selected), 'safety sample:', SAMPLE, flush=True)
    if not selected:
        print('No public content to revisit; existing EN/ZH packs unchanged.')
        return
    # A failed page stays queued next time, never marked up-to-date.
    pages = base.crawl_pages(session, max_pages=len(selected),
                            rate=0.1, use_browser=True,
                            only_urls={base.BASE + r for r in selected})
    pending = set(state.get('pending') or [])
    fingerprints = dict(state.get('fingerprints') or {})
    lastmods = dict(baseline)
    to_build = {}
    for route, segments in pages.items():
        fingerprint = source_fingerprint(segments)
        pack = pack_info(route)
        if fingerprint != fingerprints.get(route) or pack is None or not pack.get('complete', True):
            to_build[route] = segments
        fingerprints[route] = fingerprint
        lastmods[route] = snapshot.get(route, '')
        pending.discard(route)
    failures = sorted(set(selected) - set(pages))
    pending.update(failures)
    if to_build:
        base.build(to_build, max_new=MAX_NEW)
        # Preserve pending items if translation quota was hit or a phrase failed.
        for route in to_build:
            pack = pack_info(route)
            if not pack or not pack.get('complete', True):
                pending.add(route)
    # Retain all outstanding URL changes, including those beyond this run's cap.
    for route in important:
        if route not in pages:
            pending.add(route)
    pending.intersection_update(snapshot)
    state = {
        'version': 1, 'initialized': True, 'lastmods': lastmods,
        'fingerprints': fingerprints, 'pending': sorted(pending),
        'cursor': cursor,
        'last_run': datetime.now(timezone.utc).isoformat(),
    }
    update_report(snapshot, state, pages, to_build, failures)
    base.save_json(INDEX, state)
    print('DELTA DONE:', len(pages), 'fetched,', len(to_build),
          'updated packs,', len(pending), 'retry routes', flush=True)


if __name__ == '__main__':
    main()
