/* Trang chủ: bấm vào ô trống trên lưới lịch phòng để đặt nhanh khung giờ đó. */
(function (document) {
  'use strict';

  var grid = document.getElementById('roomGrid');
  if (!grid) { return; }

  var marks = grid.querySelectorAll('.hour-mark');
  if (!marks.length) { return; }

  function parseTime(text) {
    var parts = text.trim().split(':');
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
  }

  function formatTime(minutes) {
    minutes = Math.max(0, Math.min(23 * 60 + 59, minutes));
    var h = Math.floor(minutes / 60);
    var m = minutes % 60;
    return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
  }

  // Đọc khung giờ hiển thị trực tiếp từ mốc giờ đầu/cuối đã render, để không
  // phải lặp lại hằng số GRID_START_HOUR/GRID_END_HOUR của backend ở đây.
  var windowStartMin = parseTime(marks[0].textContent);
  var windowEndMin = parseTime(marks[marks.length - 1].textContent);
  var date = grid.dataset.date;

  grid.querySelectorAll('.room-grid-track[data-room-id]').forEach(function (track) {
    track.addEventListener('click', function (event) {
      if (event.target.closest('.room-block')) { return; } // đã có lịch, không đặt đè lên

      var rect = track.getBoundingClientRect();
      var fraction = (event.clientX - rect.left) / rect.width;
      fraction = Math.max(0, Math.min(1, fraction));

      var clickedMinutes = windowStartMin + fraction * (windowEndMin - windowStartMin);
      var startMinutes = Math.round(clickedMinutes / 30) * 30; // làm tròn về mốc 30 phút
      var endMinutes = startMinutes + 60; // mặc định đặt 1 giờ, tự điều chỉnh được ở trang đặt phòng

      var params = new URLSearchParams({
        room_id: track.dataset.roomId,
        date: date,
        start_time: formatTime(startMinutes),
        end_time: formatTime(endMinutes)
      });
      window.location.href = '/book?' + params.toString();
    });
  });
})(document);
