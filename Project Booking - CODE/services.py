"""Nghiệp vụ đặt phòng: thống kê, lọc phòng, kiểm tra trùng lịch, tạo booking."""

import json
import re
import sqlite3
from datetime import date as date_cls, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
MAX_ATTENDEES = 1000

# Khung giờ hành chính cho phép đặt phòng, và giới hạn thời lượng mỗi lịch.
BOOKING_MIN_HOUR = 8
BOOKING_MAX_HOUR = 18
MIN_BOOKING_MINUTES = 15
MAX_BOOKING_MINUTES = 4 * 60

STATUS_LABELS = {
    "active": "Đang hoạt động",
    "maintenance": "Đang bảo trì",
    "inactive": "Ngừng sử dụng",
}

BOOKING_STATE_LABELS = {
    "upcoming": "Sắp diễn ra",
    "ongoing": "Đang diễn ra",
    "finished": "Đã kết thúc",
    "cancelled": "Đã huỷ",
}

ROOM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,20}$")
ROOM_STATUSES = ("active", "maintenance")

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,29}$")
MIN_PASSWORD_LENGTH = 6

# Các trường của lịch đặt được theo dõi trong nhật ký thay đổi.
TRACKED_FIELDS = {
    "room_id": "Phòng họp",
    "date": "Ngày họp",
    "start_time": "Giờ bắt đầu",
    "end_time": "Giờ kết thúc",
    "booked_by": "Người đặt",
    "department": "Phòng ban",
    "purpose": "Mục đích",
}

LOG_ACTION_LABELS = {
    "imported": "Nạp từ dữ liệu gốc",
    "created": "Tạo lịch đặt",
    "updated": "Cập nhật thông tin",
    "cancelled": "Huỷ lịch",
}


# --------------------------------------------------------------------------- #
# Chuyển đổi dữ liệu
# --------------------------------------------------------------------------- #

def room_to_dict(row):
    try:
        equipment = json.loads(row["equipment"] or "[]")
    except (TypeError, ValueError):
        equipment = []
    return {
        "id": row["id"],
        "name": row["name"],
        "floor": row["floor"],
        "capacity": row["capacity"],
        "equipment": equipment,
        "image": row["image"],
        "status": row["status"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
        "bookable": row["status"] == "active",
    }


def booking_to_dict(row, now=None):
    now = now or datetime.now()
    data = {
        "id": row["id"],
        "room_id": row["room_id"],
        "room_name": row["room_name"] if "room_name" in row.keys() else None,
        "date": row["date"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "booked_by": row["booked_by"],
        "department": row["department"],
        "purpose": row["purpose"],
        "status": row["status"] if "status" in row.keys() else "active",
        "user_id": row["user_id"] if "user_id" in row.keys() else None,
    }
    if data["status"] == "cancelled":
        data["state"] = "cancelled"
    else:
        data["state"] = booking_state(data["date"], data["start_time"], data["end_time"], now)
    data["state_label"] = BOOKING_STATE_LABELS[data["state"]]
    # Chỉ lịch còn hiệu lực và chưa kết thúc mới được sửa hoặc huỷ.
    data["cancellable"] = data["status"] == "active" and data["state"] != "finished"
    data["editable"] = data["cancellable"]
    return data


def booking_state(date_str, start_time, end_time, now=None):
    """Trả về 'upcoming' | 'ongoing' | 'finished' so với thời điểm hiện tại."""
    now = now or datetime.now()
    try:
        start = datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M")
        end = datetime.strptime(f"{date_str} {end_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "upcoming"
    if now < start:
        return "upcoming"
    if now < end:
        return "ongoing"
    return "finished"


# --------------------------------------------------------------------------- #
# Kiểm tra dữ liệu đầu vào (backend)
# --------------------------------------------------------------------------- #

def validate_slot(payload, now=None, check_past=True):
    """Kiểm tra ngày / giờ / số người. Trả về (dữ liệu đã chuẩn hoá, dict lỗi).

    check_past=False khi sửa một lịch đã có: lịch đang diễn ra dĩ nhiên có giờ
    bắt đầu nằm trong quá khứ so với hiện tại, nên không thể áp cùng quy tắc
    "không đặt được ngày/giờ đã qua" như lúc tạo mới, nếu không sẽ chặn nhầm
    việc sửa các lịch đang diễn ra (vốn vẫn được phép sửa).
    """
    now = now or datetime.now()
    errors = {}
    cleaned = {}

    raw_date = (payload.get("date") or "").strip()
    if not raw_date:
        errors["date"] = "Vui lòng chọn ngày họp."
    else:
        try:
            cleaned["date"] = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
        except ValueError:
            errors["date"] = "Ngày không hợp lệ (định dạng YYYY-MM-DD)."

    for field, label in (("start_time", "Giờ bắt đầu"), ("end_time", "Giờ kết thúc")):
        value = (payload.get(field) or "").strip()
        if not value:
            errors[field] = f"Vui lòng nhập {label.lower()}."
        elif not TIME_RE.match(value):
            errors[field] = f"{label} không hợp lệ (định dạng HH:MM)."
        else:
            cleaned[field] = value

    if "start_time" in cleaned and "end_time" in cleaned:
        if cleaned["end_time"] <= cleaned["start_time"]:
            errors["end_time"] = "Giờ kết thúc phải lớn hơn giờ bắt đầu."
        else:
            start_min = _time_to_minutes(cleaned["start_time"])
            end_min = _time_to_minutes(cleaned["end_time"])
            duration = end_min - start_min

            if start_min < BOOKING_MIN_HOUR * 60:
                errors["start_time"] = f"Giờ bắt đầu phải từ {BOOKING_MIN_HOUR:02d}:00 trở đi."
            elif end_min > BOOKING_MAX_HOUR * 60:
                errors["end_time"] = f"Giờ kết thúc phải trước {BOOKING_MAX_HOUR:02d}:00."
            elif duration < MIN_BOOKING_MINUTES:
                errors["end_time"] = f"Cuộc họp phải kéo dài ít nhất {MIN_BOOKING_MINUTES} phút."
            elif duration > MAX_BOOKING_MINUTES:
                errors["end_time"] = (
                    f"Cuộc họp không được kéo dài quá {MAX_BOOKING_MINUTES // 60} giờ.")

    if "date" in cleaned:
        requested_date = datetime.strptime(cleaned["date"], "%Y-%m-%d").date()
        # Dời lịch sang một ngày đã qua thì luôn chặn, kể cả khi sửa lịch —
        # không có lý do hợp lệ nào để làm việc đó. Chỉ riêng "giờ bắt đầu
        # của hôm nay đã trôi qua" mới được nới lỏng khi check_past=False,
        # để sửa được các lịch đang diễn ra (giờ bắt đầu vốn dĩ đã ở quá khứ).
        if requested_date < now.date():
            errors["date"] = "Không thể đặt lịch cho ngày trong quá khứ."
        elif check_past and requested_date == now.date() and "start_time" in cleaned:
            requested_dt = datetime.strptime(
                f"{cleaned['date']} {cleaned['start_time']}", "%Y-%m-%d %H:%M")
            if requested_dt < now:
                errors["start_time"] = "Giờ bắt đầu đã qua, vui lòng chọn giờ khác."

    if "attendees" in payload:
        raw_attendees = payload.get("attendees")
        raw_attendees = "" if raw_attendees is None else str(raw_attendees).strip()
        if raw_attendees == "":
            errors["attendees"] = "Vui lòng nhập số người dự kiến."
        else:
            try:
                attendees = int(raw_attendees)
            except ValueError:
                errors["attendees"] = "Số người phải là một số nguyên."
            else:
                if attendees <= 0:
                    errors["attendees"] = "Số người phải lớn hơn 0."
                elif attendees > MAX_ATTENDEES:
                    errors["attendees"] = f"Số người không được vượt quá {MAX_ATTENDEES}."
                else:
                    cleaned["attendees"] = attendees

    return cleaned, errors


def validate_booking(payload, check_past=True, now=None):
    """Kiểm tra toàn bộ dữ liệu của một lịch đặt mới."""
    cleaned, errors = validate_slot(payload, now=now, check_past=check_past)

    room_id = (payload.get("room_id") or "").strip()
    if not room_id:
        errors["room_id"] = "Vui lòng chọn phòng họp."
    else:
        cleaned["room_id"] = room_id

    for field, label in (
        ("booked_by", "Người đặt"),
        ("department", "Phòng ban"),
        ("purpose", "Mục đích cuộc họp"),
    ):
        value = (payload.get(field) or "").strip()
        if not value:
            errors[field] = f"Vui lòng nhập {label.lower()}."
        elif len(value) > 255:
            errors[field] = f"{label} không được vượt quá 255 ký tự."
        else:
            cleaned[field] = value

    return cleaned, errors


# --------------------------------------------------------------------------- #
# Truy vấn phòng
# --------------------------------------------------------------------------- #

def list_rooms(floor=None, min_capacity=None, status=None):
    sql = "SELECT * FROM rooms WHERE 1 = 1"
    params = []
    if floor not in (None, "", "all"):
        sql += " AND floor = ?"
        params.append(int(floor))
    if min_capacity not in (None, "", "all"):
        sql += " AND capacity >= ?"
        params.append(int(min_capacity))
    if status not in (None, "", "all"):
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY floor, name"

    conn = get_connection()
    try:
        return [room_to_dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def get_room(room_id, conn=None):
    own = conn is None
    conn = conn or get_connection()
    try:
        row = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        return room_to_dict(row) if row else None
    finally:
        if own:
            conn.close()


def list_floors():
    conn = get_connection()
    try:
        return [r["floor"] for r in conn.execute("SELECT DISTINCT floor FROM rooms ORDER BY floor")]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Kiểm tra phòng trống
# --------------------------------------------------------------------------- #

def _conflicting_bookings(conn, room_id, date, start_time, end_time, exclude_id=None):
    """Các lịch đã đặt bị trùng: requested_start < existing_end AND requested_end > existing_start.

    Lịch đã huỷ không tính là trùng, khung giờ đó được trả lại cho người khác.
    """
    sql = """
        SELECT * FROM bookings
        WHERE room_id = ? AND date = ? AND status = 'active'
          AND ? < end_time AND ? > start_time
    """
    params = [room_id, date, start_time, end_time]
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(sql, params).fetchall()


def find_available_rooms(date, start_time, end_time, attendees):
    """Phòng active, đủ sức chứa và không trùng lịch trong khung giờ yêu cầu."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT r.* FROM rooms r
            WHERE r.status = 'active'
              AND r.capacity >= ?
              AND NOT EXISTS (
                    SELECT 1 FROM bookings b
                    WHERE b.room_id = r.id
                      AND b.date = ?
                      AND b.status = 'active'
                      AND ? < b.end_time
                      AND ? > b.start_time
              )
            ORDER BY r.capacity, r.floor, r.name
            """,
            (attendees, date, start_time, end_time),
        ).fetchall()
        return [room_to_dict(r) for r in rows]
    finally:
        conn.close()


def is_room_available(room_id, date, start_time, end_time, conn=None):
    own = conn is None
    conn = conn or get_connection()
    try:
        return not _conflicting_bookings(conn, room_id, date, start_time, end_time)
    finally:
        if own:
            conn.close()


def room_schedule(room_id, date):
    """Lịch đã đặt của một phòng trong ngày, dùng để giải thích vì sao bị trùng."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT b.*, r.name AS room_name FROM bookings b
               JOIN rooms r ON r.id = b.room_id
               WHERE b.room_id = ? AND b.date = ? AND b.status = 'active'
               ORDER BY b.start_time""",
            (room_id, date),
        ).fetchall()
        return [booking_to_dict(r) for r in rows]
    finally:
        conn.close()


def _free_windows(booked_intervals, day_start, day_end):
    """Phần bù của `booked_intervals` (đã sắp theo giờ bắt đầu) trong [day_start, day_end)."""
    windows = []
    cursor = day_start
    for start, end in booked_intervals:
        start = max(start, day_start)
        end = min(end, day_end)
        if start >= end:
            continue
        if start > cursor:
            windows.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < day_end:
        windows.append((cursor, day_end))
    return windows


def _minutes_to_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def quick_slot(now=None, duration_minutes=30):
    """Khung giờ cho nút 'Đặt nhanh phòng trống bây giờ' ở trang chủ: làm tròn
    lên bội số 5 phút gần nhất từ hiện tại, kéo dài `duration_minutes`.

    Nếu hiện tại đang ngoài giờ hành chính (trước giờ mở cửa, hoặc không còn
    đủ chỗ cho `duration_minutes` trước giờ đóng cửa), trả về khung giờ mở
    cửa sớm nhất — hôm nay nếu chưa mở cửa, ngày mai nếu đã hết giờ.
    """
    now = now or datetime.now()
    rounded = -(-(now.hour * 60 + now.minute) // 5) * 5  # làm tròn lên bội số 5
    day = now.date()
    day_start = BOOKING_MIN_HOUR * 60
    day_end = BOOKING_MAX_HOUR * 60

    if rounded < day_start:
        start = day_start
    elif rounded + duration_minutes > day_end:
        day = day + timedelta(days=1)
        start = day_start
    else:
        start = rounded

    return {
        "date": day.isoformat(),
        "start_time": _minutes_to_time(start),
        "end_time": _minutes_to_time(start + duration_minutes),
    }


def suggest_alternatives(date, start_time, end_time, attendees, limit=3, now=None):
    """Khi không còn phòng nào trống đúng khung giờ yêu cầu: gợi ý khoảng trống
    gần nhất theo từng phòng, và các mốc giờ bắt đầu thay thế gần nhất.

    Thuật toán chỉ là tìm phần bù giữa các lịch đã đặt (đã sắp theo giờ bắt
    đầu) trong khung giờ hành chính của từng phòng đủ sức chứa — không kiểm
    tra trùng lịch qua truy vấn riêng lẻ như `find_available_rooms`.
    """
    duration = _time_to_minutes(end_time) - _time_to_minutes(start_time)
    requested_start = _time_to_minutes(start_time)
    day_start = BOOKING_MIN_HOUR * 60
    day_end = BOOKING_MAX_HOUR * 60
    if date == date_cls.today().isoformat():
        now = now or datetime.now()
        day_start = max(day_start, now.hour * 60 + now.minute)
    if day_start >= day_end:
        return {"rooms": [], "nearest_starts": []}

    conn = get_connection()
    try:
        rooms = conn.execute(
            "SELECT * FROM rooms WHERE status = 'active' AND capacity >= ? ORDER BY capacity, floor, name",
            (attendees,),
        ).fetchall()

        room_options = []
        start_candidates = set()
        for room in rooms:
            bookings = conn.execute(
                """SELECT start_time, end_time FROM bookings
                   WHERE room_id = ? AND date = ? AND status = 'active'
                   ORDER BY start_time""",
                (room["id"], date),
            ).fetchall()
            intervals = [
                (_time_to_minutes(b["start_time"]), _time_to_minutes(b["end_time"]))
                for b in bookings
            ]
            free = [
                window for window in _free_windows(intervals, day_start, day_end)
                if window[1] - window[0] >= duration
            ]
            if not free:
                continue

            closest = min(
                free,
                key=lambda window: min(abs(window[0] - requested_start), abs(window[1] - requested_start)),
            )
            room_options.append({
                "room": room_to_dict(room),
                "start_time": _minutes_to_time(closest[0]),
                "end_time": _minutes_to_time(closest[1]),
                "book_start": _minutes_to_time(closest[0]),
                "book_end": _minutes_to_time(closest[0] + duration),
                "distance": min(abs(closest[0] - requested_start), abs(closest[1] - requested_start)),
            })

            for window_start, window_end in free:
                slot_start = window_start
                while slot_start + duration <= window_end:
                    start_candidates.add(slot_start)
                    slot_start += 30

        room_options.sort(key=lambda item: item["distance"])
        for item in room_options:
            del item["distance"]
        nearest = sorted(start_candidates, key=lambda m: abs(m - requested_start))[:limit]
        nearest.sort()

        return {
            "rooms": room_options[:limit],
            "nearest_starts": [
                {"start_time": _minutes_to_time(m), "end_time": _minutes_to_time(m + duration)}
                for m in nearest
            ],
        }
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Tạo lịch đặt
# --------------------------------------------------------------------------- #

def _next_booking_id(conn):
    rows = conn.execute("SELECT id FROM bookings").fetchall()
    max_num = 0
    for row in rows:
        match = re.match(r"^BK(\d+)$", row["id"])
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"BK{max_num + 1:03d}"


def create_booking(payload, user_id=None, now=None):
    """Xác thực và lưu booking. Trả về (booking, dict lỗi).

    Việc kiểm tra trùng lịch và ghi dữ liệu nằm trong cùng một transaction
    ghi (BEGIN IMMEDIATE) nên hai yêu cầu đồng thời cho cùng khung giờ
    được xử lý tuần tự, chỉ một yêu cầu thành công.
    """
    cleaned, errors = validate_booking(payload, now=now)
    if errors:
        return None, errors

    conn = get_connection()
    try:
        conn.isolation_level = None  # tự điều khiển transaction
        conn.execute("BEGIN IMMEDIATE")

        room = get_room(cleaned["room_id"], conn=conn)
        if room is None:
            conn.execute("ROLLBACK")
            return None, {"room_id": "Phòng họp không tồn tại."}
        if room["status"] != "active":
            conn.execute("ROLLBACK")
            return None, {
                "room_id": f"{room['name']} đang ở trạng thái "
                           f"{room['status_label'].lower()}, không thể đặt."
            }
        if cleaned.get("attendees") and cleaned["attendees"] > room["capacity"]:
            conn.execute("ROLLBACK")
            return None, {
                "attendees": f"{room['name']} chỉ chứa tối đa {room['capacity']} người."
            }

        conflicts = _conflicting_bookings(
            conn, cleaned["room_id"], cleaned["date"],
            cleaned["start_time"], cleaned["end_time"],
        )
        if conflicts:
            busy = ", ".join(f"{c['start_time']}–{c['end_time']}" for c in conflicts)
            conn.execute("ROLLBACK")
            return None, {
                "conflict": f"{room['name']} đã có lịch trong khung giờ này ({busy}). "
                            "Vui lòng chọn khung giờ hoặc phòng khác."
            }

        booking_id = _next_booking_id(conn)
        conn.execute(
            """INSERT INTO bookings
                   (id, room_id, date, start_time, end_time, booked_by,
                    department, purpose, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                booking_id, cleaned["room_id"], cleaned["date"],
                cleaned["start_time"], cleaned["end_time"],
                cleaned["booked_by"], cleaned["department"], cleaned["purpose"],
                user_id,
            ),
        )
        _log_booking(conn, booking_id, "created", cleaned["booked_by"])
        conn.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        conn.execute("ROLLBACK")
        return None, {"conflict": f"Không thể lưu lịch đặt: {exc}"}
    except sqlite3.OperationalError as exc:
        return None, {"conflict": f"Hệ thống đang bận, vui lòng thử lại. ({exc})"}
    finally:
        conn.close()

    return get_booking(booking_id), {}


def get_booking(booking_id):
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT b.*, r.name AS room_name FROM bookings b
               JOIN rooms r ON r.id = b.room_id WHERE b.id = ?""",
            (booking_id,),
        ).fetchone()
        return booking_to_dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Lịch sử đặt phòng & thống kê
# --------------------------------------------------------------------------- #

def list_bookings(date=None, room_id=None, department=None, booked_by=None,
                  status=None, limit=None):
    sql = """
        SELECT b.*, r.name AS room_name FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        WHERE 1 = 1
    """
    params = []
    if status and status != "all":
        sql += " AND b.status = ?"
        params.append(status)
    if date:
        sql += " AND b.date = ?"
        params.append(date)
    if room_id and room_id != "all":
        sql += " AND b.room_id = ?"
        params.append(room_id)
    if department and department != "all":
        sql += " AND b.department = ?"
        params.append(department)
    if booked_by:
        sql += " AND b.booked_by LIKE ?"
        params.append(f"%{booked_by.strip()}%")
    sql += " ORDER BY b.date DESC, b.start_time DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))

    conn = get_connection()
    try:
        now = datetime.now()
        return [booking_to_dict(r, now) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def list_departments():
    conn = get_connection()
    try:
        return [
            r["department"]
            for r in conn.execute("SELECT DISTINCT department FROM bookings ORDER BY department")
        ]
    finally:
        conn.close()


def upcoming_bookings(limit=5):
    """Các lịch chưa kết thúc, sắp xếp theo thời gian bắt đầu gần nhất."""
    now = datetime.now()
    today = now.date().isoformat()
    current_time = now.strftime("%H:%M")
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT b.*, r.name AS room_name FROM bookings b
               JOIN rooms r ON r.id = b.room_id
               WHERE b.status = 'active'
                 AND (b.date > ? OR (b.date = ? AND b.end_time > ?))
               ORDER BY b.date, b.start_time
               LIMIT ?""",
            (today, today, current_time, limit),
        ).fetchall()
        return [booking_to_dict(r, now) for r in rows]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Lưới lịch phòng theo khung giờ (dùng ở trang chủ)
# --------------------------------------------------------------------------- #

GRID_START_HOUR = 7
GRID_END_HOUR = 20


def _time_to_minutes(hhmm):
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def grid_hour_marks():
    """Mốc giờ (kèm vị trí % đã tính sẵn) để vẽ hàng tiêu đề của lưới lịch."""
    window_start = GRID_START_HOUR * 60
    span = (GRID_END_HOUR - GRID_START_HOUR) * 60
    return [
        {
            "label": f"{hour:02d}:00",
            "pct": round((hour * 60 - window_start) / span * 100, 2),
        }
        for hour in range(GRID_START_HOUR, GRID_END_HOUR + 1)
    ]


def current_time_pct(now=None):
    """Vị trí % của thời điểm hiện tại trong khung giờ hiển thị, None nếu ngoài khung giờ."""
    now = now or datetime.now()
    minutes = now.hour * 60 + now.minute
    window_start = GRID_START_HOUR * 60
    window_end = GRID_END_HOUR * 60
    if minutes < window_start or minutes > window_end:
        return None
    return round((minutes - window_start) / (window_end - window_start) * 100, 2)


def today_room_schedule(day=None):
    """Lịch từng phòng trong một ngày, đã tính sẵn vị trí/độ rộng (%) của mỗi
    lịch đặt trong khung giờ GRID_START_HOUR–GRID_END_HOUR để vẽ trực tiếp
    bằng CSS (không cần JavaScript). Lịch nằm ngoài khung giờ hiển thị bị cắt
    bớt cho vừa khung; lịch đã huỷ không xuất hiện.
    """
    day = day or date_cls.today().isoformat()
    window_start = GRID_START_HOUR * 60
    window_end = GRID_END_HOUR * 60
    window_span = window_end - window_start

    conn = get_connection()
    try:
        rooms = conn.execute("SELECT * FROM rooms ORDER BY floor, name").fetchall()
        result = []
        for room in rooms:
            room_dict = room_to_dict(room)
            bookings = conn.execute(
                """SELECT * FROM bookings
                   WHERE room_id = ? AND date = ? AND status = 'active'
                   ORDER BY start_time""",
                (room["id"], day),
            ).fetchall()

            blocks = []
            for booking in bookings:
                start = max(_time_to_minutes(booking["start_time"]), window_start)
                end = min(_time_to_minutes(booking["end_time"]), window_end)
                if end <= start:
                    continue
                blocks.append({
                    "id": booking["id"],
                    "booked_by": booking["booked_by"],
                    "department": booking["department"],
                    "purpose": booking["purpose"],
                    "start_time": booking["start_time"],
                    "end_time": booking["end_time"],
                    "left_pct": round((start - window_start) / window_span * 100, 2),
                    "width_pct": round((end - start) / window_span * 100, 2),
                })

            room_dict["blocks"] = blocks
            result.append(room_dict)
        return result
    finally:
        conn.close()


def group_rooms_by_floor(rooms):
    """Gộp danh sách phòng thành từng nhóm theo tầng, giữ nguyên thứ tự.

    Giả định `rooms` đã được sắp theo floor (như today_room_schedule trả về),
    nên chỉ cần quét tuần tự và mở nhóm mới mỗi khi floor đổi, không cần sort
    lại hay dùng dict trung gian.
    """
    groups = []
    for room in rooms:
        if not groups or groups[-1]["floor"] != room["floor"]:
            groups.append({"floor": room["floor"], "rooms": []})
        groups[-1]["rooms"].append(room)
    return groups


# --------------------------------------------------------------------------- #
# Tài khoản nhân viên
# --------------------------------------------------------------------------- #

def user_to_dict(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "department": row["department"],
    }


def list_users():
    """Danh sách tài khoản, dùng để gợi ý ở trang đăng nhập."""
    conn = get_connection()
    try:
        return [user_to_dict(r) for r in
                conn.execute("SELECT * FROM users ORDER BY full_name")]
    finally:
        conn.close()


def get_user(user_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return user_to_dict(row) if row else None
    finally:
        conn.close()


def authenticate(username, password):
    """Trả về (user, dict lỗi). Không tiết lộ tài khoản có tồn tại hay không."""
    username = (username or "").strip().lower()
    if not username:
        return None, {"username": "Vui lòng nhập tên đăng nhập."}
    if not password:
        return None, {"password": "Vui lòng nhập mật khẩu."}

    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        return None, {"_": "Tên đăng nhập hoặc mật khẩu không đúng."}
    return user_to_dict(row), {}


def _next_user_id(conn):
    rows = conn.execute("SELECT id FROM users").fetchall()
    max_num = 0
    for row in rows:
        match = re.match(r"^U(\d+)$", row["id"])
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"U{max_num + 1:03d}"


def _username_taken(username, exclude_username=None):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT username FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return False
    return exclude_username is None or row["username"] != exclude_username


def validate_user(payload, exclude_username=None, require_password=True):
    """Kiểm tra dữ liệu tài khoản. Dùng chung cho tự đăng ký và admin tạo/sửa.

    exclude_username: tên đăng nhập hiện tại khi đang SỬA, để không tự báo
    trùng với chính mình. require_password=False khi admin chỉ sửa thông tin
    (đổi mật khẩu là một thao tác tách riêng, xem set_user_password).
    """
    errors, cleaned = {}, {}

    full_name = (payload.get("full_name") or "").strip()
    if not full_name:
        errors["full_name"] = "Vui lòng nhập họ tên."
    elif len(full_name) > 100:
        errors["full_name"] = "Họ tên không được vượt quá 100 ký tự."
    else:
        cleaned["full_name"] = full_name

    department = (payload.get("department") or "").strip()
    if not department:
        errors["department"] = "Vui lòng nhập phòng ban."
    elif len(department) > 100:
        errors["department"] = "Phòng ban không được vượt quá 100 ký tự."
    else:
        cleaned["department"] = department

    username = (payload.get("username") or "").strip().lower()
    if not username:
        errors["username"] = "Vui lòng nhập tên đăng nhập."
    elif not USERNAME_RE.match(username):
        errors["username"] = ("Tên đăng nhập phải bắt đầu bằng chữ cái, chỉ gồm chữ thường, "
                              "số, dấu chấm, gạch ngang hoặc gạch dưới (3–30 ký tự).")
    elif _username_taken(username, exclude_username):
        errors["username"] = f"Tên đăng nhập {username} đã được sử dụng."
    else:
        cleaned["username"] = username

    if require_password:
        password = payload.get("password") or ""
        confirm = payload.get("confirm_password") or ""
        if not password:
            errors["password"] = "Vui lòng nhập mật khẩu."
        elif len(password) < MIN_PASSWORD_LENGTH:
            errors["password"] = f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự."
        elif password != confirm:
            errors["confirm_password"] = "Mật khẩu nhập lại không khớp."
        else:
            cleaned["password"] = password

    return cleaned, errors


def create_user(payload):
    """Tạo tài khoản mới. Dùng chung cho trang tự đăng ký lẫn admin tạo hộ."""
    cleaned, errors = validate_user(payload, require_password=True)
    if errors:
        return None, errors

    conn = get_connection()
    try:
        user_id = _next_user_id(conn)
        conn.execute(
            """INSERT INTO users (id, username, full_name, department, password_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, cleaned["username"], cleaned["full_name"], cleaned["department"],
             generate_password_hash(cleaned["password"]),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return None, {"username": f"Tên đăng nhập {cleaned['username']} đã được sử dụng."}
    finally:
        conn.close()
    return get_user(user_id), {}


def update_user(user_id, payload):
    """Sửa họ tên / phòng ban / tên đăng nhập. Đổi mật khẩu là thao tác riêng."""
    current = get_user(user_id)
    if current is None:
        return None, {"_": "Tài khoản không tồn tại."}

    cleaned, errors = validate_user(
        payload, exclude_username=current["username"], require_password=False)
    if errors:
        return None, errors

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET username = ?, full_name = ?, department = ? WHERE id = ?",
            (cleaned["username"], cleaned["full_name"], cleaned["department"], user_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return None, {"username": f"Tên đăng nhập {cleaned['username']} đã được sử dụng."}
    finally:
        conn.close()
    return get_user(user_id), {}


def set_user_password(user_id, password, confirm_password):
    """Admin đặt lại mật khẩu cho một tài khoản, không cần biết mật khẩu cũ."""
    if get_user(user_id) is None:
        return {"_": "Tài khoản không tồn tại."}

    errors = {}
    if not password:
        errors["password"] = "Vui lòng nhập mật khẩu mới."
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự."
    elif password != confirm_password:
        errors["confirm_password"] = "Mật khẩu nhập lại không khớp."
    if errors:
        return errors

    conn = get_connection()
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (generate_password_hash(password), user_id))
        conn.commit()
    finally:
        conn.close()
    return {}


def count_user_bookings(user_id):
    """Số lịch đặt (mọi trạng thái) đang gắn với một tài khoản."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE user_id = ?", (user_id,)).fetchone()[0]
    finally:
        conn.close()


def delete_user(user_id):
    """Chỉ xoá được tài khoản chưa từng đứng tên lịch đặt nào."""
    user = get_user(user_id)
    if user is None:
        return {"_": "Tài khoản không tồn tại."}

    total = count_user_bookings(user_id)
    if total:
        return {"_": f"Tài khoản {user['full_name']} đang gắn với {total} lịch đặt nên không "
                     "thể xoá. Hãy giữ lại tài khoản hoặc đặt lại mật khẩu thay vì xoá."}

    conn = get_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return {}


def list_users_with_stats():
    """Danh sách tài khoản kèm số lịch đặt, phục vụ trang quản trị."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id) AS booking_count
               FROM users u ORDER BY u.full_name"""
        ).fetchall()
        result = []
        for row in rows:
            user = user_to_dict(row)
            user["booking_count"] = row["booking_count"]
            user["created_at"] = row["created_at"]
            result.append(user)
        return result
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Nhật ký thay đổi
# --------------------------------------------------------------------------- #

def _actor_label(user, is_admin):
    """Tên hiển thị của người thực hiện thao tác trong nhật ký."""
    if is_admin:
        return f"Quản trị viên ({user['full_name']})" if user else "Quản trị viên"
    return user["full_name"] if user else "Không rõ"


def _room_name(conn, room_id):
    row = conn.execute("SELECT name FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return row["name"] if row else room_id


def _log_booking(conn, booking_id, action, actor, changes=None):
    """Ghi một dòng nhật ký. Gọi bên trong transaction của thao tác gốc."""
    conn.execute(
        """INSERT INTO booking_logs (booking_id, action, actor, changes, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (booking_id, action, actor,
         json.dumps(changes or [], ensure_ascii=False),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def _diff_booking(conn, old_row, cleaned):
    """So sánh bản ghi cũ với dữ liệu mới, trả về danh sách trường đã đổi.

    Riêng phòng họp thì lưu tên phòng tại thời điểm đó, để nhật ký vẫn đọc được
    kể cả sau này phòng bị đổi tên.
    """
    changes = []
    for field, label in TRACKED_FIELDS.items():
        old_value = old_row[field]
        new_value = cleaned[field]
        if str(old_value) == str(new_value):
            continue
        if field == "room_id":
            old_value = _room_name(conn, old_value)
            new_value = _room_name(conn, new_value)
        changes.append({
            "field": field, "label": label,
            "old": str(old_value), "new": str(new_value),
        })
    return changes


def _log_to_dict(row):
    try:
        changes = json.loads(row["changes"] or "[]")
    except ValueError:
        changes = []
    keys = row.keys()
    return {
        "id": row["id"],
        "booking_id": row["booking_id"],
        "action": row["action"],
        "action_label": LOG_ACTION_LABELS.get(row["action"], row["action"]),
        "actor": row["actor"],
        "changes": changes,
        "created_at": row["created_at"],
        "room_name": row["room_name"] if "room_name" in keys else None,
        "booking_date": row["booking_date"] if "booking_date" in keys else None,
    }


def list_booking_logs(booking_id):
    """Nhật ký của một lịch đặt, mới nhất trước."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM booking_logs WHERE booking_id = ? ORDER BY id DESC",
            (booking_id,),
        ).fetchall()
    finally:
        conn.close()
    return [_log_to_dict(row) for row in rows]


def list_activity_logs(booking_id=None, action=None, actor=None, limit=200):
    """Dòng hoạt động của toàn hệ thống, dùng cho trang quản trị."""
    sql = """
        SELECT l.*, b.date AS booking_date, r.name AS room_name
        FROM booking_logs l
        LEFT JOIN bookings b ON b.id = l.booking_id
        LEFT JOIN rooms r ON r.id = b.room_id
        WHERE 1 = 1
    """
    params = []
    if booking_id:
        sql += " AND l.booking_id = ?"
        params.append(booking_id)
    if action and action != "all":
        sql += " AND l.action = ?"
        params.append(action)
    if actor:
        sql += " AND l.actor LIKE ?"
        params.append(f"%{actor.strip()}%")
    sql += " ORDER BY l.id DESC LIMIT ?"
    params.append(int(limit))

    conn = get_connection()
    try:
        return [_log_to_dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def activity_stats():
    """Đếm số lần theo từng loại hành động, hiển thị ở bảng quản trị."""
    conn = get_connection()
    try:
        counts = dict(conn.execute(
            "SELECT action, COUNT(*) FROM booking_logs GROUP BY action").fetchall())
    finally:
        conn.close()
    return {
        "total": sum(counts.values()),
        "created": counts.get("created", 0),
        "updated": counts.get("updated", 0),
        "cancelled": counts.get("cancelled", 0),
        "imported": counts.get("imported", 0),
    }


def count_booking_changes(booking_id):
    """Số lần lịch đặt bị sửa, dùng để hiển thị nhãn ở danh sách."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM booking_logs WHERE booking_id = ? AND action = 'updated'",
            (booking_id,),
        ).fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Sửa và huỷ lịch đặt
# --------------------------------------------------------------------------- #

def authorize_booking(row, user, is_admin):
    """Kiểm tra quyền sửa/huỷ một lịch đặt. Trả về dict lỗi rỗng nếu được phép.

    Quản trị viên thao tác được với mọi lịch, không cần đăng nhập tài khoản
    nhân viên. Nhân viên phải đăng nhập và chỉ thao tác được trên lịch do
    chính tài khoản mình tạo (so khớp bằng user_id, không còn dựa vào tên gõ tay).

    Hàm này không mở transaction ghi nên dùng được cả để kiểm tra khi hiển thị
    trang (GET) lẫn ngay trước khi ghi (POST).
    """
    if row["status"] == "cancelled":
        return {"_": f"Lịch {row['id']} đã được huỷ trước đó."}

    if booking_state(row["date"], row["start_time"], row["end_time"]) == "finished":
        return {"_": "Cuộc họp đã kết thúc nên không thể sửa hoặc huỷ."}

    if is_admin:
        return {}

    if user is None:
        return {"_": "Vui lòng đăng nhập để sửa hoặc huỷ lịch đặt của bạn."}

    owner_id = row["user_id"] if "user_id" in row.keys() else None
    if owner_id is None:
        return {"_": "Lịch này được tạo trước khi có tài khoản đăng nhập nên chưa gắn với "
                     "nhân viên nào. Chỉ quản trị viên mới có thể sửa hoặc huỷ lịch này."}
    if owner_id != user["id"]:
        return {"_": "Bạn không phải người đặt lịch này nên không thể sửa hoặc huỷ. "
                     "Nếu cần hỗ trợ, hãy liên hệ quản trị viên."}
    return {}


def cancel_booking(booking_id, user=None, is_admin=False):
    """Huỷ mềm một lịch đặt: giữ bản ghi, đánh dấu cancelled và trả lại khung giờ."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if row is None:
            return None, {"_": f"Không tìm thấy booking {booking_id}."}

        errors = authorize_booking(row, user, is_admin)
        if errors:
            return None, errors

        conn.execute(
            "UPDATE bookings SET status = 'cancelled', cancelled_at = datetime('now') WHERE id = ?",
            (booking_id,),
        )
        _log_booking(conn, booking_id, "cancelled", _actor_label(user, is_admin))
        conn.commit()
    finally:
        conn.close()
    return get_booking(booking_id), {}


def update_booking(booking_id, payload, user=None, is_admin=False, now=None):
    """Sửa một lịch đặt đã có, kiểm tra lại trùng lịch trước khi lưu.

    Lịch đang sửa được loại khỏi phép kiểm tra trùng, nếu không nó sẽ tự
    xung đột với chính mình khi người dùng chỉ đổi mục đích hay phòng ban.
    Không áp quy tắc "không đặt được ngày/giờ đã qua" (check_past=False) vì
    lịch đang diễn ra vẫn được phép sửa dù giờ bắt đầu đã ở quá khứ; khung
    giờ hành chính và giới hạn thời lượng thì vẫn kiểm tra như bình thường.
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    finally:
        conn.close()

    if row is None:
        return None, {"_": f"Không tìm thấy booking {booking_id}."}

    errors = authorize_booking(row, user, is_admin)
    if errors:
        return None, errors

    cleaned, errors = validate_booking(payload, check_past=False, now=now)
    if errors:
        return None, errors

    conn = get_connection()
    try:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")

        room = get_room(cleaned["room_id"], conn=conn)
        if room is None:
            conn.execute("ROLLBACK")
            return None, {"room_id": "Phòng họp không tồn tại."}

        # Cho phép giữ nguyên phòng cũ dù phòng đó vừa chuyển sang bảo trì,
        # nhưng không cho chuyển lịch sang một phòng đang bảo trì.
        if room["status"] != "active" and cleaned["room_id"] != row["room_id"]:
            conn.execute("ROLLBACK")
            return None, {
                "room_id": f"{room['name']} đang ở trạng thái "
                           f"{room['status_label'].lower()}, không thể chuyển lịch sang phòng này."
            }

        if cleaned.get("attendees") and cleaned["attendees"] > room["capacity"]:
            conn.execute("ROLLBACK")
            return None, {
                "attendees": f"{room['name']} chỉ chứa tối đa {room['capacity']} người."
            }

        conflicts = _conflicting_bookings(
            conn, cleaned["room_id"], cleaned["date"],
            cleaned["start_time"], cleaned["end_time"], exclude_id=booking_id,
        )
        if conflicts:
            busy = ", ".join(f"{c['start_time']}–{c['end_time']}" for c in conflicts)
            conn.execute("ROLLBACK")
            return None, {
                "conflict": f"{room['name']} đã có lịch khác trong khung giờ này ({busy}). "
                            "Vui lòng chọn khung giờ hoặc phòng khác."
            }

        changes = _diff_booking(conn, row, cleaned)
        conn.execute(
            """UPDATE bookings
                  SET room_id = ?, date = ?, start_time = ?, end_time = ?,
                      booked_by = ?, department = ?, purpose = ?
                WHERE id = ?""",
            (cleaned["room_id"], cleaned["date"], cleaned["start_time"], cleaned["end_time"],
             cleaned["booked_by"], cleaned["department"], cleaned["purpose"], booking_id),
        )
        # Bấm lưu mà không đổi gì thì không ghi nhật ký, tránh làm nhiễu.
        if changes:
            _log_booking(conn, booking_id, "updated",
                         _actor_label(user, is_admin), changes)
        conn.execute("COMMIT")
    except sqlite3.OperationalError as exc:
        return None, {"conflict": f"Hệ thống đang bận, vui lòng thử lại. ({exc})"}
    finally:
        conn.close()

    return get_booking(booking_id), {}


# --------------------------------------------------------------------------- #
# Quản trị: phòng họp
# --------------------------------------------------------------------------- #

def _parse_equipment(raw):
    """Nhận chuỗi nhiều dòng hoặc ngăn cách bằng dấu phẩy, trả về danh sách đã làm sạch."""
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        text = (raw or "").replace(",", "\n")
        items = text.split("\n")
    seen, cleaned = set(), []
    for item in items:
        item = str(item).strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            cleaned.append(item)
    return cleaned


def validate_room(payload, existing_id=None):
    """Kiểm tra dữ liệu phòng. existing_id khác None nghĩa là đang cập nhật."""
    errors, cleaned = {}, {}

    if existing_id is None:
        room_id = (payload.get("id") or "").strip().upper()
        if not room_id:
            errors["id"] = "Vui lòng nhập mã phòng."
        elif not ROOM_ID_RE.match(room_id):
            errors["id"] = "Mã phòng chỉ gồm chữ, số, gạch ngang hoặc gạch dưới (2–20 ký tự)."
        elif get_room(room_id) is not None:
            errors["id"] = f"Mã phòng {room_id} đã tồn tại."
        else:
            cleaned["id"] = room_id
    else:
        cleaned["id"] = existing_id

    name = (payload.get("name") or "").strip()
    if not name:
        errors["name"] = "Vui lòng nhập tên phòng."
    elif len(name) > 100:
        errors["name"] = "Tên phòng không được vượt quá 100 ký tự."
    else:
        cleaned["name"] = name

    for field, label, low, high in (("floor", "Tầng", -5, 200), ("capacity", "Sức chứa", 1, 500)):
        raw = payload.get(field)
        raw = "" if raw is None else str(raw).strip()
        if raw == "":
            errors[field] = f"Vui lòng nhập {label.lower()}."
            continue
        try:
            value = int(raw)
        except ValueError:
            errors[field] = f"{label} phải là một số nguyên."
            continue
        if value < low or value > high:
            errors[field] = f"{label} phải nằm trong khoảng {low}–{high}."
        else:
            cleaned[field] = value

    status = (payload.get("status") or "active").strip()
    if status not in ROOM_STATUSES:
        errors["status"] = "Trạng thái không hợp lệ."
    else:
        cleaned["status"] = status

    image = (payload.get("image") or "").strip()
    if len(image) > 255:
        errors["image"] = "Đường dẫn ảnh quá dài."
    else:
        cleaned["image"] = image or None

    cleaned["equipment"] = _parse_equipment(payload.get("equipment"))
    return cleaned, errors


def create_room(payload):
    cleaned, errors = validate_room(payload)
    if errors:
        return None, errors

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO rooms (id, name, floor, capacity, equipment, image, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cleaned["id"], cleaned["name"], cleaned["floor"], cleaned["capacity"],
             json.dumps(cleaned["equipment"], ensure_ascii=False),
             cleaned["image"], cleaned["status"]),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return None, {"id": f"Mã phòng {cleaned['id']} đã tồn tại."}
    finally:
        conn.close()
    return get_room(cleaned["id"]), {}


def update_room(room_id, payload):
    if get_room(room_id) is None:
        return None, {"_": "Phòng không tồn tại."}

    cleaned, errors = validate_room(payload, existing_id=room_id)
    if errors:
        return None, errors

    conn = get_connection()
    try:
        conn.execute(
            """UPDATE rooms SET name = ?, floor = ?, capacity = ?, equipment = ?,
                                image = ?, status = ?
               WHERE id = ?""",
            (cleaned["name"], cleaned["floor"], cleaned["capacity"],
             json.dumps(cleaned["equipment"], ensure_ascii=False),
             cleaned["image"], cleaned["status"], room_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_room(room_id), {}


def set_room_status(room_id, status):
    if status not in ROOM_STATUSES:
        return None, {"_": "Trạng thái không hợp lệ."}
    if get_room(room_id) is None:
        return None, {"_": "Phòng không tồn tại."}

    conn = get_connection()
    try:
        conn.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        conn.commit()
    finally:
        conn.close()
    return get_room(room_id), {}


def count_room_bookings(room_id, only_upcoming=False):
    """Số lịch đặt còn hiệu lực của một phòng."""
    sql = "SELECT COUNT(*) FROM bookings WHERE room_id = ? AND status = 'active'"
    params = [room_id]
    if only_upcoming:
        sql += " AND date >= ?"
        params.append(date_cls.today().isoformat())

    conn = get_connection()
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def delete_room(room_id):
    """Chỉ xoá được phòng chưa từng có lịch đặt, để không phá vỡ khoá ngoại."""
    room = get_room(room_id)
    if room is None:
        return {"_": "Phòng không tồn tại."}

    conn = get_connection()
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE room_id = ?", (room_id,)).fetchone()[0]
        if total:
            return {"_": f"{room['name']} đã có {total} lịch đặt trong lịch sử nên không thể xoá. "
                         "Hãy chuyển phòng sang trạng thái bảo trì để ngừng cho đặt."}
        conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        conn.commit()
    finally:
        conn.close()
    return {}


def rooms_with_stats():
    """Danh sách phòng kèm số lịch đặt, phục vụ bảng quản trị."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT r.*,
                      (SELECT COUNT(*) FROM bookings b
                        WHERE b.room_id = r.id AND b.status = 'active') AS booking_count,
                      (SELECT COUNT(*) FROM bookings b
                        WHERE b.room_id = r.id AND b.status = 'active'
                          AND b.date >= ?) AS upcoming_count
               FROM rooms r ORDER BY r.floor, r.name""",
            (date_cls.today().isoformat(),),
        ).fetchall()
        result = []
        for row in rows:
            room = room_to_dict(row)
            room["booking_count"] = row["booking_count"]
            room["upcoming_count"] = row["upcoming_count"]
            result.append(room)
        return result
    finally:
        conn.close()


def dashboard_stats():
    today = date_cls.today().isoformat()
    conn = get_connection()
    try:
        one = lambda sql, p=(): conn.execute(sql, p).fetchone()[0]  # noqa: E731
        return {
            "total_rooms": one("SELECT COUNT(*) FROM rooms"),
            "active_rooms": one("SELECT COUNT(*) FROM rooms WHERE status = 'active'"),
            "maintenance_rooms": one("SELECT COUNT(*) FROM rooms WHERE status = 'maintenance'"),
            "total_bookings": one("SELECT COUNT(*) FROM bookings WHERE status = 'active'"),
            "cancelled_bookings": one("SELECT COUNT(*) FROM bookings WHERE status = 'cancelled'"),
            "today_bookings": one(
                "SELECT COUNT(*) FROM bookings WHERE date = ? AND status = 'active'", (today,)),
            "upcoming_count": one(
                "SELECT COUNT(*) FROM bookings WHERE status = 'active' AND date >= ?", (today,)),
            "today": today,
        }
    finally:
        conn.close()
