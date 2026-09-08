<img src="Project%20Booking%20-%20CODE/static/images/logo.svg" alt="Office Booking" width="280">

**Hệ thống đặt phòng họp nội bộ** — Flask · SQLite · Jinja2 · Bootstrap 5

### 🔗 [Xem website tại nguyen-thanh-phong.vercel.app](https://nguyen-thanh-phong.vercel.app)

Đăng nhập thử — nhân viên: `an.nv` / `123456` · quản trị viên: vào `/admin` với mật khẩu `admin123`

> ⚠️ Đây là bản demo học tập nên mật khẩu để mặc định cho dễ dùng thử. Bản chạy trên Vercel lưu
> cơ sở dữ liệu tạm, nên dữ liệu bạn thêm vào sẽ quay về trạng thái mẫu sau một thời gian không
> ai truy cập.

---

## Giới thiệu

Office Booking là website nội bộ giúp nhân viên công ty tìm phòng họp trống và đặt lịch họp
chỉ trong vài bước.

Ở nhiều văn phòng, phòng họp được đặt bằng cách hô nhau, nhắn nhóm chat hoặc ghi vào một file
Excel dùng chung. Cách làm này sinh ra bốn vấn đề lặp đi lặp lại, và đây là những gì dự án
giải quyết:

- **Trùng lịch** — hai nhóm cùng tin là mình đã đặt được phòng, tới giờ mới phát hiện
- **Không nhìn được toàn cảnh** — muốn biết phòng nào trống lúc 14h phải hỏi từng người
- **Không truy vết được** — lịch bị đổi hoặc biến mất mà không rõ ai làm, làm lúc nào
- **Phòng đang bảo trì vẫn bị đặt nhầm**

## Tính năng chính

**Dành cho nhân viên**

- Xem lưới lịch tất cả phòng theo ngày, chuyển ngày bằng một cú bấm
- Kiểm tra phòng trống theo khung giờ và số người, có gợi ý phương án thay thế khi hết phòng
- Đặt nhanh phòng trống ở khung giờ gần nhất bằng một nút bấm
- Đặt, sửa và huỷ lịch của chính mình
- Đăng ký tài khoản, xem lịch sử đặt phòng

**Dành cho quản trị viên**

- Quản lý phòng họp: thêm, sửa, xoá, chuyển trạng thái bảo trì
- Quản lý tài khoản nhân viên và đặt lại mật khẩu
- Huỷ được mọi lịch, xem nhật ký toàn bộ thao tác trên hệ thống

**Điểm đáng chú ý**

- Chống trùng lịch bằng phép giao khoảng thời gian, xử lý ngay trong câu truy vấn
- Huỷ mềm — giữ lịch sử để truy vết, đồng thời trả lại khung giờ cho người khác đặt
- Lưới lịch vẽ bằng CSS thuần, không dùng thư viện lịch nào
- Mật khẩu băm bằng `werkzeug.security`, mọi thao tác ghi đều có kiểm tra CSRF
- Trang giới thiệu có nhúng bản đồ Google Maps

## Công nghệ

| Thành phần | Lựa chọn |
|---|---|
| Ngôn ngữ | Python 3 |
| Web framework | Flask 3 |
| Cơ sở dữ liệu | SQLite |
| Giao diện | Jinja2 + Bootstrap 5 |
| JavaScript | JS thuần, không framework |
| Triển khai | Vercel |

Thư viện ngoài duy nhất là Flask. Không có bước biên dịch, không cần Node.js.

## Cấu trúc repo

```
Project Booking - CODE/           Mã nguồn
├── app.py                        Định tuyến web + API JSON
├── services.py                   Nghiệp vụ
├── database.py                   Schema SQLite, nạp dữ liệu gốc
├── api/index.py                  Điểm vào WSGI cho Vercel
├── data/                         Dữ liệu gốc (chỉ đọc)
├── templates/  static/           Giao diện
├── README.md                     Hướng dẫn cài đặt chi tiết
├── PRD.md                        Yêu cầu sản phẩm
└── DESIGN.md                     Thiết kế kỹ thuật

BaoCao_DoAn_Office_Booking.docx   Báo cáo đồ án
```

## Chạy ở máy

```bash
cd "Project Booking - CODE"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Mở trình duyệt tại http://localhost:5000 (đổi cổng bằng biến môi trường `PORT`).

Lần chạy đầu, ứng dụng tự tạo `office_booking.db` và nạp dữ liệu mẫu từ `data/*.json`.
Muốn nạp lại dữ liệu gốc: xoá file `.db` rồi chạy lại.

## Tài liệu

| File | Nội dung |
|---|---|
| [Hướng dẫn chi tiết](Project%20Booking%20-%20CODE/README.md) | Cài đặt, cấu hình, tra cứu đầy đủ từng tính năng |
| [PRD.md](Project%20Booking%20-%20CODE/PRD.md) | *Product Requirements Document* — sản phẩm **làm gì** và **vì sao** |
| [DESIGN.md](Project%20Booking%20-%20CODE/DESIGN.md) | Thiết kế kỹ thuật — hệ thống được xây **như thế nào** |
| [Báo cáo đồ án](BaoCao_DoAn_Office_Booking.docx) | Báo cáo đầy đủ kèm ảnh chụp màn hình |
