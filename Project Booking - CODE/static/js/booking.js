/* Trang Tạo lịch đặt: kiểm tra dữ liệu phía trình duyệt và xem lịch đã đặt của phòng. */
(function (window, document) {
  'use strict';

  var OB = window.OB;
  var form = document.getElementById('bookingForm');
  if (!form) { return; }

  var submitBtn = document.getElementById('submitBooking');
  var scheduleBox = document.getElementById('roomSchedule');
  var roomSelect = form.querySelector('#room_id');
  var dateInput = form.querySelector('#date');
  var attendeesInput = form.querySelector('#attendees');

  // Trang sửa lịch đánh dấu data-check-past="false" trên form: lịch đang
  // diễn ra vẫn được phép sửa dù giờ bắt đầu đã ở quá khứ, khớp với backend.
  var checkPast = form.dataset.checkPast !== 'false';

  function validate(values) {
    var errors = OB.validateSlot(values, { requireAttendees: false, checkPast: checkPast });

    if (!values.room_id) { errors.room_id = 'Vui lòng chọn phòng họp.'; }
    if (!values.booked_by) { errors.booked_by = 'Vui lòng nhập người đặt.'; }
    if (!values.department) { errors.department = 'Vui lòng nhập phòng ban.'; }
    if (!values.purpose) { errors.purpose = 'Vui lòng nhập mục đích cuộc họp.'; }

    var option = roomSelect.selectedOptions[0];
    if (option && values.attendees && !errors.attendees) {
      var capacity = Number(option.dataset.capacity || 0);
      if (Number(values.attendees) > capacity) {
        errors.attendees = 'Phòng này chỉ chứa tối đa ' + capacity + ' người.';
      }
    }
    return errors;
  }

  form.addEventListener('submit', function (event) {
    var values = OB.formValues(form);
    var errors = validate(values);
    if (Object.keys(errors).length) {
      event.preventDefault();
      OB.showErrors(form, errors);
      OB.toast('Vui lòng kiểm tra lại thông tin đã nhập.', 'error');
      return;
    }
    OB.clearErrors(form);
    OB.setLoading(submitBtn, true);
  });

  /* ------------------------- Lịch đã đặt của phòng ------------------------- */

  function renderSchedule(bookings) {
    if (!bookings.length) {
      scheduleBox.innerHTML = '<p class="text-muted mb-0">Phòng còn trống cả ngày này.</p>';
      return;
    }
    scheduleBox.innerHTML = bookings.map(function (bk) {
      return '<div class="schedule-item">' +
        '<strong>' + OB.escapeHtml(bk.start_time) + ' – ' + OB.escapeHtml(bk.end_time) + '</strong>' +
        '<span class="text-muted">' + OB.escapeHtml(bk.booked_by) + ' · ' + OB.escapeHtml(bk.department) + '</span>' +
        '</div>';
    }).join('');
  }

  function loadSchedule() {
    if (!scheduleBox) { return; }
    var roomId = roomSelect.value;
    var date = dateInput.value;
    if (!roomId || !date) {
      scheduleBox.innerHTML = '<p class="text-muted mb-0">Chọn phòng và ngày để xem các khung giờ đã có lịch.</p>';
      return;
    }
    scheduleBox.innerHTML = '<div class="loading-state py-3">' +
      '<div class="spinner-border spinner-border-sm text-primary" role="status"></div> Đang tải lịch…</div>';

    fetch('/api/rooms/' + encodeURIComponent(roomId) + '/schedule?date=' + encodeURIComponent(date))
      .then(function (res) { return res.json(); })
      .then(function (body) {
        if (!body.ok) {
          scheduleBox.innerHTML = '<p class="text-danger mb-0">Không tải được lịch của phòng.</p>';
          return;
        }
        renderSchedule(body.bookings);
      })
      .catch(function () {
        scheduleBox.innerHTML = '<p class="text-danger mb-0">Không kết nối được tới máy chủ.</p>';
      });
  }

  function syncCapacityHint() {
    var option = roomSelect.selectedOptions[0];
    if (option && option.dataset.capacity && attendeesInput) {
      attendeesInput.max = option.dataset.capacity;
    }
  }

  roomSelect.addEventListener('change', function () {
    syncCapacityHint();
    loadSchedule();
  });
  dateInput.addEventListener('change', loadSchedule);

  syncCapacityHint();
  loadSchedule();
})(window, document);
