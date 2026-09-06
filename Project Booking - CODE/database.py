"""Khởi tạo SQLite và nạp dữ liệu gốc từ thư mục data/.

Hai file JSON trong data/ chỉ được ĐỌC, không bao giờ bị ghi đè.
"""

import json
import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ROOMS_JSON = os.path.join(DATA_DIR, "rooms.json")
BOOKINGS_JSON = os.path.join(DATA_DIR, "bookings.json")
USERS_JSON = os.path.join(DATA_DIR, "users.json")

# Mật khẩu dùng chung cho các tài khoản mẫu khi khởi tạo lần đầu.
# Đặt biến môi trường DEFAULT_USER_PASSWORD khi triển khai thật.
DEFAULT_USER_PASSWORD = os.environ.get("DEFAULT_USER_PASSWORD", "123456")
DB_PATH = os.environ.get("OFFICE_BOOKING_DB", os.path.join(BASE_DIR, "office_booking.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id        TEXT PRIMARY KEY,
    name      TEXT    NOT NULL,
    floor     INTEGER NOT NULL,
    capacity  INTEGER NOT NULL,
    equipment TEXT    NOT NULL DEFAULT '[]',
    image     TEXT,
    status    TEXT    NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS bookings (
    id           TEXT PRIMARY KEY,
    room_id      TEXT NOT NULL,
    date         TEXT NOT NULL,
    start_time   TEXT NOT NULL,
    end_time     TEXT NOT NULL,
    booked_by    TEXT NOT NULL,
    department   TEXT NOT NULL,
    purpose      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    cancelled_at TEXT,
    user_id      TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (room_id) REFERENCES rooms (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Tài khoản nhân viên. Mật khẩu luôn lưu dưới dạng băm, không bao giờ lưu thô.
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    department    TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bookings_room_date ON bookings (room_id, date);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings (date);

-- Nhật ký thay đổi của từng lịch đặt. Mỗi lần thao tác ghi đúng một dòng;
-- các trường bị đổi được gói trong cột changes dưới dạng JSON.
CREATE TABLE IF NOT EXISTS booking_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id TEXT NOT NULL,
    action     TEXT NOT NULL,
    actor      TEXT NOT NULL,
    changes    TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (booking_id) REFERENCES bookings (id)
);

CREATE INDEX IF NOT EXISTS idx_booking_logs_booking ON booking_logs (booking_id, id);
"""


def get_connection():
    """Mở kết nối SQLite với row factory dạng dict và bật ràng buộc khoá ngoại."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _seed_rooms(conn):
    rooms = _load_json(ROOMS_JSON)
    conn.executemany(
        """INSERT INTO rooms (id, name, floor, capacity, equipment, image, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                room["id"],
                room["name"],
                int(room["floor"]),
                int(room["capacity"]),
                json.dumps(room.get("equipment", []), ensure_ascii=False),
                room.get("image"),
                room.get("status", "active"),
            )
            for room in rooms
        ],
    )
    return len(rooms)


def _seed_bookings(conn):
    bookings = _load_json(BOOKINGS_JSON)
    conn.executemany(
        """INSERT INTO bookings
               (id, room_id, date, start_time, end_time, booked_by, department, purpose)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                bk["id"],
                bk["roomId"],
                bk["date"],
                bk["startTime"],
                bk["endTime"],
                bk["bookedBy"],
                bk["department"],
                bk["purpose"],
            )
            for bk in bookings
        ],
    )
    return len(bookings)


def _column_exists(conn, table, column):
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _migrate(conn):
    """Bổ sung cột mới cho database đã tạo từ phiên bản trước."""
    if not _column_exists(conn, "bookings", "status"):
        conn.execute("ALTER TABLE bookings ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    if not _column_exists(conn, "bookings", "cancelled_at"):
        conn.execute("ALTER TABLE bookings ADD COLUMN cancelled_at TEXT")
    if not _column_exists(conn, "bookings", "user_id"):
        conn.execute("ALTER TABLE bookings ADD COLUMN user_id TEXT")


def _seed_users(conn):
    """Nạp tài khoản mẫu, băm mật khẩu mặc định trước khi lưu."""
    users = _load_json(USERS_JSON)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        """INSERT INTO users (id, username, full_name, department, password_hash, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (
                user["id"],
                user["username"],
                user["fullName"],
                user["department"],
                generate_password_hash(DEFAULT_USER_PASSWORD),
                now,
            )
            for user in users
        ],
    )
    return len(users)


def _backfill_logs(conn):
    """Ghi một mốc khởi đầu cho các lịch đã có trước khi hệ thống lưu nhật ký.

    Nhờ vậy mọi booking đều có ít nhất một dòng lịch sử, kể cả dữ liệu nạp từ
    JSON hoặc tạo ra ở phiên bản chưa có bảng booking_logs.
    """
    if conn.execute("SELECT COUNT(*) FROM booking_logs").fetchone()[0]:
        return 0

    rows = conn.execute("SELECT id, booked_by FROM bookings").fetchall()
    if not rows:
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        """INSERT INTO booking_logs (booking_id, action, actor, changes, created_at)
           VALUES (?, 'imported', ?, '[]', ?)""",
        [(row["id"], row["booked_by"], now) for row in rows],
    )
    return len(rows)


def _link_bookings_to_users(conn):
    """Gắn user_id cho các booking đang chưa có chủ, dựa trên tên trùng khớp tài khoản.

    Chỉ chạm vào các dòng đang NULL, không ghi đè lựa chọn đã có sẵn. Nhờ đó
    các booking nạp từ JSON (hoặc tạo trước khi có đăng nhập) mà trùng tên với
    một tài khoản thật sẽ được nhân viên đó tự quản lý được.
    """
    conn.execute(
        """UPDATE bookings
              SET user_id = (SELECT u.id FROM users u WHERE u.full_name = bookings.booked_by)
            WHERE user_id IS NULL
              AND EXISTS (SELECT 1 FROM users u WHERE u.full_name = bookings.booked_by)"""
    )


def init_db():
    """Tạo bảng nếu chưa có và nạp dữ liệu gốc khi bảng còn rỗng."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        summary = {"rooms": 0, "bookings": 0, "users": 0, "seeded": False}

        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            summary["users"] = _seed_users(conn)
            summary["seeded"] = True

        if conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
            summary["rooms"] = _seed_rooms(conn)
            summary["seeded"] = True

        if conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 0:
            summary["bookings"] = _seed_bookings(conn)
            summary["seeded"] = True

        summary["logs_backfilled"] = _backfill_logs(conn)
        _link_bookings_to_users(conn)
        conn.commit()
        return summary
    finally:
        conn.close()
