VẬN TẢI LƯU LÊ – ĐA NGÔN NGỮ TOÀN WEBSITE – V3.0 AN TOÀN
Ngày: 08/11/2026

MỤC TIÊU
- Một bộ code chung trong Haravan cho Việt – Anh – Trung giản thể.
- Kho dịch công khai tạo theo lịch từ các bài viết/trang công khai, không phải sửa JS cho từng bài.
- Dịch đủ chữ trên trang mới mới thay đổi; nếu thiếu, trở lại toàn bộ tiếng Việt.
- KHÔNG lớp phủ, làm mờ, khóa giao diện, API trả phí hay dịch từng từ như V1–V2.
- GIỮ NGUYÊN hệ thống tính cước, LL-TRACKING, LL-CUSTOMER, AI Chat.

CẦN HIỂU RÕ
- V3 là HỆ THỐNG MÃ NGUỒN + CÔNG CỤ TẠO DỮ LIỆU, CHƯA CÓ BẢN DỊCH THẬT.
- Không thể tự hoạt động đầy đủ chỉ bằng cách dán file JavaScript vào Assets.
- Phải đưa kho dịch lên GitHub + Cloudflare Pages (có gói miễn phí) TRƯỚC khi kích hoạt.
- Chưa được triển khai lên Haravan của bạn. Chưa chạy dịch hàng loạt hay kiểm thử trực tiếp website thật.
- Không bắt buộc dùng dịch vụ có phí; cần thao tác trên tài khoản do chủ website sở hữu.
- Chất lượng dịch máy phải biên tập ở bài quan trọng, báo giá, chính sách, thuật ngữ.
- Chữ trong ẢNH/BANNER, VIDEO không được dịch; cần tự làm ảnh tương ứng.
- Các ứng dụng KHÔNG chạy trong trang Haravan như LL-CUSTOMER/ADMIN cần hỗ trợ ngôn ngữ từ chính ứng dụng đó.
- Chuyển chữ bằng JavaScript KHÔNG TẠO SEO 3 ngôn ngữ trên Google; muốn SEO phải làm URL riêng, hreflang và canonical phù hợp.

1) TẠO KHO DỊCH MIỄN PHÍ (MỚI)
A. Tạo một repository GitHub PUBLIC, ví dụ: luule-website-i18n.
B. Giải nén file ZIP và đưa toàn bộ cấu trúc vào gốc repo; cần có .github/workflows/build-i18n.yml, tools/build_translations.py, public/.
   KHÔNG đưa dữ liệu tài khoản, báo giá khách, mật khẩu, API key hoặc dữ liệu Google Sheets lên repo công khai.
C. GitHub > Repository > Settings > Actions > General: bật Actions; cho phép Read and write permissions (cần để ghi file dịch trở lại repo).
D. Mở Actions > Build Luu Le public translations (VI EN ZH) > Run workflow.
E. Khi Workflow hoàn thành, xem public/i18n/manifest.json.
   pages_seen: số trang đọc được; pages_published: số trang có bộ dịch đầy đủ; pages_pending: số trang đang thiếu dịch.
   Nếu job báo lỗi, KHÔNG KÍCH HOẠT TRÊN WEBSITE thật. Sửa lỗi và chạy lại.
   Nếu pages_published=0, nghĩa là CHƯA CÓ dữ liệu để đổi ngôn ngữ.
F. Công cụ chỉ đọc nội dung công khai qua sitemap + link nội bộ; chạy lịch hàng ngày.
   Bài mới chỉ có bản dịch SAU khi workflow chạy xong, không phải ngay lúc đăng bài.

2) ĐƯA KHO DỊCH LÊN CLOUDFLARE PAGES (GÓI FREE)
A. Vào Cloudflare > Workers & Pages > Create application > Pages > Connect to Git.
B. Chọn repo mới ở bước 1.
C. Framework preset: None; Build command: bỏ trống; Build output directory: public.
D. Deploy. Bạn có URL dạng https://ten-du-an.pages.dev.
E. Truy cập https://ten-du-an.pages.dev/i18n/manifest.json.
   Chỉ đi tiếp khi hiển thị đúng JSON v3 và pages_published > 0.
F. Vào một route, ví dụ https://ten-du-an.pages.dev/i18n/home.json, xác nhận có version: 3 và texts chứa cả en, zh.

3) CÀI HARAVAN – CHỈ TRÊN BẢN SAO GIAO DIỆN
A. Vào Website > Giao diện > SAO CHÉP GIAO DIỆN.
B. Chỉnh sửa code bản sao > Assets > ll-language-switcher.js.
   Dán TOÀN BỘ mã từ file LL-JavaScript-3-ngon-ngu-V3-AN-TOAN-COPY.txt rồi LƯU.
   Đây là phiên bản thay thế V1.3/V2 cũ; chỉ để một file cùng tên.
C. Trong theme.liquid của bản sao, ngay sau {% include 'll-ai-chat' %} và trước </body>, chèn:

<script>window.LL_I18N_BASE='https://TEN-DU-AN.pages.dev';</script>
<script src="{{ 'll-language-switcher.js' | asset_url }}" defer></script>

   THAY https://TEN-DU-AN.pages.dev bằng URL thật ở bước 2. Chỉ chèn MỘT dòng gọi script.
D. LƯU, XEM TRƯỚC, chọn Việt/Anh/Trung. Nếu pack không đầy đủ, trang giữ tiếng Việt + cảnh báo nhỏ.
E. Kiểm tra tối thiểu: trang chủ, các blog, menu, tra cứu, biểu mẫu, mobile, chuyển trang, quay lại vi, tốc độ.
F. KHÔNG CHUYỂN THÀNH THEME CHÍNH khi chưa kiểm tra đầy đủ.

4) KHI CÓ LỖI / MUỐN TẮT NGAY
Chỉ bỏ dòng:
<script src="{{ 'll-language-switcher.js' | asset_url }}" defer></script>
Trong theme.liquid của giao diện tương ứng. Không xóa nội dung Assets và không sửa các đoạn code khác.

5) KIỂM TRA CƠ BẢN
F12 > Console (ở trang đã tích hợp):
  window.LLGlobalI18N.state()
Kết quả mẫu: {version:'3.0',lang:'vi',route:'/',base:'https://...',packLoaded:true}

6) GIỚI HẠN HIỆN TẠI
- Cơ chế chuyển đồng loạt theo text node, dựa trên nội dung trang đã được quét và dịch trước.
- Những script nhúng động hoặc dữ liệu thời gian thực có thể khác thời điểm quét; V3 sẽ quay lại tiếng Việt nếu thiếu pack.
- Nếu trang có nhiều nội dung thay đổi liên tục, nên làm i18n trực tiếp trong module đó thay vì dịch DOM.
- Tự động quét nhiều trang có thể tốn tài nguyên trong giới hạn miễn phí; theo dõi Usage của GitHub Actions/Cloudflare.
- Website hiện tại KHÔNG CÓ nguồn dịch triển khai, vì vậy V3 CHƯA làm xong việc chuyển ba ngôn ngữ khi chưa kết nối và xuất bản kho dịch.

Thông số:
  Mã frontend: ll-language-switcher.js
  Mã xây kho dịch: tools/build_translations.py
  Lịch: .github/workflows/build-i18n.yml
  Gói mỗi trang: public/i18n/<route-id>.json
  Hệ dịch: Argos Translate (vi->en, en->zh), chạy trong GitHub Actions.

THAM KHẢO
Haravan sửa Assets: https://help.haravan.com/docs/website/themes/huong-dan-chinh-sua-code-giao-dien/
Argos Translate: https://argos-translate.readthedocs.io/
Cloudflare Pages: https://developers.cloudflare.com/pages/
GitHub Actions: https://docs.github.com/en/actions/
