(function () {
  if (typeof window === 'undefined') {
    return;
  }

  const tables = document.querySelectorAll('[data-enhanced-table]');
  if (!tables.length) {
    return;
  }

  const parseValue = (raw, sortType) => {
    const text = String(raw || '').trim();
    if (!text || text === '-') {
      return null;
    }

    if (sortType === 'number') {
      const normalized = text.replace(/,/g, '');
      const num = Number.parseFloat(normalized);
      return Number.isNaN(num) ? null : num;
    }

    if (sortType === 'date') {
      const t = Date.parse(text);
      return Number.isNaN(t) ? null : t;
    }

    return text.toLowerCase();
  };

  tables.forEach((table) => {
    const tbody = table.tBodies && table.tBodies[0];
    if (!tbody) {
      return;
    }

    const allRows = Array.from(tbody.rows).filter((row) => !row.hasAttribute('data-empty-row'));
    if (!allRows.length) {
      return;
    }

    const pageSize = Math.max(Number.parseInt(table.dataset.pageSize || '10', 10) || 10, 1);
    let currentPage = 1;
    let sortState = { index: -1, direction: 'asc', sortType: 'text' };
    let sortedRows = allRows.slice();

    const paginationNav = document.createElement('div');
    paginationNav.className = 'd-flex justify-content-between align-items-center px-3 py-2 border-top';
    const pageInfo = document.createElement('small');
    pageInfo.className = 'text-muted';
    const controlWrap = document.createElement('div');
    controlWrap.className = 'btn-group btn-group-sm';
    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'btn btn-outline-secondary';
    prevBtn.textContent = 'Prev';
    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'btn btn-outline-secondary';
    nextBtn.textContent = 'Next';
    controlWrap.appendChild(prevBtn);
    controlWrap.appendChild(nextBtn);
    paginationNav.appendChild(pageInfo);
    paginationNav.appendChild(controlWrap);

    const wrapper = table.closest('.table-responsive') || table.parentElement;
    if (wrapper) {
      wrapper.insertAdjacentElement('afterend', paginationNav);
    }

    const render = () => {
      const totalPages = Math.max(Math.ceil(sortedRows.length / pageSize), 1);
      currentPage = Math.min(Math.max(currentPage, 1), totalPages);

      const start = (currentPage - 1) * pageSize;
      const pageRows = sortedRows.slice(start, start + pageSize);
      tbody.innerHTML = '';
      pageRows.forEach((row) => tbody.appendChild(row));

      pageInfo.textContent = `${currentPage} / ${totalPages} (total: ${sortedRows.length})`;
      prevBtn.disabled = currentPage <= 1;
      nextBtn.disabled = currentPage >= totalPages;
    };

    prevBtn.addEventListener('click', () => {
      currentPage -= 1;
      render();
    });

    nextBtn.addEventListener('click', () => {
      currentPage += 1;
      render();
    });

    const headers = Array.from(table.querySelectorAll('thead th[data-sortable]'));
    headers.forEach((th, headerIndex) => {
      const colIndex = Number.parseInt(th.dataset.sortIndex || String(headerIndex), 10);
      const sortType = th.dataset.sortType || 'text';
      th.classList.add('table-sortable-header');
      th.addEventListener('click', () => {
        const sameColumn = sortState.index === colIndex;
        const direction = sameColumn && sortState.direction === 'asc' ? 'desc' : 'asc';
        sortState = { index: colIndex, direction, sortType };

        headers.forEach((header) => {
          header.removeAttribute('data-sort-direction');
        });
        th.setAttribute('data-sort-direction', direction);

        sortedRows = sortedRows.slice().sort((a, b) => {
          const aCell = a.cells[colIndex];
          const bCell = b.cells[colIndex];
          const aVal = parseValue(aCell ? aCell.textContent : '', sortType);
          const bVal = parseValue(bCell ? bCell.textContent : '', sortType);

          if (aVal === null && bVal === null) return 0;
          if (aVal === null) return 1;
          if (bVal === null) return -1;
          if (aVal < bVal) return direction === 'asc' ? -1 : 1;
          if (aVal > bVal) return direction === 'asc' ? 1 : -1;
          return 0;
        });

        currentPage = 1;
        render();
      });
    });

    render();
  });
})();