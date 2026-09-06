/* Tiện ích dùng chung: toast, trạng thái loading, hiển thị lỗi form. */
(function (window, document) {
  'use strict';

  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function toast(message, type) {
    var stack = document.getElementById('toastStack');
    if (!stack) { return; }
    var el = document.createElement('div');
    el.className = 'toast-item alert alert-' + (type === 'success' ? 'success' : 'danger') + ' shadow-sm';
    el.setAttribute('role', 'alert');
    el.innerHTML = '<span>' + escapeHtml(message) + '</span>' +
      '<button type="button" class="btn-close" aria-label="Đóng"></button>';
    stack.appendChild(el);
    window.setTimeout(function () { dismiss(el); }, 6000);
  }

  function dismiss(el) {
    if (el && el.parentNode) { el.parentNode.removeChild(el); }
  }

  function setLoading(button, isLoading) {
    if (!button) { return; }
    var spinner = button.querySelector('.spinner-border');
    button.disabled = !!isLoading;
    if (spinner) { spinner.classList.toggle('d-none', !isLoading); }
  }

  function clearErrors(form) {
    form.querySelectorAll('.is-invalid').forEach(function (el) {
      el.classList.remove('is-invalid');
    });
  }

  function showFieldError(form, field, message) {
    var input = form.querySelector('[name="' + field + '"]');
    if (!input) { return false; }
    input.classList.add('is-invalid');
    var feedback = form.querySelector('.invalid-feedback[data-field="' + field + '"]');
    if (feedback && message) { feedback.textContent = message; }
    return true;
  }

  function showErrors(form, errors) {
    clearErrors(form);
    var firstInput = null;
    Object.keys(errors || {}).forEach(function (field) {
      if (showFieldError(form, field, errors[field])) {
        if (!firstInput) { firstInput = form.querySelector('[name="' + field + '"]'); }
      } else {
        toast(errors[field], 'error');
      }
    });
    if (firstInput) { firstInput.focus(); }
  }

  // Phải khớp với BOOKING_MIN_HOUR/BOOKING_MAX_HOUR/MIN_BOOKING_MINUTES/
  // MAX_BOOKING_MINUTES trong services.py — đây chỉ là kiểm tra trước cho
  // nhanh, backend luôn là nơi quyết định cuối cùng.
  var BOOKING_MIN_HOUR = 8;
  var BOOKING_MAX_HOUR = 18;
  var MIN_BOOKING_MINUTES = 15;
  var MAX_BOOKING_MINUTES = 4 * 60;

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function todayStr() {
    var d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  function timeToMinutes(hhmm) {
    var parts = hhmm.split(':');
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
  }

  /* Kiểm tra ngày / giờ / số người ở phía trình duyệt.
     Backend luôn kiểm tra lại các điều kiện này. */
  function validateSlot(values, options) {
    var errors = {};
    var requireAttendees = !options || options.requireAttendees !== false;

    if (!values.date) {
      errors.date = 'Vui lòng chọn ngày họp.';
    } else if (!/^\d{4}-\d{2}-\d{2}$/.test(values.date)) {
      errors.date = 'Ngày không hợp lệ (định dạng YYYY-MM-DD).';
    }

    if (!values.start_time) {
      errors.start_time = 'Vui lòng nhập giờ bắt đầu.';
    }
    if (!values.end_time) {
      errors.end_time = 'Vui lòng nhập giờ kết thúc.';
    } else if (values.start_time && values.end_time <= values.start_time) {
      errors.end_time = 'Giờ kết thúc phải lớn hơn giờ bắt đầu.';
    }

    // Khung giờ hành chính + giới hạn thời lượng, chỉ xét khi giờ bắt đầu/kết
    // thúc đều hợp lệ và chưa có lỗi nào ở trên (đúng thứ tự ưu tiên như
    // backend, để hai bên nhất quán khi cùng áp dụng nhiều điều kiện).
    if (!errors.start_time && !errors.end_time && values.start_time && values.end_time) {
      var startMin = timeToMinutes(values.start_time);
      var endMin = timeToMinutes(values.end_time);
      var duration = endMin - startMin;

      if (startMin < BOOKING_MIN_HOUR * 60) {
        errors.start_time = 'Giờ bắt đầu phải từ ' + pad2(BOOKING_MIN_HOUR) + ':00 trở đi.';
      } else if (endMin > BOOKING_MAX_HOUR * 60) {
        errors.end_time = 'Giờ kết thúc phải trước ' + pad2(BOOKING_MAX_HOUR) + ':00.';
      } else if (duration < MIN_BOOKING_MINUTES) {
        errors.end_time = 'Cuộc họp phải kéo dài ít nhất ' + MIN_BOOKING_MINUTES + ' phút.';
      } else if (duration > MAX_BOOKING_MINUTES) {
        errors.end_time = 'Cuộc họp không được kéo dài quá ' + (MAX_BOOKING_MINUTES / 60) + ' giờ.';
      }
    }

    // Dời sang một ngày đã qua thì luôn chặn, kể cả ở trang sửa lịch — không
    // có lý do hợp lệ để làm việc đó. Riêng "giờ bắt đầu của hôm nay đã trôi
    // qua" mới bỏ qua khi options.checkPast===false (trang sửa lịch), để sửa
    // được các lịch đang diễn ra (giờ bắt đầu vốn dĩ đã ở quá khứ).
    var checkPastTime = !options || options.checkPast !== false;
    if (values.date && !errors.date) {
      var today = todayStr();
      if (values.date < today) {
        errors.date = 'Không thể đặt lịch cho ngày trong quá khứ.';
      } else if (checkPastTime && values.date === today && values.start_time && !errors.start_time) {
        var now = new Date();
        if (timeToMinutes(values.start_time) < now.getHours() * 60 + now.getMinutes()) {
          errors.start_time = 'Giờ bắt đầu đã qua, vui lòng chọn giờ khác.';
        }
      }
    }

    if (requireAttendees || (values.attendees !== '' && values.attendees !== undefined)) {
      if (values.attendees === '' || values.attendees === undefined) {
        errors.attendees = 'Vui lòng nhập số người dự kiến.';
      } else {
        var n = Number(values.attendees);
        if (!Number.isInteger(n)) {
          errors.attendees = 'Số người phải là một số nguyên.';
        } else if (n <= 0) {
          errors.attendees = 'Số người phải lớn hơn 0.';
        }
      }
    }
    return errors;
  }

  function formValues(form) {
    var data = {};
    new FormData(form).forEach(function (value, key) {
      data[key] = typeof value === 'string' ? value.trim() : value;
    });
    return data;
  }

  document.addEventListener('click', function (event) {
    if (event.target.classList.contains('btn-close')) {
      dismiss(event.target.closest('.toast-item'));
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('#toastStack .toast-item').forEach(function (el) {
      window.setTimeout(function () { dismiss(el); }, 8000);
    });
  });

  window.OB = {
    escapeHtml: escapeHtml,
    toast: toast,
    setLoading: setLoading,
    clearErrors: clearErrors,
    showErrors: showErrors,
    validateSlot: validateSlot,
    formValues: formValues
  };
})(window, document);
