/* Trang quản trị: hỏi xác nhận trước các thao tác không hoàn tác được. */
(function (document) {
  'use strict';

  document.addEventListener('submit', function (event) {
    var form = event.target;
    var trigger = form.querySelector('[data-confirm]');
    if (!trigger) { return; }
    if (!window.confirm(trigger.dataset.confirm)) {
      event.preventDefault();
      return;
    }
    trigger.disabled = true;
    // Nút bị vô hiệu hoá sẽ không được gửi kèm, nhưng các input hidden vẫn đi bình thường.
  });
})(document);
