"""Self-contained Chromium regression tests. No request to vantailuule.vn."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

js=Path(__file__).resolve().parents[1].joinpath('ll-language-switcher.js').read_text(encoding='utf-8')
source=['Trang chủ','Dịch vụ vận chuyển hàng hóa','Nhập mã vận đơn','Tư vấn và báo giá','Thời gian vận chuyển']
en=['Home','Freight transportation services','Enter the tracking number','Consultation and quotation','Transit time']
zh=['首页','货物运输服务','输入运单号','咨询与报价','运输时间']
pack={'version':3,'route':'blank','texts':{k:{'en':e,'zh':z} for k,e,z in zip(source,en,zh)}}
html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"></head>
<body><div id="wrapper"><header><nav>Trang chủ</nav></header>
<main><h1>Dịch vụ vận chuyển hàng hóa</h1><input placeholder="Nhập mã vận đơn"><p>Tư vấn và báo giá</p></main></div></body></html>'''

def new_page(browser, data):
    p=browser.new_page()
    p.route('https://trans.pages.dev/i18n/blank.json',lambda route:route.fulfill(
        status=200 if data is not None else 404,
        body=json.dumps(data) if data is not None else 'Not found',
        content_type='application/json',headers={'access-control-allow-origin':'*'}))
    p.set_content(html)
    p.evaluate("window.LL_I18N_BASE='https://trans.pages.dev'")
    p.add_script_tag(content=js)
    return p

with sync_playwright() as p:
    opts={'headless':True,'args':['--no-sandbox']}
    if Path('/usr/bin/chromium').exists(): opts['executable_path']='/usr/bin/chromium'
    b=p.chromium.launch(**opts)
    q=b.new_page();q.set_content(html);q.add_script_tag(content=js)
    assert q.locator('#ll-language-v3').count()==0
    assert q.locator('h1').inner_text()==source[1]
    q.close()
    print('PASS 1: no repo configuration => website remains untouched')
    q=new_page(b,pack)
    errors=[];q.on('pageerror',lambda e:errors.append(str(e)))
    q.locator('#ll-language-v3 select').select_option('en')
    q.wait_for_function("document.querySelector('h1').textContent==='Freight transportation services'")
    assert q.locator('nav').inner_text()=='Home'
    assert q.locator('input').get_attribute('placeholder')=='Enter the tracking number'
    assert q.locator('#ll-i18n-overlay').count()==0
    q.wait_for_timeout(800)
    assert q.locator('h1').inner_text()=='Freight transportation services'
    print('PASS 2: full English translation, no overlay or translation loop')
    q.evaluate("document.querySelector('main').appendChild(Object.assign(document.createElement('p'), {textContent:'Thời gian vận chuyển'}))")
    q.wait_for_function("document.querySelector('main p:last-child').textContent==='Transit time'")
    assert q.locator('h1').inner_text()=='Freight transportation services'
    print('PASS 3: new dynamic segment with a translation is translated')
    q.locator('#ll-language-v3 select').select_option('zh')
    q.wait_for_function("document.querySelector('h1').textContent==='货物运输服务'")
    assert q.locator('nav').inner_text()=='首页'
    print('PASS 4: full Simplified Chinese translation')
    q.locator('#ll-language-v3 select').select_option('vi')
    q.wait_for_function("document.querySelector('h1').textContent==='Dịch vụ vận chuyển hàng hóa'")
    print('PASS 5: originals restored')
    q.locator('#ll-language-v3 select').select_option('en')
    q.wait_for_function("document.querySelector('h1').textContent==='Freight transportation services'")
    q.evaluate("document.querySelector('main').appendChild(Object.assign(document.createElement('p'), {textContent:'Nội dung mới chưa dịch'}))")
    q.wait_for_function("document.querySelector('h1').textContent==='Dịch vụ vận chuyển hàng hóa'")
    assert q.locator('#ll-language-v3 select').input_value()=='vi'
    print('PASS 6: missing dynamic text rolls whole site back to Vietnamese')
    assert not errors, errors
    q.close()
    q=new_page(b,None)
    q.locator('#ll-language-v3 select').select_option('en')
    q.wait_for_function("document.querySelector('#ll-language-v3-notice').hidden===false")
    assert q.locator('h1').inner_text()==source[1]
    assert q.locator('#ll-i18n-overlay').count()==0
    print('PASS 7: 404 translation pack does not blur/block the page')
    q.close();b.close()
print('ALL 7 BROWSER TESTS PASSED')
