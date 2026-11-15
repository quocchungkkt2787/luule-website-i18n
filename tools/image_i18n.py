#!/usr/bin/env python3
"""Discover images on PUBLIC Luu Le pages and expose ONLY reviewed translations."""
import argparse, hashlib, json, re
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'public'/'i18n'/'images'
SITE='https://vantailuule.vn'
ALLOWED={'vantailuule.vn','www.vantailuule.vn','cdn.hstatic.net','theme.hstatic.net','file.hstatic.net','product.hstatic.net','media.hstatic.net'}
EXT=re.compile(r'\.(?:png|jpe?g|webp|gif|avif|svg)$',re.I)
CSS=re.compile(r'url\(\s*["\']?([^"\')]+)',re.I)
HINT=re.compile(r'banner|hero|slide|gia-cuoc|bang-gia|poster|infographic|quy-trinh|gioi-thieu|pricing|price',re.I)
ATTRS=('src','data-src','data-original','data-lazy','data-lazy-src','data-bg','data-background','poster')

def canonical(src):
    if not isinstance(src,str) or not src.strip() or src.lstrip().startswith(('data:','blob:','javascript:','#')):return None
    u=urlsplit(urljoin(SITE+'/',src.strip()))
    if u.scheme not in ('http','https') or u.hostname not in ALLOWED or not EXT.search(u.path):return None
    return urlunsplit((u.scheme,u.netloc.lower(),u.path,'',''))

def extract(html,route):
    if not route.startswith('/') or route.startswith(('/account','/api','/admin','/cart','/checkout','/pages/customer','/pages/ll-customer')):return {}
    soup=BeautifulSoup(html,'html.parser')
    if not soup.body:return {}
    found={}
    def add(src,el,kind):
        key=canonical(src)
        if key:
            row=found.setdefault(key,{'alt':set(),'routes':set(),'kinds':set()})
            if el.get('alt'):row['alt'].add(' '.join(el['alt'].split())[:160])
            row['routes'].add(route);row['kinds'].add(kind)
    for el in soup.body.select('img,source,video,[style],[data-bg],[data-background]'):
        if el.find_parent(attrs={'data-ll-private':True}) or el.find_parent(attrs={'data-ll-no-translate':True}):continue
        for attr in ATTRS:
            if el.get(attr):add(el[attr],el,el.name or 'background')
        for attr in ('srcset','data-srcset','data-lazy-srcset'):
            for part in el.get(attr,'').split(','):
                if part.strip():add(part.split()[0],el,el.name or 'source')
        if el.get('style'):
            for value in CSS.findall(el['style']):add(value,el,'background')
    return found

def read(path,default):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default

def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    temp.replace(path)

def capture(all_images,new):
    for url,item in new.items():
        row=all_images.setdefault(url,{'id':hashlib.sha256(url.encode()).hexdigest()[:16], 'alt':[],'routes':[],'kinds':[]})
        for field,max_items in (('alt',3),('routes',8),('kinds',5)):
            row[field]=sorted(set(row[field])|set(item[field]))[:max_items]
        row['priority']='banner_candidate' if HINT.search(url+' '+ ' '.join(row['alt'])) else 'general'

def publish(all_images):
    approved=read(OUT/'approved.json',{})
    if not isinstance(approved,dict):raise ValueError('approved.json must be a dictionary')
    assets={}
    for orig,entry in approved.items():
        if canonical(orig)!=orig or orig not in all_images or not isinstance(entry,dict):continue
        pair={};okay=True
        for lang in ('en','zh'):
            rel=entry.get(lang)
            if not isinstance(rel,str) or not re.fullmatch(r'[a-zA-Z0-9_.\-/]+\.(?:png|jpe?g|webp|avif)',rel,re.I):
                okay=False;break
            path=(OUT/'assets'/rel).resolve()
            if not path.is_relative_to((OUT/'assets').resolve()) or not path.is_file():
                okay=False;break
            pair[lang]='images/assets/'+rel
        if okay:assets[orig]=pair
    write(OUT/'manifest.json',{'version':1,'assets':assets,'approved_pair_count':len(assets),
        'unapproved_public_images':max(0,len(all_images)-len(assets)),
        'note':'Only manually reviewed EN/ZH image pairs with real files are used. No fake translation from alt text.'})
    return assets

def save(all_images):
    write(OUT/'catalog.json',{'version':1,'images':all_images,'unique_public_images':len(all_images),
        'note':'Public image inventory, not OCR. Original logos and photos remain unchanged until a reviewed image variant exists.'})
    return publish(all_images)

def test():
    html="""<html><body><img src='https://cdn.hstatic.net/a/banner.png?v=2' alt='Bảng giá'>
    <picture><source srcset='/images/a.jpg 1x, /images/a2.jpg 2x'></picture>
    <div style="background-image:url(https://theme.hstatic.net/a/hero.webp)"></div>
    <img src='https://evil.example/secret.png'></body></html>"""
    data=extract(html,'/')
    assert len(data)==4,data
    assert canonical('https://cdn.hstatic.net/a/banner.png?v=2') in data
    assert not extract(html,'/pages/customer')
    assert canonical('https://evil.example/a.jpg') is None
    print('PASS: public image discoverer and URL safety')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');args=p.parse_args()
    if args.self_test:test()
    else:
        d=read(OUT/'catalog.json',{});imgs=d.get('images',{})
        print('Approved image pairs:',len(publish(imgs)),'out of',len(imgs))
