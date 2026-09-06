/* Trang Danh sách phòng họp: kiểm tra phòng trống theo khung giờ. */
(function (window, document) {
  'use strict';

  var OB = window.OB;
  var form = document.getElementById('availabilityForm');
  var results = document.getElementById('availabilityResults');
  var button = document.getElementById('checkBtn');
  if (!form || !results) { return; }

  var STATIC_PREFIX = '/static/';

  function statusBadge(room) {
    if (room.status === 'active') {
      return '<span class="badge badge-active">● ' + OB.escapeHtml(room.status_label) + '</span>';
    }
    if (room.status === 'maintenance') {
      return '<span class="badge badge-maintenance">🛠 ' + OB.escapeHtml(room.status_label) + '</span>';
    }
    return '<span class="badge badge-inactive">' + OB.escapeHtml(room.status_label) + '</span>';
  }

  function thumb(room) {
    var fallback = '<div class="room-thumb-fallback"><span>' +
      OB.escapeHtml(room.id) + '</span></div>';
    if (!room.image) { return fallback; }
    // Nếu ảnh không tồn tại, chỉ thay riêng thẻ <img> bằng khối dự phòng
    // để badge trạng thái nằm cùng khung ảnh không bị xoá.
    return '<img src="' + STATIC_PREFIX + OB.escapeHtml(room.image) + '" alt="' +
      OB.escapeHtml(room.name) + '" loading="lazy" ' +
      'onerror="this.outerHTML=this.parentNode.dataset.fallback">';
  }

  function bookUrl(room, criteria) {
    var params = new URLSearchParams({
      room_id: room.id,
      date: criteria.date,
      start_time: criteria.start_time,
      end_time: criteria.end_time,
      attendees: criteria.attendees
    });
    return '/book?' + params.toString();
  }

  function roomCard(room, criteria) {
    var equipment = (room.equipment || []).map(function (item) {
      return '<span class="chip">' + OB.escapeHtml(item) + '</span>';
    }).join('');

    return '' +
      '<div class="col-12 col-md-6 col-xl-4">' +
        '<article class="room-card h-100">' +
          '<div class="room-thumb" data-fallback="' +
            OB.escapeHtml('<div class="room-thumb-fallback"><span>' + room.id + '</span></div>') +
            '">' + thumb(room) +
            '<div class="room-thumb-status">' + statusBadge(room) + '</div>' +
          '</div>' +
          '<div class="room-body">' +
            '<h3 class="room-name">' + OB.escapeHtml(room.name) + '</h3>' +
            '<ul class="room-meta">' +
              '<li><span>Mã phòng</span><strong>' + OB.escapeHtml(room.id) + '</strong></li>' +
              '<li><span>Tầng</span><strong>' + OB.escapeHtml(room.floor) + '</strong></li>' +
              '<li><span>Sức chứa</span><strong>' + OB.escapeHtml(room.capacity) + ' người</strong></li>' +
            '</ul>' +
            '<div class="room-equipment">' + (equipment || '<span class="text-muted small">Chưa cập nhật thiết bị</span>') + '</div>' +
            '<a class="btn btn-primary w-100 mt-3" href="' + bookUrl(room, criteria) + '">Đặt phòng này</a>' +
          '</div>' +
        '</article>' +
      '</div>';
  }

  function suggestionsHtml(suggestions, criteria) {
    if (!suggestions || (!suggestions.rooms.length && !suggestions.nearest_starts.length)) {
      return '';
    }
    var html = '<div class="suggestion-box mt-3">';
    if (suggestions.rooms.length) {
      html += '<p class="mb-2"><strong>Phòng trống gần khung giờ này:</strong></p><ul class="suggestion-list">';
      suggestions.rooms.forEach(function (opt) {
        var bookParams = new URLSearchParams({
          room_id: opt.room.id,
          date: criteria.date,
          start_time: opt.book_start,
          end_time: opt.book_end,
          attendees: criteria.attendees
        });
        html += '<li><a href="/book?' + bookParams.toString() + '">' +
          OB.escapeHtml(opt.room.name) + ' trống ' + OB.escapeHtml(opt.start_time) +
          '–' + OB.escapeHtml(opt.end_time) + '</a></li>';
      });
      html += '</ul>';
    }
    if (suggestions.nearest_starts.length) {
      html += '<p class="mb-2"><strong>Khung giờ gần nhất còn trống:</strong></p><div class="d-flex flex-wrap gap-2">';
      suggestions.nearest_starts.forEach(function (slot) {
        var slotParams = new URLSearchParams({
          check: 1,
          date: criteria.date,
          start_time: slot.start_time,
          end_time: slot.end_time,
          attendees: criteria.attendees
        });
        html += '<a class="btn btn-outline-primary btn-sm" href="/rooms?' + slotParams.toString() +
          '#availability">' + OB.escapeHtml(slot.start_time) + '</a>';
      });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function renderLoading() {
    results.innerHTML =
      '<div class="loading-state">' +
        '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Đang tải…</span></div>' +
        '<p class="mt-2 mb-0">Đang kiểm tra phòng trống…</p>' +
      '</div>';
  }

  function renderResults(payload) {
    var criteria = payload.criteria;
    var head = '' +
      '<div class="result-head">' +
        '<h3 class="h6 mb-0">Kết quả cho ngày ' + OB.escapeHtml(criteria.date) + ', ' +
          OB.escapeHtml(criteria.start_time) + ' – ' + OB.escapeHtml(criteria.end_time) + ', ' +
          OB.escapeHtml(criteria.attendees) + ' người</h3>' +
        '<span class="badge text-bg-light">' + payload.count + ' phòng</span>' +
      '</div>';

    if (!payload.rooms.length) {
      results.innerHTML = head + suggestionsHtml(payload.suggestions, criteria) +
        '<div class="empty-state">' +
          '<div class="empty-icon">🔍</div>' +
          '<h3>Không có phòng nào phù hợp</h3>' +
          '<p>Không tìm thấy phòng còn trống đáp ứng sức chứa trong khung giờ này. ' +
          'Hãy thử khung giờ khác hoặc giảm số người.</p>' +
        '</div>';
      return;
    }

    results.innerHTML = head + '<div class="row g-3 mt-1">' +
      payload.rooms.map(function (room) { return roomCard(room, criteria); }).join('') +
      '</div>';
  }

  form.addEventListener('submit', function (event) {
    var values = OB.formValues(form);
    var errors = OB.validateSlot(values, { requireAttendees: true });

    if (Object.keys(errors).length) {
      event.preventDefault();
      OB.showErrors(form, errors);
      return;
    }

    // Có JavaScript: gọi API để hiển thị loading và kết quả tại chỗ.
    event.preventDefault();
    OB.clearErrors(form);
    OB.setLoading(button, true);
    renderLoading();

    var params = new URLSearchParams({
      date: values.date,
      start_time: values.start_time,
      end_time: values.end_time,
      attendees: values.attendees
    });

    fetch('/api/availability?' + params.toString(), {
      headers: { 'Accept': 'application/json' }
    })
      .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok || !res.body.ok) {
          results.innerHTML = '';
          OB.showErrors(form, res.body.errors || { _: 'Không kiểm tra được phòng trống.' });
          return;
        }
        renderResults(res.body);
        OB.toast(res.body.message, res.body.count ? 'success' : 'error');
      })
      .catch(function () {
        results.innerHTML = '';
        OB.toast('Không kết nối được tới máy chủ. Vui lòng thử lại.', 'error');
      })
      .finally(function () { OB.setLoading(button, false); });
  });
})(window, document);
