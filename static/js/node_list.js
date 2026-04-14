(function () {
  const filter = document.querySelector('[data-status-filter]');
  if (!filter) {
    return;
  }

  filter.addEventListener('change', function () {
    const form = filter.closest('[data-node-filter-form]');
    if (form) {
      form.submit();
    }
  });
})();
