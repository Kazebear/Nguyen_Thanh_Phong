"""Office Booking – hệ thống quản lý và đặt phòng họp nội bộ."""

import hmac
import os
import secrets
from datetime import date as date_cls
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for,
)

import database
import services
from database import BASE_DIR, init_db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "office-booking-dev-secret")
app.config["JSON_AS_ASCII"] = False

# Mật khẩu chung cho trang quản trị. Đặt biến môi trường ADMIN_PASSWORD khi
# triển khai thật; giá trị mặc định chỉ dùng cho môi trường phát triển.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


@app.context_processor
def inject_globals():
    """Biến dùng chung cho mọi template."""
    return {
        "today": date_cls.today().isoformat(),
        "app_name": "Office Booking",
        "is_admin": session.get("is_admin", False),
        "current_user": session.get("user"),
        "csrf_token": _csrf_token,
        "booking_min_time": f"{services.BOOKING_MIN_HOUR:02d}:00",
        "booking_max_time": f"{services.BOOKING_MAX_HOUR:02d}:00",
    }


# --------------------------------------------------------------------------- #
# Đăng nhập nhân viên
# --------------------------------------------------------------------------- #

def _safe_next(target, fallback_endpoint="index"):
    """Chỉ cho phép quay lại đường dẫn nội bộ, tránh chuyển hướng ra ngoài."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for(fallback_endpoint)


@app.route("/login", methods=["GET", "POST"])
def login():
    target = request.args.get("next", "")

    if session.get("user"):
        return redirect(_safe_next(target))

    errors = {}
    username = ""
    if request.method == "POST":
        _check_csrf()
        username = request.form.get("username", "")
        user, errors = services.authenticate(username, request.form.get("password", ""))
        if not errors:
            session["user"] = user
            flash(f"Xin chào {user['full_name']}! Bạn đã đăng nhập.", "success")
            return redirect(_safe_next(request.form.get("next", "")))

    return render_template(
        "login.html", errors=errors, username=username, next=target,
        users=services.list_users(),
        default_password=database.DEFAULT_USER_PASSWORD,
    ), (400 if errors else 200)


@app.route("/logout", methods=["POST"])
def logout():
    _check_csrf()
    session.pop("user", None)
    flash("Bạn đã đăng xuất.", "success")
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    target = request.args.get("next", "")

    if session.get("user"):
        return redirect(_safe_next(target))

    form = {"full_name": "", "department": "", "username": ""}
    errors = {}

    if request.method == "POST":
        _check_csrf()
        form = {key: request.form.get(key, "") for key in form}
        payload = dict(form, password=request.form.get("password", ""),
                       confirm_password=request.form.get("confirm_password", ""))
        user, errors = services.create_user(payload)
        if not errors:
            # Đăng ký xong tự động đăng nhập luôn, không bắt phải đăng nhập lại.
            session["user"] = user
            flash(f"Đăng ký thành công! Xin chào {user['full_name']}.", "success")
            return redirect(_safe_next(request.form.get("next", "")))

    return render_template(
        "register.html", form=form, errors=errors, next=target,
    ), (400 if errors else 200)


# --------------------------------------------------------------------------- #
# Xác thực quản trị
# --------------------------------------------------------------------------- #

def _csrf_token():
    """Token chống giả mạo yêu cầu, sinh một lần cho mỗi session."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def _check_csrf():
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Phiên làm việc đã hết hạn, vui lòng thử lại.")


def admin_required(view):
    """Chặn truy cập trang quản trị khi chưa đăng nhập."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Vui lòng đăng nhập để vào trang quản trị.", "error")
            return redirect(url_for("admin_login", next=request.path))
        if request.method == "POST":
            _check_csrf()
        return view(*args, **kwargs)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            session["is_admin"] = True
            session.permanent = False
            flash("Đăng nhập quản trị thành công.", "success")
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/admin") else url_for("admin_dashboard"))
        error = "Mật khẩu không đúng."

    return render_template("admin/login.html", error=error,
                           using_default=ADMIN_PASSWORD == "admin123")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    _check_csrf()
    session.pop("is_admin", None)
    flash("Đã đăng xuất khỏi trang quản trị.", "success")
    return redirect(url_for("index"))


@app.template_filter("has_image")
def has_image(path):
    """Kiểm tra ảnh phòng có tồn tại trong static/ hay không."""
    if not path:
        return False
    return os.path.isfile(os.path.join(BASE_DIR, "static", path))


# --------------------------------------------------------------------------- #
# Trang chủ
# --------------------------------------------------------------------------- #

@app.route("/")
def index():
    # Lưới lịch phòng xem được theo ngày bất kỳ qua ?date=, phần còn lại của
    # trang chủ (thống kê, lịch sắp tới) luôn bám theo ngày thực tế hôm nay.
    raw_date = request.args.get("date", "").strip()
    try:
        selected_day = datetime.strptime(raw_date, "%Y-%m-%d").date() if raw_date else date_cls.today()
    except ValueError:
        selected_day = date_cls.today()
    is_today = selected_day == date_cls.today()

    schedule = services.today_room_schedule(day=selected_day.isoformat())
    # Quá 10 phòng thì gộp theo tầng, mỗi tầng thu gọn/mở rộng được, để lưới
    # lịch không kéo quá dài; từ 10 phòng trở xuống vẫn hiển thị phẳng như cũ.
    floor_groups = services.group_rooms_by_floor(schedule) if len(schedule) > 10 else None

    return render_template(
        "index.html",
        stats=services.dashboard_stats(),
        quick=services.quick_slot(),
        upcoming=services.upcoming_bookings(limit=5),
        room_schedule=schedule,
        floor_groups=floor_groups,
        hour_marks=services.grid_hour_marks(),
        now_pct=services.current_time_pct() if is_today else None,
        selected_day=selected_day.isoformat(),
        is_today=is_today,
        prev_day=(selected_day - timedelta(days=1)).isoformat(),
        next_day=(selected_day + timedelta(days=1)).isoformat(),
    )


@app.route("/about")
def about():
    return render_template("about.html")


# --------------------------------------------------------------------------- #
# Danh sách phòng họp + kiểm tra phòng trống
# --------------------------------------------------------------------------- #

@app.route("/rooms")
def rooms():
    filters = {
        "floor": request.args.get("floor", ""),
        "min_capacity": request.args.get("min_capacity", ""),
        "status": request.args.get("status", ""),
    }
    room_list = services.list_rooms(
        floor=filters["floor"] or None,
        min_capacity=filters["min_capacity"] or None,
        status=filters["status"] or None,
    )

    # Kiểm tra phòng trống phía server (hoạt động cả khi trình duyệt tắt JavaScript).
    search = {
        "date": request.args.get("date", ""),
        "start_time": request.args.get("start_time", ""),
        "end_time": request.args.get("end_time", ""),
        "attendees": request.args.get("attendees", ""),
    }
    availability = None
    errors = {}
    if request.args.get("check") == "1":
        cleaned, errors = services.validate_slot(search)
        if not errors:
            found = services.find_available_rooms(
                cleaned["date"], cleaned["start_time"],
                cleaned["end_time"], cleaned["attendees"],
            )
            availability = {
                "criteria": cleaned,
                "rooms": found,
                "suggestions": None if found else services.suggest_alternatives(
                    cleaned["date"], cleaned["start_time"],
                    cleaned["end_time"], cleaned["attendees"],
                ),
            }

    return render_template(
        "rooms.html",
        rooms=room_list,
        floors=services.list_floors(),
        filters=filters,
        search=search,
        availability=availability,
        errors=errors,
    )


@app.route("/api/rooms")
def api_rooms():
    return jsonify(services.list_rooms(
        floor=request.args.get("floor") or None,
        min_capacity=request.args.get("min_capacity") or None,
        status=request.args.get("status") or None,
    ))


@app.route("/api/availability")
def api_availability():
    cleaned, errors = services.validate_slot({
        "date": request.args.get("date"),
        "start_time": request.args.get("start_time"),
        "end_time": request.args.get("end_time"),
        "attendees": request.args.get("attendees"),
    })
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    available = services.find_available_rooms(
        cleaned["date"], cleaned["start_time"], cleaned["end_time"], cleaned["attendees"]
    )
    return jsonify({
        "ok": True,
        "criteria": cleaned,
        "count": len(available),
        "rooms": available,
        "suggestions": None if available else services.suggest_alternatives(
            cleaned["date"], cleaned["start_time"], cleaned["end_time"], cleaned["attendees"]
        ),
        "message": (
            "Không có phòng nào phù hợp với yêu cầu của bạn."
            if not available else f"Tìm thấy {len(available)} phòng phù hợp."
        ),
    })


@app.route("/api/rooms/<room_id>/schedule")
def api_room_schedule(room_id):
    room = services.get_room(room_id)
    if room is None:
        return jsonify({"ok": False, "errors": {"room_id": "Phòng không tồn tại."}}), 404
    date = (request.args.get("date") or "").strip()
    if not date:
        return jsonify({"ok": False, "errors": {"date": "Thiếu tham số ngày."}}), 400
    return jsonify({"ok": True, "room": room, "bookings": services.room_schedule(room_id, date)})


# --------------------------------------------------------------------------- #
# Tạo lịch đặt
# --------------------------------------------------------------------------- #

@app.route("/book", methods=["GET", "POST"])
def book():
    user = session.get("user")
    is_admin = session.get("is_admin", False)

    if request.method == "POST":
        payload = {key: request.form.get(key, "") for key in (
            "room_id", "date", "start_time", "end_time",
            "booked_by", "department", "purpose", "attendees",
        )}

        # Ai cũng điền được biểu mẫu, nhưng phải đăng nhập mới hoàn tất được.
        # Quản trị viên là ngoại lệ: đã đăng nhập /admin thì đặt được luôn,
        # không cần đăng nhập thêm tài khoản nhân viên.
        # Giữ nguyên dữ liệu đã nhập và gắn vào link đăng nhập để quay lại không mất công gõ.
        if user is None and not is_admin:
            return render_template(
                "book.html",
                form=payload,
                errors={"auth": "Bạn cần đăng nhập để hoàn tất đặt phòng. "
                                "Thông tin vừa nhập sẽ được giữ nguyên sau khi đăng nhập."},
                login_url=url_for("login", next=url_for(
                    "book", **{k: v for k, v in payload.items() if v})),
                room=services.get_room(payload.get("room_id", "")),
                rooms=services.list_rooms(status="active"),
            ), 401

        if user is not None:
            # Người đã đăng nhập luôn đặt dưới danh tính của chính mình.
            payload["booked_by"] = user["full_name"]
            payload["department"] = user["department"]
            owner_id = user["id"]
        else:
            # Quản trị viên chưa đăng nhập tài khoản nhân viên: tự gõ người đặt,
            # booking sẽ không gắn với tài khoản nào (chỉ quản trị viên quản lý được).
            owner_id = None
        if not payload["attendees"]:
            payload.pop("attendees")

        booking, errors = services.create_booking(payload, user_id=owner_id)
        if errors:
            return render_template(
                "book.html",
                form=payload,
                errors=errors,
                room=services.get_room(payload.get("room_id", "")),
                rooms=services.list_rooms(status="active"),
            ), 400

        flash(
            f"Đặt phòng thành công! Mã booking {booking['id']} – {booking['room_name']}, "
            f"ngày {booking['date']} lúc {booking['start_time']}–{booking['end_time']}.",
            "success",
        )
        return redirect(url_for("history", highlight=booking["id"]))

    form = {
        "room_id": request.args.get("room_id", ""),
        "date": request.args.get("date", ""),
        "start_time": request.args.get("start_time", ""),
        "end_time": request.args.get("end_time", ""),
        "attendees": request.args.get("attendees", ""),
        "booked_by": request.args.get("booked_by", ""),
        "department": request.args.get("department", ""),
        "purpose": request.args.get("purpose", ""),
    }
    if user:
        form["booked_by"] = user["full_name"]
        form["department"] = user["department"]
    return render_template(
        "book.html",
        form=form,
        errors={},
        room=services.get_room(form["room_id"]) if form["room_id"] else None,
        rooms=services.list_rooms(status="active"),
    )


@app.route("/bookings/<booking_id>")
def booking_detail(booking_id):
    booking = services.get_booking(booking_id)
    if booking is None:
        abort(404)
    # Nhật ký thay đổi chỉ dành cho quản trị viên, xem tại /admin/logs.
    return render_template(
        "booking_detail.html",
        booking=booking,
        room=services.get_room(booking["room_id"]),
        change_count=services.count_booking_changes(booking_id),
    )


@app.route("/bookings/<booking_id>/edit", methods=["GET", "POST"])
def booking_edit(booking_id):
    booking = services.get_booking(booking_id)
    if booking is None:
        abort(404)

    user = session.get("user")
    is_admin = session.get("is_admin", False)

    # Sửa lịch là thao tác trên tài sản có chủ, không có khái niệm "điền tự do
    # rồi đăng nhập sau" như lúc tạo mới — phải xác định danh tính trước.
    if user is None and not is_admin:
        flash("Vui lòng đăng nhập để sửa lịch đặt của bạn.", "error")
        return redirect(url_for("login", next=request.path))

    form = {
        "room_id": booking["room_id"],
        "date": booking["date"],
        "start_time": booking["start_time"],
        "end_time": booking["end_time"],
        "booked_by": booking["booked_by"],
        "department": booking["department"],
        "purpose": booking["purpose"],
    }
    # Kiểm tra quyền ngay từ GET để trang hiển thị đúng trạng thái ngay lần tải đầu.
    errors = services.authorize_booking(booking, user, is_admin)

    if request.method == "POST" and not errors:
        _check_csrf()
        form = {key: request.form.get(key, "") for key in form}
        updated, errors = services.update_booking(
            booking_id, form, user=user, is_admin=is_admin
        )
        if not errors:
            flash(f"Đã cập nhật lịch {updated['id']} – {updated['room_name']}, "
                  f"ngày {updated['date']} lúc {updated['start_time']}–{updated['end_time']}.",
                  "success")
            return redirect(url_for("history", highlight=updated["id"]))

    return render_template(
        "booking_edit.html", booking=booking, form=form, errors=errors,
        rooms=services.list_rooms(status="active"),
        current_room=services.get_room(form["room_id"] or booking["room_id"]),
    ), (400 if errors else 200)


@app.route("/bookings/<booking_id>/cancel", methods=["GET", "POST"])
def booking_cancel(booking_id):
    booking = services.get_booking(booking_id)
    if booking is None:
        abort(404)

    user = session.get("user")
    is_admin = session.get("is_admin", False)

    if user is None and not is_admin:
        flash("Vui lòng đăng nhập để huỷ lịch đặt của bạn.", "error")
        return redirect(url_for("login", next=request.path))

    errors = services.authorize_booking(booking, user, is_admin)

    if request.method == "POST" and not errors:
        _check_csrf()
        cancelled, errors = services.cancel_booking(booking_id, user=user, is_admin=is_admin)
        if not errors:
            flash(f"Đã huỷ lịch {cancelled['id']} – {cancelled['room_name']}, "
                  f"ngày {cancelled['date']} {cancelled['start_time']}–{cancelled['end_time']}. "
                  "Khung giờ này đã được trả lại cho người khác đặt.", "success")
            return redirect(url_for("history"))

    return render_template("booking_cancel.html", booking=booking,
                           errors=errors), (400 if errors else 200)


@app.route("/api/bookings", methods=["GET", "POST"])
def api_bookings():
    if request.method == "GET":
        return jsonify(services.list_bookings(
            date=request.args.get("date") or None,
            room_id=request.args.get("room_id") or None,
            department=request.args.get("department") or None,
            booked_by=request.args.get("booked_by") or None,
        ))

    payload = request.get_json(silent=True) or request.form.to_dict()
    booking, errors = services.create_booking(payload)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 409 if "conflict" in errors else 400
    return jsonify({"ok": True, "booking": booking}), 201


# --------------------------------------------------------------------------- #
# Lịch sử đặt phòng
# --------------------------------------------------------------------------- #

@app.route("/history")
def history():
    filters = {
        "date": request.args.get("date", ""),
        "room_id": request.args.get("room_id", ""),
        "department": request.args.get("department", ""),
        "booked_by": request.args.get("booked_by", ""),
    }
    return render_template(
        "history.html",
        bookings=services.list_bookings(
            date=filters["date"] or None,
            room_id=filters["room_id"] or None,
            department=filters["department"] or None,
            booked_by=filters["booked_by"] or None,
        ),
        rooms=services.list_rooms(),
        departments=services.list_departments(),
        filters=filters,
        highlight=request.args.get("highlight", ""),
    )


# --------------------------------------------------------------------------- #
# Trang quản trị
# --------------------------------------------------------------------------- #

@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template(
        "admin/dashboard.html",
        stats=services.dashboard_stats(),
        rooms=services.rooms_with_stats(),
        recent=services.list_bookings(limit=5),
        activity=services.list_activity_logs(limit=5),
    )


def _room_form_from(room):
    """Chuyển bản ghi phòng thành dữ liệu điền sẵn cho biểu mẫu."""
    if room is None:
        return {"id": "", "name": "", "floor": "", "capacity": "",
                "equipment": "", "image": "", "status": "active"}
    return {
        "id": room["id"],
        "name": room["name"],
        "floor": room["floor"],
        "capacity": room["capacity"],
        "equipment": "\n".join(room["equipment"]),
        "image": room["image"] or "",
        "status": room["status"],
    }


@app.route("/admin/rooms/new", methods=["GET", "POST"])
@admin_required
def admin_room_new():
    form = _room_form_from(None)
    errors = {}

    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in form}
        room, errors = services.create_room(form)
        if not errors:
            flash(f"Đã thêm phòng {room['name']} ({room['id']}).", "success")
            return redirect(url_for("admin_dashboard"))

    return render_template("admin/room_form.html", form=form, errors=errors,
                           mode="new", room=None)


@app.route("/admin/rooms/<room_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_room_edit(room_id):
    room = services.get_room(room_id)
    if room is None:
        abort(404)

    form = _room_form_from(room)
    errors = {}

    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in form}
        form["id"] = room_id
        updated, errors = services.update_room(room_id, form)
        if not errors:
            flash(f"Đã cập nhật phòng {updated['name']}.", "success")
            return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin/room_form.html", form=form, errors=errors, mode="edit", room=room,
        upcoming_count=services.count_room_bookings(room_id, only_upcoming=True),
    )


@app.route("/admin/rooms/<room_id>/status", methods=["POST"])
@admin_required
def admin_room_status(room_id):
    status = request.form.get("status", "")
    room, errors = services.set_room_status(room_id, status)
    if errors:
        flash(errors["_"], "error")
    else:
        upcoming = services.count_room_bookings(room_id, only_upcoming=True)
        message = f"{room['name']} chuyển sang trạng thái {room['status_label'].lower()}."
        if status == "maintenance" and upcoming:
            message += (f" Lưu ý: phòng vẫn còn {upcoming} lịch đã đặt sắp tới, "
                        "hãy thông báo cho người đặt.")
        flash(message, "success")
    return redirect(request.form.get("next") or url_for("admin_dashboard"))


@app.route("/admin/rooms/<room_id>/delete", methods=["POST"])
@admin_required
def admin_room_delete(room_id):
    room = services.get_room(room_id)
    if room is None:
        abort(404)
    errors = services.delete_room(room_id)
    if errors:
        flash(errors["_"], "error")
    else:
        flash(f"Đã xoá phòng {room['name']} ({room_id}).", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    filters = {
        "date": request.args.get("date", ""),
        "room_id": request.args.get("room_id", ""),
        "department": request.args.get("department", ""),
        "booked_by": request.args.get("booked_by", ""),
        "status": request.args.get("status", ""),
    }
    return render_template(
        "admin/bookings.html",
        bookings=services.list_bookings(
            date=filters["date"] or None,
            room_id=filters["room_id"] or None,
            department=filters["department"] or None,
            booked_by=filters["booked_by"] or None,
            status=filters["status"] or None,
        ),
        rooms=services.list_rooms(),
        departments=services.list_departments(),
        filters=filters,
    )


@app.route("/admin/logs")
@admin_required
def admin_logs():
    filters = {
        "booking_id": request.args.get("booking_id", "").strip(),
        "action": request.args.get("action", ""),
        "actor": request.args.get("actor", "").strip(),
    }
    booking = services.get_booking(filters["booking_id"]) if filters["booking_id"] else None
    return render_template(
        "admin/logs.html",
        logs=services.list_activity_logs(
            booking_id=filters["booking_id"] or None,
            action=filters["action"] or None,
            actor=filters["actor"] or None,
        ),
        stats=services.activity_stats(),
        action_labels=services.LOG_ACTION_LABELS,
        booking=booking,
        filters=filters,
    )


@app.route("/admin/bookings/<booking_id>/cancel", methods=["POST"])
@admin_required
def admin_booking_cancel(booking_id):
    booking, errors = services.cancel_booking(booking_id, is_admin=True)
    if errors:
        flash(next(iter(errors.values())), "error")
    else:
        flash(f"Đã huỷ booking {booking['id']} – {booking['room_name']}, "
              f"ngày {booking['date']} {booking['start_time']}–{booking['end_time']}. "
              "Khung giờ này đã được trả lại cho người khác đặt.", "success")
    return redirect(request.form.get("next") or url_for("admin_bookings"))


@app.route("/admin/users")
@admin_required
def admin_users():
    return render_template("admin/users.html", users=services.list_users_with_stats())


def _user_form_from(user):
    """Chuyển bản ghi tài khoản thành dữ liệu điền sẵn cho biểu mẫu."""
    if user is None:
        return {"full_name": "", "department": "", "username": ""}
    return {"full_name": user["full_name"], "department": user["department"],
            "username": user["username"]}


@app.route("/admin/users/new", methods=["GET", "POST"])
@admin_required
def admin_user_new():
    form = _user_form_from(None)
    errors = {}

    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in form}
        payload = dict(form, password=request.form.get("password", ""),
                       confirm_password=request.form.get("confirm_password", ""))
        user, errors = services.create_user(payload)
        if not errors:
            flash(f"Đã tạo tài khoản {user['full_name']} ({user['username']}).", "success")
            return redirect(url_for("admin_users"))

    return render_template("admin/user_form.html", form=form, errors=errors,
                           mode="new", user=None)


@app.route("/admin/users/<user_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_user_edit(user_id):
    user = services.get_user(user_id)
    if user is None:
        abort(404)

    form = _user_form_from(user)
    errors = {}

    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in form}
        updated, errors = services.update_user(user_id, form)
        if not errors:
            flash(f"Đã cập nhật tài khoản {updated['full_name']}.", "success")
            return redirect(url_for("admin_users"))

    return render_template(
        "admin/user_form.html", form=form, errors=errors, mode="edit", user=user,
        booking_count=services.count_user_bookings(user_id),
    )


@app.route("/admin/users/<user_id>/reset-password", methods=["GET", "POST"])
@admin_required
def admin_user_reset_password(user_id):
    user = services.get_user(user_id)
    if user is None:
        abort(404)

    errors = {}
    if request.method == "POST":
        errors = services.set_user_password(
            user_id, request.form.get("password", ""), request.form.get("confirm_password", "")
        )
        if not errors:
            flash(f"Đã đặt lại mật khẩu cho {user['full_name']}.", "success")
            return redirect(url_for("admin_users"))

    return render_template("admin/user_reset_password.html", user=user, errors=errors)


@app.route("/admin/users/<user_id>/delete", methods=["POST"])
@admin_required
def admin_user_delete(user_id):
    user = services.get_user(user_id)
    if user is None:
        abort(404)
    errors = services.delete_user(user_id)
    if errors:
        flash(errors["_"], "error")
    else:
        flash(f"Đã xoá tài khoản {user['full_name']} ({user_id}).", "success")
    return redirect(url_for("admin_users"))


# --------------------------------------------------------------------------- #
# Lỗi
# --------------------------------------------------------------------------- #

@app.errorhandler(400)
def bad_request(error):
    message = getattr(error, "description", "Yêu cầu không hợp lệ.")
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "errors": {"_": message}}), 400
    return render_template("error.html", code=400, message=message), 400


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "errors": {"_": "Không tìm thấy tài nguyên."}}), 404
    return render_template("error.html", code=404,
                           message="Không tìm thấy trang bạn yêu cầu."), 404


@app.errorhandler(500)
def server_error(_error):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "errors": {"_": "Lỗi hệ thống."}}), 500
    return render_template("error.html", code=500,
                           message="Đã xảy ra lỗi trong hệ thống."), 500


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
