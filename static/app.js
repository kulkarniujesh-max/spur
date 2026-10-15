document.addEventListener('DOMContentLoaded', () => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  document.querySelectorAll('form[method="post"], form:not([method])').forEach(form => {
    if (!form.querySelector('[name="csrf_token"]')) {
      const input = document.createElement('input');
      input.type = 'hidden'; input.name = 'csrf_token'; input.value = token || '';
      form.append(input);
    }
  });
  const dialog = document.querySelector('#register-dialog');
  document.querySelector('[data-open-register]')?.addEventListener('click', () => dialog?.showModal());
  document.querySelector('[data-close-register]')?.addEventListener('click', () => dialog?.close());
  dialog?.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  const preview = document.querySelector('#event-preview-dialog');
  const previewContent = document.querySelector('#event-preview-content');
  document.querySelectorAll('[data-event-preview]').forEach(link => link.addEventListener('click', async event => {
    event.preventDefault();
    try {
      const response = await fetch(link.dataset.eventPreview, { headers: { 'X-Requested-With': 'fetch' } });
      if (!response.ok) throw new Error('Could not load event details');
      previewContent.innerHTML = await response.text();
      const close = previewContent.querySelector('[data-close-preview]');
      close?.addEventListener('click', () => preview.close());
      preview.showModal();
    } catch (_error) { window.location.href = link.href; }
  }));
  preview?.addEventListener('click', event => { if (event.target === preview) preview.close(); });
  const count = document.querySelector('[data-participant-count]');
  const names = document.querySelector('[data-participant-names]');
  count?.addEventListener('change', () => {
    const wanted = Math.max(1, Math.min(20, Number(count.value) || 1));
    count.value = wanted;
    const existing = names.value.split('\n');
    while (existing.length < wanted) existing.push('');
    names.value = existing.slice(0, wanted).join('\n');
  });

  const search = document.querySelector('[data-event-search]');
  const clearSearch = document.querySelector('[data-clear-search]');
  const filterButtons = [...document.querySelectorAll('[data-event-filter]')];
  const resultCount = document.querySelector('[data-event-results]');
  const noResults = document.querySelector('[data-event-no-results]');
  const eventCards = [...document.querySelectorAll('.event-card')];
  let activeFilter = 'all';

  function updateEventResults() {
    if (!search || !eventCards.length) return;
    const term = search.value.trim().toLocaleLowerCase();
    let visibleCount = 0;

    eventCards.forEach(card => {
      const section = card.closest('#discover, #upcoming');
      const eventType = section?.id === 'discover' ? 'live' : 'upcoming';
      const matchesFilter = activeFilter === 'all' || activeFilter === eventType;
      const matchesSearch = !term || card.textContent.toLocaleLowerCase().includes(term);
      card.hidden = !(matchesFilter && matchesSearch);
      if (!card.hidden) visibleCount += 1;
    });

    document.querySelectorAll('#discover, #upcoming').forEach(section => {
      const cards = [...section.querySelectorAll('.event-card')];
      const sectionType = section.id === 'discover' ? 'live' : 'upcoming';
      const sectionEligible = activeFilter === 'all' || activeFilter === sectionType;
      section.hidden = !sectionEligible;
      if (cards.length) {
        const visibleInSection = cards.some(card => !card.hidden);
        const heading = section.querySelector('.section-heading');
        const grid = section.querySelector('.event-grid');
        if (heading) heading.hidden = !visibleInSection;
        if (grid) grid.hidden = !visibleInSection;
      }
    });

    clearSearch.hidden = !search.value;
    noResults.hidden = visibleCount > 0;
    resultCount.textContent = visibleCount === eventCards.length && activeFilter === 'all' && !term
      ? `${eventCards.length} event${eventCards.length === 1 ? '' : 's'}`
      : `Showing ${visibleCount} of ${eventCards.length} events`;
  }

  search?.addEventListener('input', updateEventResults);
  clearSearch?.addEventListener('click', () => {
    search.value = '';
    search.focus();
    updateEventResults();
  });
  filterButtons.forEach(button => button.addEventListener('click', () => {
    activeFilter = button.dataset.eventFilter;
    filterButtons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    updateEventResults();
  }));
  updateEventResults();
});
