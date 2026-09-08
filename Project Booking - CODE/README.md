<img src="static/images/logo.svg" alt="Office Booking" width="260">

Website nội bộ quản lý và đặt phòng họp cho văn phòng công ty.
Backend Flask, dữ liệu lưu trong SQLite, giao diện Jinja2 + Bootstrap 5.

## Tài liệu

| File | Nội dung |
|---|---|
| **README.md** | File này — hướng dẫn cài đặt, chạy và tra cứu tính năng |
| **[PRD.md](PRD.md)** | *Product Requirements Document* — sản phẩm **làm gì** và **vì sao**: bối cảnh, người dùng mục tiêu, user stories, danh sách chức năng, quy tắc nghiệp vụ, phạm vi |
| **[DESIGN.md](DESIGN.md)** | Thiết kế kỹ thuật — hệ thống được xây **như thế nào**: kiến trúc 3 lớp, schema database, bảng định tuyến, thuật toán chống trùng lịch, bảo mật, hệ màu và logo |

## Cài đặt và chạy

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Mở trình duyệt tại http://localhost:5000 (đổi cổng bằng biến môi trường `PORT`).

Trang quản trị nằm ở `/admin`, mật khẩu mặc định là `admin123`. Nhân viên đăng
nhập ở `/login` với 3 tài khoản mẫu (`an.nv`, `binh.tt`, `cuong.lm`), mật khẩu
mặc định `123456`.

Khi triển khai thật, hãy đặt các biến môi trường sau **trước lần chạy đầu tiên**
(mật khẩu nhân viên được băm ngay lúc nạp dữ liệu nên đổi sau sẽ không có tác dụng):

```bash
export SECRET_KEY="chuoi-ngau-nhien-dai"
export ADMIN_PASSWORD="mat-khau-cua-ban"
export DEFAULT_USER_PASSWORD="mat-khau-nhan-vien"
```

Lần chạy đầu tiên, ứng dụng tự tạo file `office_booking.db` và nạp dữ liệu từ
`data/rooms.json` và `data/bookings.json`. Hai file JSON này chỉ được đọc,
không bao giờ bị ghi đè. Muốn nạp lại dữ liệu gốc: xoá `office_booking.db`
rồi chạy lại ứng dụng.

## Cấu trúc thư mục

```
app.py                  Routes web + API JSON
database.py             Schema SQLite, kết nối, nạp dữ liệu gốc từ JSON
services.py             Nghiệp vụ: lọc phòng, kiểm tra trùng lịch, tạo booking
data/                   Dữ liệu gốc (chỉ đọc)
templates/              base.html + các trang + _macros.html
templates/admin/        Các trang quản trị
static/css/style.css    Giao diện
static/js/              main.js (dùng chung), availability.js, booking.js, admin.js
static/images/          Ảnh phòng họp (xem mục Ảnh phòng bên dưới)
```

## Cơ sở dữ liệu

`rooms(id, name, floor, capacity, equipment, image, status)` – `equipment` lưu
dạng chuỗi JSON.

`bookings(id, room_id, date, start_time, end_time, booked_by, department,
purpose, status, cancelled_at, created_at)` với khoá ngoại
`bookings.room_id → rooms.id`.

`status` nhận giá trị `active` hoặc `cancelled`. Huỷ lịch là **huỷ mềm**: bản
ghi vẫn nằm trong lịch sử để truy vết, nhưng không còn tính vào kiểm tra trùng
lịch nên khung giờ được trả lại cho người khác đặt. Database tạo từ phiên bản
trước sẽ được tự động bổ sung hai cột này khi khởi động.

## Lưới lịch phòng ở trang chủ

Trang chủ hiển thị lịch tất cả các phòng theo **ngày xem được** (mặc định là
hôm nay), dạng lưới: mỗi hàng là một phòng, trục ngang là khung giờ hành
chính (mặc định **07:00–20:00**, đổi được qua `GRID_START_HOUR`/
`GRID_END_HOUR` trong `services.py`). Lịch đã đặt hiện thành khối màu đúng
vị trí và độ dài theo giờ; đưa chuột vào khối để xem người đặt, phòng ban,
mục đích. Có vạch đỏ đánh dấu giờ hiện tại (chỉ hiện khi đang xem đúng hôm
nay và đang trong khung giờ hành chính). Phòng đang bảo trì có nền vân chéo
và chú thích riêng, không lẫn với ô trống.

Toàn bộ vị trí/độ rộng (tính theo %) được tính sẵn ở backend
(`services.today_room_schedule`) và vẽ bằng CSS thuần — không cần JavaScript
hay thư viện lịch ngoài. Lịch nằm ngoài khung giờ hiển thị (vd bắt đầu 06:00)
được cắt cho vừa khung; lịch đã huỷ không xuất hiện.

**Tương tác được theo ngày và khung giờ:**

* **Đổi ngày xem**: mũi tên ‹ › lùi/tiến 1 ngày, nút "Hôm nay" quay về ngày
  thực tế, và một ô chọn ngày để nhảy thẳng đến ngày bất kỳ — tất cả qua query
  param `?date=YYYY-MM-DD`, không cần JavaScript. Ngày truyền vào sai định
  dạng thì tự động rơi về hôm nay thay vì báo lỗi. Chỉ phần lưới lịch đổi theo
  ngày xem; các thẻ thống kê và bảng "Lịch họp sắp tới" luôn bám theo ngày
  thực tế.
* **Đặt nhanh từ ô trống**: bấm vào khoảng trống trên track của một phòng
  đang hoạt động sẽ tính ra khung giờ tương ứng (làm tròn về mốc 30 phút, mặc
  định đặt 1 giờ) và chuyển sang `/book` với phòng/ngày/giờ đã điền sẵn —
  dùng `static/js/home-grid.js`, một script nhỏ tính % vị trí click rồi suy
  ra giờ, không có thư viện ngoài. Bấm vào khối đã có lịch thì không có gì
  xảy ra (tooltip vẫn hiển thị bình thường); phòng đang bảo trì không bấm
  đặt nhanh được.

**Khi số phòng vượt quá 10**, lưới tự động gộp theo tầng: mỗi tầng là một
khối `<details>`/`<summary>` gốc HTML thu gọn/mở rộng được, mặc định mở hết
(không ẩn gì cho tới khi người dùng tự bấm). Hàng mốc giờ ở đầu lưới luôn
tách riêng, không lặp lại theo từng tầng, để cột giờ vẫn thẳng hàng khi cuộn
ngang dù đang xem tầng nào. Từ 10 phòng trở xuống, lưới vẫn hiển thị phẳng
như trước (không có khối tầng nào) — hiện tại (6 phòng) chưa đủ để kích hoạt
chế độ gộp.

## Quy tắc trùng lịch

Hai lịch trùng nhau khi cùng phòng, cùng ngày và:

```
requested_start < existing_end AND requested_end > existing_start
```

Hai khung giờ tiếp giáp (09:00–10:00 và 10:00–11:00) **không** tính là trùng.

Việc kiểm tra trùng lịch khi lưu booking nằm trong cùng một transaction ghi
(`BEGIN IMMEDIATE`), nên khi hai người gửi yêu cầu cho cùng phòng và cùng
khung giờ tại cùng thời điểm, chỉ một yêu cầu được lưu, yêu cầu còn lại nhận
thông báo trùng lịch.

## Chặn đặt lịch quá khứ và giới hạn khung giờ hành chính

Khi **tạo lịch mới**, hệ thống chặn:

* **Ngày trong quá khứ** — không thể chọn ngày trước hôm nay.
* **Giờ đã qua trong ngày hôm nay** — nếu chọn đúng hôm nay, giờ bắt đầu phải
  lớn hơn giờ hiện tại.
* **Ngoài khung giờ hành chính `08:00–18:00`** — giờ bắt đầu không được trước
  08:00, giờ kết thúc không được sau 18:00.
* **Thời lượng cuộc họp** — tối thiểu 15 phút, tối đa 4 giờ.

Khung giờ hành chính này (`BOOKING_MIN_HOUR`/`BOOKING_MAX_HOUR` trong
`services.py`) là quy tắc **tạo/sửa lịch**, tách biệt với khung giờ **hiển thị**
của lưới lịch ở trang chủ (07:00–20:00, xem mục "Lưới lịch phòng ở trang chủ")
— hai khung giờ này cố ý khác nhau: lưới hiển thị rộng hơn để không cắt mất các
lịch cũ/nhập tay nằm ngoài giờ hành chính hiện tại, còn khung tạo lịch thì siết
chặt theo giờ làm việc thực tế.

Khi **sửa lịch đã có** (`update_booking`), quy tắc "ngày trong quá khứ" vẫn áp
dụng như bình thường — không thể dời một lịch sang một ngày đã qua. Riêng nhánh
"giờ đã qua trong ngày hôm nay" được **miễn trừ**, để không chặn việc sửa các
trường khác (vd. mục đích cuộc họp, số người) của một cuộc họp đang diễn ra
hoặc vừa mới bắt đầu trong hôm nay. Khung giờ hành chính và giới hạn thời lượng
vẫn được kiểm tra đầy đủ khi sửa.

Validation được lặp lại ở cả hai phía để vừa có trải nghiệm tức thời vừa an
toàn:

* **Phía trình duyệt** — `static/js/main.js` (`validateSlot`) chặn ngay khi
  submit, không cần round-trip server.
* **Phía server** — `services.py` (`validate_slot`) là nguồn xác thực cuối
  cùng, luôn chạy dù JS có bị tắt hay bị qua mặt.

Quản trị viên **không** được miễn trừ các quy tắc này — quyền admin chỉ bỏ qua
kiểm tra **quyền sở hữu** (xem mục "Quyền sửa và huỷ lịch đặt"), không bỏ qua
các quy tắc về **tính hợp lệ dữ liệu** như múi giờ hay thời lượng.

## Các trang

| Đường dẫn | Nội dung |
|---|---|
| `/login` | Đăng nhập nhân viên, có gợi ý sẵn các tài khoản để bấm chọn nhanh |
| `/register` | Tự đăng ký tài khoản nhân viên, đăng ký xong tự động đăng nhập |
| `/` | Tổng quan: số phòng hoạt động, tổng lượt đặt, lịch đặt hôm nay, lưới lịch phòng theo khung giờ, lịch họp sắp tới |
| `/rooms` | Danh sách phòng (lọc theo tầng / sức chứa / trạng thái) + biểu mẫu kiểm tra phòng trống |
| `/book` | Tạo lịch đặt mới |
| `/history` | Lịch sử booking, lọc theo ngày / phòng / phòng ban / người đặt |
| `/bookings/<id>` | Chi tiết một lịch đặt kèm toàn bộ lịch sử thay đổi |
| `/bookings/<id>/edit` | Sửa lịch đặt |
| `/bookings/<id>/cancel` | Trang xác nhận huỷ lịch đặt |
| `/admin/login` | Đăng nhập quản trị bằng mật khẩu chung |
| `/admin` | Bảng quản trị: thống kê, bảng phòng kèm thao tác sửa / bảo trì / xoá |
| `/admin/rooms/new`, `/admin/rooms/<id>/edit` | Thêm và sửa phòng họp |
| `/admin/bookings` | Quản lý booking, lọc theo tình trạng và huỷ lịch |
| `/admin/logs` | Nhật ký thay đổi toàn hệ thống, lọc theo booking / thao tác / người thao tác |
| `/admin/users` | Quản lý tài khoản nhân viên: thêm, sửa, đặt lại mật khẩu, xoá |

Mọi thao tác ghi ở khu vực quản trị đều đi qua POST kèm token chống CSRF và
hộp thoại xác nhận.

## Đăng nhập và đăng ký nhân viên

Bảng `users(id, username, full_name, department, password_hash, created_at)`,
nạp từ `data/users.json` khi chạy lần đầu (3 tài khoản mẫu). Mật khẩu **luôn
lưu dưới dạng băm** (`werkzeug.security`, mỗi tài khoản một salt riêng) — file
JSON không chứa mật khẩu.

Nhân viên có 2 cách để có tài khoản:

* **Tự đăng ký** ở `/register`: nhập họ tên, phòng ban, tên đăng nhập, mật
  khẩu. Đăng ký xong tự động đăng nhập luôn, không cần đăng nhập lại.
* **Admin tạo hộ** ở `/admin/users` (xem mục Quản trị bên dưới).

Ràng buộc khi tạo tài khoản: họ tên và phòng ban không được rỗng; tên đăng
nhập phải bắt đầu bằng chữ cái, chỉ gồm chữ thường/số/`.`/`_`/`-` (3–30 ký tự)
và không trùng tài khoản đã có; mật khẩu tối thiểu 6 ký tự và phải nhập lại
khớp nhau.

**Chưa đăng nhập vẫn dùng được gần như mọi thứ**: xem trang chủ, duyệt phòng,
kiểm tra phòng trống, xem lịch sử, mở và điền biểu mẫu đặt phòng. Chỉ **bước
hoàn tất đặt phòng** là bị chặn — hệ thống trả về thông báo cần đăng nhập, giữ
nguyên dữ liệu đã nhập và gắn nó vào link đăng nhập để quay lại không phải gõ lại.

Khi đã đăng nhập, ô *Người đặt* và *Phòng ban* được điền sẵn từ tài khoản và
khoá lại. Backend luôn ghi đè hai trường này bằng thông tin của tài khoản, nên
không thể đặt phòng dưới danh nghĩa người khác kể cả khi sửa HTML. Booking mới
được gắn `user_id` trỏ về tài khoản đã đặt.

Đăng nhập nhân viên **tách biệt** với đăng nhập quản trị: tài khoản nhân viên
không vào được khu quản trị. Ngược lại, **quản trị viên được miễn đăng nhập
tài khoản nhân viên cho mọi thao tác** — đặt phòng, sửa, huỷ đều làm được ngay
sau khi đăng nhập `/admin`. Khi admin tự đặt phòng mà không kèm tài khoản nhân
viên, ô *Người đặt*/*Phòng ban* để trống cho gõ tay và booking đó không gắn
`user_id` nào (chỉ quản trị viên quản lý được về sau).

## Quyền sửa và huỷ lịch đặt

Nút **Sửa** và **Huỷ** xuất hiện ở trang Lịch sử với mọi lịch còn hiệu lực và
chưa kết thúc, nhưng chỉ **chủ lịch** (tài khoản có `user_id` trùng với booking)
hoặc **quản trị viên** mới thấy nút. Việc xác thực dựa trên **danh tính đăng
nhập thật** (so khớp `user_id`), không còn gõ lại tên để xác nhận như trước:

* Chưa đăng nhập → chuyển hướng sang `/login`, quay lại đúng trang sau khi vào.
* Đăng nhập nhưng không phải chủ lịch → bị chặn với thông báo rõ ràng, có gợi ý
  liên hệ quản trị viên.
* Lịch tạo trước khi có đăng nhập (hoặc tạo qua admin không kèm tài khoản) thì
  **không ai tự quản lý được**, chỉ admin thao tác được — vì không có `user_id`
  để đối chiếu.
* Quản trị viên bỏ qua toàn bộ các kiểm tra trên.

Khi khởi động, hệ thống tự **gắn lại `user_id`** cho các booking cũ nếu tên
người đặt (`booked_by`) trùng khớp chính xác với tên một tài khoản đang có —
chỉ chạm vào các dòng chưa có chủ, không ghi đè lựa chọn đã tồn tại.

Lịch đã kết thúc hoặc đã huỷ thì không sửa/huỷ được nữa. Khi sửa, lịch đang sửa
được loại khỏi phép kiểm tra trùng giờ để nó không tự xung đột với chính mình.

## Quản trị tài khoản (`/admin/users`)

Admin xem danh sách tài khoản kèm số lịch đặt của từng người, và có thể:

* **Thêm** tài khoản mới (giống form đăng ký, admin gõ luôn mật khẩu ban đầu).
* **Sửa** họ tên / phòng ban / tên đăng nhập — đổi tên đăng nhập không ảnh
  hưởng tới các lịch đã đặt trước đó (nhật ký và lịch sử vẫn giữ tên cũ tại
  thời điểm đó).
* **Đặt lại mật khẩu** mà không cần biết mật khẩu cũ — dùng khi nhân viên quên
  mật khẩu, thay vì phải xoá và tạo lại tài khoản.
* **Xoá** tài khoản — chỉ xoá được khi tài khoản đó **chưa từng đứng tên lịch
  đặt nào** (kể cả lịch đã huỷ), để không phá vỡ khoá ngoại `bookings.user_id`.
  Nếu chỉ muốn ngăn nhân viên đăng nhập, hãy đặt lại mật khẩu thay vì xoá.

## Nhật ký thay đổi

Bảng `booking_logs(id, booking_id, action, actor, changes, created_at)` ghi lại
mọi thao tác lên lịch đặt. Mỗi lần thao tác là **một dòng**, các trường bị đổi
được gói trong cột `changes` dưới dạng JSON: `[{field, label, old, new}]`.

| `action` | Khi nào ghi |
|---|---|
| `imported` | Mốc khởi đầu cho lịch có sẵn trước khi hệ thống lưu nhật ký |
| `created` | Tạo lịch đặt mới |
| `updated` | Sửa lịch, kèm diff của từng trường thay đổi |
| `cancelled` | Huỷ lịch |

**Nhật ký chỉ quản trị viên xem được**, tại `/admin/logs` (lọc theo mã booking,
loại thao tác, người thao tác) và ở khối "Hoạt động gần đây" trên bảng quản trị.
Trang chi tiết booking `/bookings/<id>` vẫn công khai nhưng chỉ hiện số lần đã
chỉnh sửa, không hiện nội dung thay đổi hay tên người thao tác.

Vài điểm trong thiết kế:

* Ghi nhật ký nằm trong **cùng transaction** với thao tác gốc, nên thao tác
  thất bại (trùng lịch, sai giờ, sai tên xác nhận) không để lại dòng rác.
* Trường phòng họp lưu **tên phòng tại thời điểm đó**, nên đổi tên phòng về sau
  không làm sai lệch nhật ký cũ.
* Bấm lưu mà không đổi gì thì không ghi nhật ký.
* Cột `actor` ghi tên người dùng đã xác nhận, hoặc `Quản trị viên` khi thao tác
  từ khu quản trị.

## API JSON

| Endpoint | Mô tả |
|---|---|
| `GET /api/rooms` | Danh sách phòng, hỗ trợ `floor`, `min_capacity`, `status` |
| `GET /api/availability` | Phòng còn trống, tham số `date`, `start_time`, `end_time`, `attendees` |
| `GET /api/rooms/<id>/schedule?date=` | Lịch đã đặt của một phòng trong ngày |
| `GET /api/bookings` | Lịch sử booking, hỗ trợ các bộ lọc như trang `/history` |
| `POST /api/bookings` | Tạo booking (JSON hoặc form). Trả 400 nếu dữ liệu sai, 409 nếu trùng lịch |

## Ảnh phòng

`data/rooms.json` trỏ tới các đường dẫn dạng `images/room-sen.jpg`. Đặt các
file ảnh tương ứng vào `static/images/` là ảnh sẽ tự hiển thị. Khi chưa có
ảnh, hệ thống hiển thị khối dự phòng mang mã phòng thay cho ảnh vỡ.

## Kiểm tra dữ liệu

Cả trình duyệt và backend đều kiểm tra: ngày không được rỗng, giờ kết thúc
phải lớn hơn giờ bắt đầu, số người phải lớn hơn 0. Backend còn kiểm tra thêm
phòng có tồn tại, phòng có đang `active` hay không, sức chứa và trùng lịch.
