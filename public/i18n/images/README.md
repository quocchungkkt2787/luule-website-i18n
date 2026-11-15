# Luu Le public image translations (VI/EN/ZH)

The normal text builder translates HTML text and image alt attributes. It cannot
change lettering permanently burned into JPG/PNG/WebP files. This feature
provides a safe, free two-language image-asset pipeline.

1. `tools/build_translations.py` also discovers image URLs from public pages
   and updates `images/catalog.json`. It does not access Customer accounts.
2. `tools/image_i18n_audit.py` performs limited **offline** OCR with Tesseract
   (`vie+eng`). OCR is only a candidate detector; it cannot guarantee that
   every word printed on every picture was found or read accurately.
3. To localize one image, edit the ORIGINAL file (not a screenshot). Keep its
   canvas size, photographic subjects, composition, and official visual logo.
   Translate Vietnamese lettering to reviewed English and Chinese, including
   marketing copy, company name and slogan outside the official logo.
   Keep phone number 0909 81 6625 and URLs unchanged. Both new raster assets
   must be reviewed for legibility and proportions before publication.
4. Store both validated files in `public/i18n/images/assets/`, then
   add their **relative filenames** to `approved.json` as:
   ```json
   {
     "https://cdn.hstatic.net/your/original-banner.jpg": {
       "en": "original-banner-en.webp",
       "zh": "original-banner-zh.webp"
     }
   }
   ```
   `tools/image_i18n.py` validates that BOTH files exist and the original
   is inventoried, then publishes only safe references in `manifest.json`.
5. The opt-in, client-side `switcher.js` reads this manifest from the same
   Cloudflare Pages origin as the translation JSON. It switches <img>,
   <picture> and supported CSS background images when the customer selects
   EN or ZH. Vietnamese always restores the original. It never changes the
   layout, customer data, URLs, original media files or external widgets.

**Current status**: Image inventory/inspection and the translation switch
are implemented. No localized raster is published until original image bytes
and the matching EN/ZH variants have been created and reviewed. Do not
describe an empty manifest as 100% image translation.

For existing Haravan LL Language V3.8.6, install the one-time V3.8.7
loader; all subsequent reviewed image mappings update on the static host.
