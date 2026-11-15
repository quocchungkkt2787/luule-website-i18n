#!/usr/bin/env python3
"""Best-effort OCR catalog for public website images. Does not edit pixels."""
import argparse,csv,io,json,re,subprocess,tempfile
from pathlib import Path
import requests
from PIL import Image,ImageOps
from image_i18n import OUT,read,write
DIACRITICS=re.compile('[ăâđêôơưĂÂĐÊÔƠƯàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]',re.I)
MAX_BYTES=9*1024*1024

def ocr(image):
    with tempfile.TemporaryDirectory() as folder:
        f=Path(folder)/'image.png';image.save(f)
        r=subprocess.run(['tesseract',str(f),'stdout','-l','vie+eng','--psm','11','tsv'],
                         capture_output=True,text=True,timeout=40)
        if r.returncode:raise RuntimeError('Tesseract '+r.stderr[:120])
        words=[]
        for row in csv.DictReader(io.StringIO(r.stdout),delimiter='\t'):
            try:
                word=(row.get('text') or '').strip()
                if float(row.get('conf','-1'))>=52 and len(word)>1:words.append(word)
            except (ValueError,TypeError):pass
    text=' '.join(words)
    return {'has_possible_vietnamese_text':bool(DIACRITICS.search(text)),
            'ocr_excerpt':text[:300],'confident_word_count':len(words)}

def check(url,session):
    with session.get(url,timeout=22,stream=True,headers={'Accept':'image/*'}) as response:
        response.raise_for_status()
        content=bytearray()
        for block in response.iter_content(65536):
            content.extend(block)
            if len(content)>MAX_BYTES:raise ValueError('Image exceeds 9MB')
    img=Image.open(io.BytesIO(content))
    if img.format not in ('JPEG','PNG','WEBP','GIF'):return {'status':'unsupported_format'}
    img.seek(0);img=ImageOps.exif_transpose(img)
    if min(img.size)<100 or max(img.size)>12000:return {'status':'unsupported_dimensions'}
    img.thumbnail((3000,3000))
    result=ocr(img.convert('RGB'))
    result['dimensions']=[img.width,img.height]
    result['status']='possibly_contains_vietnamese' if result['has_possible_vietnamese_text'] else 'no_vietnamese_detected'
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=int,default=12);p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    if args.self_test:
        assert DIACRITICS.search('VẬN TẢI') and not DIACRITICS.search('Transport')
        assert ocr(Image.new('RGB',(160,80),'white'))['confident_word_count']==0
        print('PASS: safe local OCR and Vietnamese detection');return
    catalog=read(OUT/'catalog.json',{}).get('images',{})
    prior=read(OUT/'audit.json',{}).get('images',{})
    if not isinstance(catalog,dict) or not catalog:print('No public images discovered yet');return
    if not isinstance(prior,dict):prior={}
    ordered=sorted(catalog,key=lambda url:(0 if catalog[url].get('priority')=='banner_candidate' else 1,url))
    pending=[u for u in ordered if u not in prior]
    session=requests.Session();session.headers['User-Agent']='LuuLePublicImageOcrAudit/1.0'
    for url in pending[:min(30,max(1,args.batch))]:
        try:result=check(url,session)
        except Exception as exc:result={'status':'check_failed','reason':str(exc)[:130]}
        prior[url]=result
        print('Image OCR:',result['status'],url[:96],flush=True)
    reviewed=read(OUT/'manifest.json',{}).get('assets',{})
    data={'version':1,'unique_public_images':len(catalog),
          'images_scanned':sum(u in prior for u in catalog),
          'images_unscanned':sum(u not in prior for u in catalog),
          'possibly_vietnamese':sum(prior.get(u,{}).get('status')=='possibly_contains_vietnamese' for u in catalog),
          'approved_bilingual_images':len(reviewed),
          'ocr_failures':sum(prior.get(u,{}).get('status')=='check_failed' for u in catalog),
          'full_image_translation_verified':False,
          'note':'OCR misses some text. No original images modified; approval of translated variants is required.',
          'images':prior}
    write(OUT/'audit.json',data)
    print('Image OCR:',data['images_scanned'],'/',len(catalog),
          'possible Vietnamese:',data['possibly_vietnamese'],flush=True)
if __name__=='__main__':main()
