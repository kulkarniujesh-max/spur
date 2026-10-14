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
});
