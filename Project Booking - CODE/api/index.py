"""Điểm vào WSGI cho Vercel.

Vercel chạy serverless với filesystem chỉ đọc, chỉ thư mục /tmp mới ghi được.
Vì vậy phải trỏ SQLite vào /tmp. Mỗi lần function khởi động lạnh, init_db()
trong app.py sẽ tự nạp lại dữ liệu mẫu từ data/*.json.

Thứ tự các dòng dưới đây quan trọng: OFFICE_BOOKING_DB phải được đặt TRƯỚC
khi import app, vì database.py đọc biến này ngay lúc import module.
"""

import os
import sys

# Thư mục cha (chứa app.py, services.py, database.py) chưa nằm trong sys.path
# khi Vercel nạp file này, nên phải thêm vào thủ công.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# setdefault: nếu đã khai báo biến môi trường trên dashboard Vercel thì tôn
# trọng giá trị đó, ở đây chỉ là mạng lưới an toàn phòng khi quên khai báo.
os.environ.setdefault("OFFICE_BOOKING_DB", "/tmp/office_booking.db")

from app import app  # noqa: E402  (bắt buộc import sau khi đặt biến môi trường)

# Vercel tìm biến tên `app` trong file này để làm WSGI handler.
__all__ = ["app"]
