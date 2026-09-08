# DESIGN — Office Booking

> **DESIGN.md** là tài liệu mô tả **hệ thống được xây dựng như thế nào**.
> Nó trả lời: chia thành những lớp nào, dữ liệu tổ chức ra sao, thuật toán chính là gì,
> giao diện dùng màu và font nào. Còn *làm cái gì và vì sao* thì nằm ở [PRD.md](PRD.md).

---

## 1. Công nghệ sử dụng

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Ngôn ngữ | Python 3 | Yêu cầu môn học |
| Web framework | Flask 3 | Nhẹ, đủ dùng, không cần cấu hình phức tạp |
| Cơ sở dữ liệu | SQLite | Nằm gọn trong một file, không cần cài server |
| Template | Jinja2 | Đi kèm Flask |
| CSS | Bootstrap 5 + CSS thuần | Bootstrap lo phần khung, CSS thuần lo phần bản sắc riêng |
| JavaScript | JS thuần | Không dùng framework — dự án nhỏ, tránh phụ thuộc thừa |

**Thư viện ngoài duy nhất là Flask.** Không có bước biên dịch, không cần Node.js.

## 2. Kiến trúc

Chia làm ba lớp, mỗi lớp một file, phụ thuộc đi theo **một chiều**:

```
      Trình duyệt
           │
           ▼
   ┌───────────────┐
   │    app.py     │  Lớp giao tiếp
   │   (821 dòng)  │  Định tuyến, đăng nhập, CSRF, đổ dữ liệu ra template
   └───────┬───────┘
           ▼
   ┌───────────────┐
   │  services.py  │  Lớp nghiệp vụ
   │  (1498 dòng)  │  Kiểm tra dữ liệu, chống trùng lịch, phân quyền, ghi nhật ký
   └───────┬───────┘
           ▼
   ┌───────────────┐
   │  database.py  │  Lớp dữ liệu
   │   (236 dòng)  │  Định nghĩa bảng, mở kết nối, nạp dữ liệu gốc
   └───────┬───────┘
           ▼
    office_booking.db  ←  nạp lần đầu từ  data/*.json
```

**Nguyên tắc:** `services.py` không biết gì về HTTP (không import Flask), `database.py` không chứa logic nghiệp vụ. Nhờ vậy có thể kiểm thử nghiệp vụ mà không cần chạy web server.

### Cấu trúc thư mục
```
app.py                Định tuyến web + API JSON
services.py           Nghiệp vụ
database.py           Schema, kết nối, nạp dữ liệu gốc
api/index.py          Điểm vào WSGI khi chạy trên Vercel
vercel.json           Cấu hình deploy
data/                 Dữ liệu gốc, chỉ đọc (rooms, bookings, users)
templates/            Giao diện — base.html + các trang + _macros.html
templates/admin/      Giao diện khu quản trị
static/css/           style.css
static/js/            main.js, availability.js, booking.js, home-grid.js, admin.js, login.js
static/images/        Logo + ảnh phòng họp
```

## 3. Thiết kế cơ sở dữ liệu

### 3.1 Sơ đồ quan hệ
```
   users                rooms
     │                    │
     │ user_id            │ room_id
     ▼                    ▼
        ┌──────────┐
        │ bookings │
        └────┬─────┘
             │ booking_id
             ▼
       booking_logs
```

### 3.2 Bảng

**`rooms`** — phòng họp
| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | TEXT | Khoá chính, ví dụ `R102` |
| `name`, `floor`, `capacity` | TEXT / INT / INT | |
| `equipment` | TEXT | Danh sách thiết bị, lưu dạng chuỗi JSON |
| `image` | TEXT | Đường dẫn ảnh |
| `status` | TEXT | `active` \| `maintenance` |

**`bookings`** — lịch đặt
| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | TEXT | Khoá chính, dạng `BK001` |
| `room_id` | TEXT | → `rooms.id` |
| `date`, `start_time`, `end_time` | TEXT | `YYYY-MM-DD`, `HH:MM` |
| `booked_by`, `department`, `purpose` | TEXT | |
| `status` | TEXT | `active` \| `cancelled` |
| `cancelled_at` | TEXT | Thời điểm huỷ, `NULL` nếu chưa huỷ |
| `user_id` | TEXT | → `users.id`, dùng để phân quyền |
| `created_at` | TEXT | |

**`users`** — tài khoản nhân viên
| Cột | Ghi chú |
|---|---|
| `id`, `username` (duy nhất), `full_name`, `department` | |
| `password_hash` | **Luôn là băm**, không bao giờ lưu mật khẩu thô |

**`booking_logs`** — nhật ký thay đổi
| Cột | Ghi chú |
|---|---|
| `booking_id` | → `bookings.id` |
| `action` | `create` \| `update` \| `cancel` |
| `actor` | Ai thực hiện |
| `changes` | Danh sách trường đã đổi, dạng JSON |

### 3.3 Chỉ mục
```sql
idx_bookings_room_date  ON bookings (room_id, date)   -- tăng tốc kiểm tra trùng lịch
idx_bookings_date       ON bookings (date)            -- tăng tốc lưới lịch trang chủ
idx_booking_logs_booking ON booking_logs (booking_id, id)
```

### 3.4 Nạp dữ liệu gốc
`init_db()` chạy mỗi lần khởi động và **an toàn khi gọi lại nhiều lần**:
1. Tạo bảng nếu chưa có (`CREATE TABLE IF NOT EXISTS`)
2. Tự bổ sung cột mới cho database tạo từ phiên bản cũ
3. Nạp dữ liệu từ `data/*.json` **chỉ khi bảng còn rỗng**

Ba file JSON trong `data/` **chỉ được đọc, không bao giờ bị ghi đè**. Muốn nạp lại dữ liệu gốc: xoá `office_booking.db` rồi chạy lại.

## 4. Bảng định tuyến

### Trang công khai
| Route | Chức năng |
|---|---|
| `GET /` | Trang chủ — lưới lịch theo ngày |
| `GET /about` | Về chúng tôi (có nhúng Google Maps) |
| `GET /rooms` | Danh sách phòng + kiểm tra phòng trống |
| `GET,POST /login` · `/register` · `POST /logout` | Tài khoản nhân viên |

### Cần đăng nhập
| Route | Chức năng | Thao tác dữ liệu |
|---|---|---|
| `GET,POST /book` | Đặt phòng | **THÊM** |
| `GET /bookings/<id>` | Chi tiết lịch | |
| `GET,POST /bookings/<id>/edit` | Sửa lịch | **CẬP NHẬT** |
| `GET,POST /bookings/<id>/cancel` | Huỷ lịch | **XOÁ** (mềm) |
| `GET /history` | Lịch sử đặt phòng | |

### Khu quản trị (`admin_required`)
| Route | Chức năng | Thao tác dữ liệu |
|---|---|---|
| `GET /admin` | Bảng điều khiển | |
| `/admin/rooms/new` · `/<id>/edit` · `/<id>/status` · `/<id>/delete` | Quản lý phòng | **THÊM / CẬP NHẬT / XOÁ** |
| `/admin/users` + `/new` · `/<id>/edit` · `/<id>/reset-password` · `/<id>/delete` | Quản lý tài khoản | **THÊM / CẬP NHẬT / XOÁ** |
| `/admin/bookings` · `/admin/logs` | Lịch đặt & nhật ký | |

### API JSON
| Route | Trả về |
|---|---|
| `GET /api/rooms` | Danh sách phòng |
| `GET /api/availability` | Phòng trống theo tiêu chí + gợi ý thay thế |
| `GET /api/rooms/<id>/schedule` | Lịch của một phòng trong ngày |
| `GET,POST /api/bookings` | Đọc / tạo lịch đặt |

## 5. Các thuật toán chính

### 5.1 Phát hiện trùng lịch
Dùng phép giao khoảng thời gian tiêu chuẩn, thực hiện ngay trong câu SQL:

```sql
SELECT * FROM bookings
WHERE room_id = ? AND date = ? AND status = 'active'
  AND ? < end_time      -- giờ bắt đầu yêu cầu  <  giờ kết thúc lịch cũ
  AND ? > start_time    -- giờ kết thúc yêu cầu >  giờ bắt đầu lịch cũ
```

Nhờ so sánh chuỗi `HH:MM` (định dạng cố định 5 ký tự nên so sánh chuỗi cho kết quả đúng như so sánh thời gian), không cần chuyển kiểu. Điều kiện `status = 'active'` chính là chỗ khiến **lịch đã huỷ tự động trả lại khung giờ**.

Khi *sửa* lịch, truyền thêm `exclude_id` để lịch không tự coi mình là trùng với chính nó.

### 5.2 Lưới lịch trang chủ
Trang chủ vẽ lịch tất cả phòng theo trục thời gian **07:00–20:00** bằng **CSS thuần**, không dùng thư viện lịch nào:

1. `today_room_schedule()` ở backend tính sẵn vị trí `left` và độ rộng `width` của từng khối lịch theo **phần trăm**
2. Template chỉ việc đổ số phần trăm đó vào thuộc tính `style`
3. Lịch nằm ngoài khung giờ hiển thị được cắt cho vừa; lịch đã huỷ không xuất hiện
4. Vạch đỏ chỉ giờ hiện tại chỉ hiện khi đang xem đúng hôm nay

> Khung giờ **hiển thị** (07–20) rộng hơn khung giờ **cho phép đặt** (08–18) để lịch sát hai đầu vẫn nhìn thấy trọn vẹn.

### 5.3 Gợi ý phương án thay thế
Khi không còn phòng nào trống, `suggest_alternatives()` tìm theo thứ tự ưu tiên: cùng khung giờ nhưng phòng khác → cùng phòng nhưng khung giờ gần nhất còn trống → phòng lớn hơn.

## 6. Bảo mật

| Cơ chế | Cách làm |
|---|---|
| Mật khẩu | Băm bằng `werkzeug.security.generate_password_hash`, không bao giờ lưu thô |
| So sánh mật khẩu | `hmac.compare_digest` — chống dò mật khẩu qua thời gian phản hồi |
| CSRF | Mỗi phiên sinh một token bằng `secrets.token_urlsafe(32)`; **mọi POST đều kiểm tra**, sai thì trả 400 |
| Chuyển hướng | `_safe_next()` chỉ cho phép chuyển hướng nội bộ, chặn lừa sang web ngoài |
| Phân quyền | `authorize_booking()` đối chiếu `user_id`, kiểm tra cả khi hiển thị trang lẫn ngay trước khi ghi |
| Cấu hình nhạy cảm | `SECRET_KEY`, `ADMIN_PASSWORD`, `DEFAULT_USER_PASSWORD` đọc từ biến môi trường |

> ⚠️ Giá trị mặc định của ba biến trên chỉ dùng cho môi trường phát triển và bản demo học tập. Khi triển khai thật **bắt buộc** phải đặt lại.

## 7. Thiết kế giao diện

### 7.1 Hệ màu
Khai báo tập trung bằng biến CSS ở đầu `static/css/style.css`:

| Biến | Mã màu | Dùng cho |
|---|---|---|
| `--ob-primary` | `#2563eb` | Màu thương hiệu, nút chính, logo |
| `--ob-primary-dark` | `#1d4ed8` | Trạng thái hover |
| `--ob-ink` | `#0f172a` | Chữ chính |
| `--ob-muted` | `#64748b` | Chữ phụ |
| `--ob-surface` / `--ob-bg` | `#ffffff` / `#f1f5f9` | Nền thẻ / nền trang |
| `--ob-border` | `#e2e8f0` | Đường viền |
| `--ob-radius` | `14px` | Bo góc dùng chung |

### 7.2 Chữ
Dùng font hệ thống (`-apple-system`, `Segoe UI`, `Roboto`…) — tải tức thì, hiển thị quen mắt trên mọi máy, và không phụ thuộc dịch vụ font bên ngoài.

### 7.3 Logo

| File | Dùng ở đâu |
|---|---|
| `static/images/logo-mark.svg` | Biểu tượng vuông — favicon và thanh menu |
| `static/images/logo.svg` | Bản đầy đủ (biểu tượng + chữ) — trang Về chúng tôi, README |

**Ý tưởng:** một khối vuông bo góc màu `--ob-primary`, bên trong là ba thanh ngang mô phỏng **lưới lịch phòng theo trục thời gian**. Thanh ở hàng giữa được tô đặc, tượng trưng cho **một khung giờ đã được đặt** — chính là hành động cốt lõi của sản phẩm và cũng là hình ảnh người dùng nhìn thấy đầu tiên ở trang chủ.

Chữ trong logo tách hai màu: **Office** màu mực đậm, **Booking** màu thương hiệu — nhấn vào chữ "Booking" vì đó là chức năng chính.

Logo vẽ bằng **SVG**, nên sắc nét ở mọi kích thước, từ favicon 16px tới bảng hiệu lớn, mà dung lượng chưa tới 1KB.

### 7.4 Responsive
Bootstrap lo phần lưới. Các bảng và lưới lịch được bọc trong khung cuộn ngang riêng để trang chính không bao giờ bị tràn ngang trên điện thoại.

## 8. Triển khai

Chạy trên **Vercel** dưới dạng hàm serverless.

Vercel có **filesystem chỉ đọc**, chỉ thư mục `/tmp` mới ghi được. Vì `database.py` đã cho phép đổi đường dẫn database qua biến môi trường `OFFICE_BOOKING_DB`, chỉ cần trỏ biến này vào `/tmp/office_booking.db` là chạy được — **không phải sửa một dòng mã nào**.

Hệ quả: mỗi lần hàm khởi động lạnh, `init_db()` nạp lại dữ liệu mẫu từ `data/*.json`. Các thao tác thêm/sửa/xoá hoạt động bình thường, nhưng dữ liệu sẽ trở về trạng thái mẫu sau một thời gian không ai truy cập. Đây là **đánh đổi có chủ đích** cho một bản demo học tập; nếu cần lưu vĩnh viễn thì chuyển sang SQLite dạng dịch vụ (ví dụ Turso) mà vẫn giữ nguyên kiến trúc.

| File | Vai trò |
|---|---|
| `api/index.py` | Điểm vào WSGI. **Đặt biến môi trường trước khi `import app`**, vì `database.py` đọc đường dẫn database ngay lúc import |
| `vercel.json` | Điều hướng mọi request vào Flask để Flask tự phục vụ cả `/static` |

> Khi cấu hình trên Vercel phải đặt **Root Directory** trỏ vào thư mục `Project Booking - CODE`, vì mã nguồn nằm trong thư mục con chứ không ở gốc repo.

---

Tài liệu liên quan: [README.md](README.md) — hướng dẫn cài đặt · [PRD.md](PRD.md) — yêu cầu sản phẩm
