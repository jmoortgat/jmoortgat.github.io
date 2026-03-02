/* main.js — Navigation active state, mobile hamburger, publication filter */

document.addEventListener('DOMContentLoaded', function () {

  /* ----------------------------------------
     Active nav link (based on current page)
     ---------------------------------------- */
  const currentFile = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(function (link) {
    const href = link.getAttribute('href');
    if (href === currentFile || (currentFile === '' && href === 'index.html')) {
      link.classList.add('active');
    }
  });

  /* ----------------------------------------
     Mobile hamburger toggle
     ---------------------------------------- */
  const hamburger = document.getElementById('navHamburger');
  const navLinks  = document.getElementById('navLinks');

  if (hamburger && navLinks) {
    hamburger.addEventListener('click', function () {
      const isOpen = navLinks.classList.contains('open');
      navLinks.classList.toggle('open');
      hamburger.setAttribute('aria-expanded', String(!isOpen));
    });

    // Close menu when a link is clicked (mobile UX)
    navLinks.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        navLinks.classList.remove('open');
        hamburger.setAttribute('aria-expanded', 'false');
      });
    });
  }

  /* ----------------------------------------
     Publication filter
     ---------------------------------------- */
  const filterBtns = document.querySelectorAll('.filter-btn');
  const pubItems   = document.querySelectorAll('.pub-item');

  if (filterBtns.length && pubItems.length) {
    filterBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        filterBtns.forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');

        var cat = btn.dataset.filter;

        pubItems.forEach(function (item) {
          if (cat === 'all') {
            item.classList.remove('filtered-out');
          } else {
            var cats = (item.dataset.category || '').split(' ');
            if (cats.indexOf(cat) !== -1) {
              item.classList.remove('filtered-out');
            } else {
              item.classList.add('filtered-out');
            }
          }
        });
      });
    });
  }

});
