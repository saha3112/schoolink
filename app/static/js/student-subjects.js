(() => {
 const root = document.getElementById('subjectPage'); if (!root) return;
 const all = selector => Array.from(root.querySelectorAll(selector));
 function update() {
  const cells = all('.cell'), count = cells.filter(c => c.checked).length;
  root.querySelector('#allocationCount').textContent = count;
  root.querySelector('#completionRate').textContent = (cells.length ? Math.round(count / cells.length * 100) : 0) + '%';
  const label = root.querySelector('#selectedLabel'); if (label) label.textContent = count + ' allocations selected';
  all('.col-all,.row-all').forEach(box => {
   const group = all(box.classList.contains('col-all') ? '.cell[data-c="' + box.dataset.col + '"]' : '.cell[data-r="' + box.dataset.row + '"]');
   const checked = group.filter(c => c.checked).length;
   box.checked = group.length > 0 && checked === group.length;
   box.indeterminate = checked > 0 && checked < group.length;
  });
 }
 let pendingRequest = null;
 async function loadSelection(classChanged = false) {
  if (pendingRequest) pendingRequest.abort();
  const controller = new AbortController(); pendingRequest = controller;
  const query = root.querySelector('#studentSearch').value;
  const url = new URL(location.href);
  url.searchParams.delete('detect');
  url.searchParams.set('class_id', root.querySelector('#subjectClass').value);
  url.searchParams.set('section_id', classChanged ? '' : root.querySelector('#subjectSection').value);
  const status = root.querySelector('#subjectLoadStatus');
  status.textContent = 'Loading student subjects…';
  root.setAttribute('aria-busy', 'true');
  const save = root.querySelector('#allocationForm button[type=submit]'); if (save) save.disabled = true;
  const readPage = async () => {
   const response = await fetch(url, {signal: controller.signal, credentials: 'same-origin'});
   if (!response.ok) throw new Error('Unable to load student subjects. Please try again.');
   const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
   const page = doc.getElementById('subjectPage');
   if (!page) throw new Error('Your session may have expired. Please sign in again.');
   return page;
  };
  try {
   let page = await readPage();
   if (classChanged && url.searchParams.get('class_id')) {
    const firstSection = Array.from(page.querySelector('#subjectSection').options).find(option => option.value);
    if (firstSection) { url.searchParams.set('section_id', firstSection.value); page = await readPage(); }
   }
   if (controller.signal.aborted) return;
   root.innerHTML = page.innerHTML;
   history.replaceState(null, '', url.pathname + url.search);
   const main = root.closest('main');
   if (main) { main.dataset.liveClass = url.searchParams.get('class_id'); main.dataset.liveSection = url.searchParams.get('section_id'); }
   const search = root.querySelector('#studentSearch'); search.value = query;
   update(); search.dispatchEvent(new Event('input', {bubbles:true}));
   if (window.slPretty) window.slPretty.init();
  } catch (error) {
   if (error.name !== 'AbortError') root.querySelector('#subjectLoadStatus').textContent = error.message;
  } finally {
   if (pendingRequest === controller) { pendingRequest = null; root.removeAttribute('aria-busy'); const save = root.querySelector('#allocationForm button[type=submit]'); if (save) save.disabled = false; }
  }
 }
 root.addEventListener('submit', e => {
  if (e.target.matches('.filters')) { e.preventDefault(); loadSelection(); }
 });
 root.addEventListener('change', e => {
  const box = e.target;
  if (box.matches('#subjectClass,#subjectSection')) { loadSelection(box.id === 'subjectClass'); return; }
  if (box.matches('.col-all,.row-all')) all(box.matches('.col-all') ? '.cell[data-c="' + box.dataset.col + '"]' : '.cell[data-r="' + box.dataset.row + '"]').forEach(c => c.checked = box.checked);
  if (box.matches('.cell,.col-all,.row-all')) { update(); root.querySelector('#saveStatus').textContent = 'Unsaved changes · Press Save to apply'; }
 });
 root.addEventListener('input', e => {
  if (e.target.id !== 'studentSearch') return;
  const query = e.target.value.trim().toLowerCase(), rows = all('[data-student-row]');
  rows.forEach(row => row.hidden = !row.querySelector('.student-name span').textContent.toLowerCase().includes(query) && !row.querySelector('.roll').textContent.includes(query));
  const info = root.querySelector('#footerInfo');
  if (info) info.textContent = `Showing ${rows.filter(r => !r.hidden).length} of ${rows.length} students · ${all('.col-all').length} subjects`;
 });
 root.addEventListener('click', e => {
  const button = e.target.closest('[data-action]'); if (!button) return;
  if (button.dataset.action === 'export') {
   const rows = [['Roll', 'Student', ...all('.vertical').map(x => x.textContent.trim())], ...all('[data-student-row]').map(row => [row.querySelector('.roll').textContent.trim(), row.querySelector('.student-name span').textContent.trim(), ...Array.from(row.querySelectorAll('.cell')).map(c => c.checked ? 'Yes' : 'No')])];
   const csv = '\uFEFF' + rows.map(row => row.map(v => '"' + String(v).replaceAll('"', '""') + '"').join(',')).join('\r\n');
   const url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'})), a = document.createElement('a');
   a.href = url; a.download = 'student-subjects.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); return;
  }
  all('.cell').forEach(c => c.checked = button.dataset.action === 'select'); update();
  root.querySelector('#saveStatus').textContent = 'Unsaved changes · Press Save to apply';
 });
 update();
 window.addEventListener('sl:live-updated', update);
})();
