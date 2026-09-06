/* Trang đăng nhập: bấm vào một tài khoản gợi ý để điền nhanh tên đăng nhập. */
(function (document) {
  'use strict';

  var input = document.getElementById('username');
  if (!input) { return; }

  document.querySelectorAll('.account-pick').forEach(function (button) {
    button.addEventListener('click', function () {
      input.value = button.dataset.username;
      document.querySelectorAll('.account-pick').forEach(function (other) {
        other.classList.toggle('is-selected', other === button);
      });
      var password = document.getElementById('password');
      if (password) { password.focus(); }
    });
  });
})(document);
