# PRD — Office Booking

> **PRD** (Product Requirements Document) là tài liệu mô tả **sản phẩm cần làm gì và tại sao**.
> Nó trả lời: giải quyết vấn đề gì, cho ai, gồm những chức năng nào, ràng buộc ra sao.
> PRD **không** nói về cách lập trình — phần đó nằm ở [DESIGN.md](DESIGN.md).

| | |
|---|---|
| Sản phẩm | Office Booking — hệ thống đặt phòng họp nội bộ |
| Phiên bản | 1.0 |
| Cập nhật | 08/09/2026 |

---

## 1. Bối cảnh và vấn đề

Ở nhiều văn phòng, phòng họp được đặt bằng cách hô nhau, nhắn nhóm chat hoặc ghi vào một file Excel dùng chung. Cách làm này sinh ra bốn vấn đề lặp đi lặp lại:

1. **Trùng lịch** — hai nhóm cùng tin là mình đã đặt được phòng, tới giờ mới phát hiện
2. **Không nhìn được toàn cảnh** — muốn biết phòng nào trống lúc 14h phải mở từng file, hỏi từng người
3. **Không truy vết được** — lịch bị đổi hoặc biến mất mà không rõ ai làm, làm lúc nào
4. **Phòng bảo trì vẫn bị đặt** — không có chỗ nào đánh dấu phòng đang sửa chữa

Office Booking giải quyết bằng một website nội bộ: mọi lịch đặt nằm trên một màn hình duy nhất, hệ thống tự chặn trùng giờ, và mọi thay đổi đều được ghi nhật ký.

## 2. Người dùng mục tiêu

| Nhóm | Họ là ai | Họ cần gì |
|---|---|---|
| **Nhân viên** | Người tổ chức cuộc họp | Tìm nhanh phòng trống đúng khung giờ và đủ chỗ ngồi, đặt xong trong vài bước, tự sửa/huỷ lịch của mình |
| **Quản trị viên** | Hành chính / IT nội bộ | Quản lý danh sách phòng, tài khoản nhân viên, xử lý lịch có vấn đề, xem nhật ký thay đổi |

## 3. User stories

**Nhân viên**
- Là nhân viên, tôi muốn **xem lịch tất cả phòng trong ngày trên một lưới** để biết ngay khung giờ nào còn trống
- Là nhân viên, tôi muốn **nhập khung giờ và số người rồi được gợi ý phòng phù hợp**, thay vì tự dò từng phòng
- Là nhân viên, tôi muốn **được gợi ý phương án thay thế khi không còn phòng nào trống**, để không phải mò lại từ đầu
- Là nhân viên, tôi muốn **đặt phòng gấp bằng một nút bấm** khi cần họp ngay
- Là nhân viên, tôi muốn **sửa hoặc huỷ lịch của chính mình**, và không ai sửa được lịch của tôi
- Là nhân viên, tôi muốn **xem lại lịch sử đặt phòng của mình**

**Quản trị viên**
- Là quản trị viên, tôi muốn **thêm/sửa/xoá phòng họp** khi công ty đổi mặt bằng
- Là quản trị viên, tôi muốn **đánh dấu phòng đang bảo trì** để không ai đặt nhầm
- Là quản trị viên, tôi muốn **quản lý tài khoản nhân viên** và đặt lại mật khẩu khi họ quên
- Là quản trị viên, tôi muốn **huỷ được mọi lịch** khi có sự cố
- Là quản trị viên, tôi muốn **xem nhật ký ai đã thay đổi gì**, để truy vết khi có tranh chấp

## 4. Danh sách chức năng

### 4.1 Dành cho mọi người
- Trang chủ: lưới lịch toàn bộ phòng theo ngày, chọn được ngày xem
- Danh sách phòng: lọc theo tầng và sức chứa
- Kiểm tra phòng trống theo ngày + khung giờ + số người
- Gợi ý phương án thay thế khi hết phòng
- Nút "đặt nhanh phòng trống bây giờ"
- Trang giới thiệu, có nhúng bản đồ Google Maps vị trí văn phòng

### 4.2 Dành cho nhân viên (cần đăng nhập)
- Đăng ký tài khoản, đăng nhập, đăng xuất
- **Đặt phòng** *(thêm dữ liệu)*
- **Sửa lịch đã đặt** *(cập nhật dữ liệu)*
- **Huỷ lịch** *(xoá dữ liệu — huỷ mềm, xem mục 5.3)*
- Xem chi tiết một lịch đặt kèm nhật ký thay đổi của lịch đó
- Xem lịch sử đặt phòng, lọc theo ngày / phòng / phòng ban / người đặt

### 4.3 Dành cho quản trị viên
- Đăng nhập khu quản trị bằng mật khẩu riêng
- Bảng điều khiển: số liệu tổng quan
- **Quản lý phòng**: thêm, sửa, xoá, chuyển trạng thái hoạt động ⇄ bảo trì
- **Quản lý tài khoản**: thêm, sửa, xoá, đặt lại mật khẩu
- Huỷ bất kỳ lịch nào
- Xem nhật ký hoạt động toàn hệ thống, lọc theo hành động / người thực hiện

## 5. Quy tắc nghiệp vụ

### 5.1 Ràng buộc khi đặt phòng
| Ràng buộc | Giá trị |
|---|---|
| Khung giờ cho phép đặt | 08:00 – 18:00 |
| Thời lượng tối thiểu | 15 phút |
| Thời lượng tối đa | 4 giờ |
| Số người dự kiến | 1 – 1000, và **không vượt sức chứa phòng** |
| Ngày giờ bắt đầu | Không được ở quá khứ |
| Phòng đang bảo trì | Không đặt được |

### 5.2 Chống trùng lịch
Hai lịch bị coi là trùng khi chúng **giao nhau về thời gian** trên **cùng một phòng, cùng một ngày**:

```
lịch_mới.bắt_đầu  <  lịch_cũ.kết_thúc
        VÀ
lịch_mới.kết_thúc >  lịch_cũ.bắt_đầu
```

Hai cuộc họp nối đuôi nhau (9:00–10:00 và 10:00–11:00) **không** tính là trùng.

### 5.3 Huỷ mềm
Huỷ lịch **không xoá dòng dữ liệu**, chỉ đổi `status` thành `cancelled` và ghi lại thời điểm huỷ. Lý do:
- Lịch sử vẫn còn để truy vết khi có tranh chấp
- Khung giờ đó **được trả lại ngay** cho người khác đặt, vì phép kiểm tra trùng lịch chỉ xét các lịch còn `active`

### 5.4 Phân quyền
- Nhân viên chỉ sửa/huỷ được lịch **do chính tài khoản mình tạo** (đối chiếu bằng `user_id`, không dựa vào tên gõ tay)
- Quản trị viên thao tác được với **mọi lịch**
- **Cuộc họp đã kết thúc không sửa/huỷ được**, kể cả quản trị viên
- Lịch đã huỷ rồi thì không huỷ lại

### 5.5 Ghi nhật ký
Mỗi lần tạo / sửa / huỷ đều ghi đúng **một dòng** vào nhật ký, kèm người thực hiện và danh sách trường đã đổi.

## 6. Ngoài phạm vi

Những thứ **cố ý không làm** ở phiên bản 1.0:
- Gửi email / thông báo nhắc họp
- Đồng bộ với Google Calendar, Outlook
- Đặt lịch lặp lại hàng tuần
- Duyệt lịch nhiều cấp
- Ứng dụng di động riêng (giao diện web đã responsive)
- Phân quyền nhiều vai trò (hiện chỉ có nhân viên và quản trị viên)

## 7. Tiêu chí hoàn thành

- [x] Đủ các trang: Trang chủ, Phòng họp, Đặt phòng, Lịch sử, Về chúng tôi, khu Quản trị — liên kết với nhau qua thanh menu
- [x] Dữ liệu lưu trong SQLite
- [x] Có đủ 3 thao tác thêm / sửa / xoá dữ liệu
- [x] Nhúng Google Maps ở trang Về chúng tôi
- [x] Không cho đặt trùng lịch
- [x] Mật khẩu lưu dạng băm, có chống giả mạo yêu cầu (CSRF)
- [x] Có logo thương hiệu riêng
- [x] Tài liệu: README.md, PRD.md, DESIGN.md
- [x] Mã nguồn công khai trên GitHub
- [ ] Chạy được online

---

Tài liệu liên quan: [README.md](README.md) — hướng dẫn cài đặt · [DESIGN.md](DESIGN.md) — thiết kế kỹ thuật
