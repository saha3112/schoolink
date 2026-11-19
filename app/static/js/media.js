/* Media library pop-up.
   Tabs:  Gallery (first)  |  Upload.   Gallery = 10 items a page, remove -> Trash, restore, permanent delete (if allowed).
   Upload = drag & drop / browse, single or multiple; afterwards the new files are shown selected in the Gallery.
   The pop-up closes only with its ✕ button (or Esc) - never by clicking outside it.
   Forms use  <div data-media-picker data-name="media_ids" data-accept="any|image" data-multiple="1" data-max="6">  */
(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ALLOWED = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'zip'];
  const IMAGES = ['png', 'jpg', 'jpeg', 'gif', 'webp'];
  const MAX = 8 * 1024 * 1024;
  const toast = (t, m) => (window.slToast ? slToast(t, m) : console.log(t, m));
  const I = {
    img: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>',
    restore: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
    open: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14 21 3"/></svg>',
    up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4m-5 5 5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>',
    clip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 11-9 9a6 6 0 0 1-8.5-8.5l9-9a4 4 0 0 1 5.7 5.7l-9 9a2 2 0 0 1-2.8-2.8l8.3-8.3"/></svg>'
  };
  const extColor = e => ({ pdf: '#e64c67', doc: '#4a78e6', docx: '#4a78e6', xls: '#19a889', xlsx: '#19a889', ppt: '#e9a044', pptx: '#e9a044', zip: '#8a6ae6', csv: '#19a889', txt: '#6c7a96' }[e] || '#6c7a96');
  const jget = async url => { const r = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } }); if (!r.ok) throw new Error('Could not load the library (' + r.status + ').'); return r.json(); };
  const csrf = () => { const m = document.querySelector('meta[name=csrf]'); return m ? m.content : ''; };

  /* ------------------------------------------------------------------ file preview pop-up (same page, never a new tab)
     Closes only with the round ✕ (top-right corner, half outside the box) or Esc - not by clicking outside. */
  function preview(f) {
    const ext = (f.ext || (String(f.name || f.url).split('?')[0].split('.').pop() || '')).toLowerCase();
    const isImg = IMAGES.includes(ext), isPdf = ext === 'pdf' || ext === 'txt';
    const dl = f.dl || f.url + (f.url.includes('?') ? '&' : '?') + 'dl=1';
    const prev = document.activeElement;
    const w = document.createElement('div'); w.className = 'pv-modal';
    w.innerHTML = '<div class="pv-box" role="dialog" aria-modal="true" aria-label="' + esc(f.name || 'Preview') + '">' +
      '<button type="button" class="pv-x" data-x aria-label="Close" title="Close"></button>' +
      '<div class="pv-head"><b title="' + esc(f.name || '') + '">' + esc(f.name || 'Preview') + '</b><a class="btn sm" href="' + esc(dl) + '" download>Download</a></div>' +
      '<div class="pv-body">' + (isImg ? '<img src="' + esc(f.url) + '" alt="' + esc(f.name || '') + '">' : isPdf ? '<iframe src="' + esc(f.url) + '" title="' + esc(f.name || '') + '"></iframe>' :
        '<div class="pv-none"><div class="mp-ext" style="--c:' + extColor(ext) + '">' + I.file + '<b>' + esc((ext || 'file').toUpperCase()) + '</b></div><p>This file type cannot be shown here.</p><a class="btn primary" href="' + esc(dl) + '" download>Download file</a></div>') + '</div></div>';
    document.body.appendChild(w); document.body.classList.add('vm-open');
    const close = () => { document.removeEventListener('keydown', key, true); w.remove(); if (!document.querySelector('.sl-modal,.mp-modal,.pv-modal') && document.getElementById('viewer') && document.getElementById('viewer').hidden) document.body.classList.remove('vm-open'); if (prev && prev.focus) try { prev.focus(); } catch (e) {} };
    const key = e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
    document.addEventListener('keydown', key, true);
    w.querySelector('[data-x]').onclick = close; w.querySelector('[data-x]').focus({ preventScroll: true });
    return { close };
  }

  /* ------------------------------------------------------------------ the pop-up */
  function openLibrary(opts) {
    opts = Object.assign({ accept: 'any', multiple: true, max: 6, selected: [], manage: false, inline: null, per: 10, title: 'Media library', onInsert: null }, opts || {});
    const imageOnly = opts.accept === 'image';
    const sel = new Map(); (opts.selected || []).forEach(it => sel.set(it.id, it));
    const st = { tab: 'gallery', view: 'library', kind: imageOnly ? 'image' : 'all', q: '', page: 1, pages: 1, total: 0, lib: 0, trash: 0, admin: false, purge: false, items: [], fresh: new Set(), mode: opts.multiple ? 'multi' : 'single', queue: [], busy: false };
    const prev = document.activeElement;
    const wrap = document.createElement('div'); wrap.className = opts.inline ? 'mp-inline' : 'mp-modal';
    wrap.innerHTML =
      '<div class="mp-box" role="dialog" aria-modal="true" aria-label="' + esc(opts.title) + '">' +
      '<div class="mp-head"><h3>' + esc(opts.title) + '</h3>' +
      '<div class="mp-tabs" role="tablist"><button type="button" role="tab" data-tab="gallery" class="on">Gallery <em data-c="lib">0</em></button><button type="button" role="tab" data-tab="upload">Upload</button></div>' +
      (opts.inline ? '' : '<button type="button" class="modal-x" data-x aria-label="Close" title="Close"></button>') + '</div>' +
      '<div class="mp-body">' +
        '<section class="mp-pane" data-pane="gallery">' +
          '<div class="mp-bar"><div class="mp-seg" data-seg="view"><button type="button" data-v="library" class="on">Library</button><button type="button" data-v="trash">Trash <em data-c="trash">0</em></button></div>' +
          (imageOnly ? '' : '<div class="mp-seg" data-seg="kind"><button type="button" data-k="all" class="on">All</button><button type="button" data-k="image">Images</button><button type="button" data-k="file">Files</button></div>') +
          '<label class="mp-search"><input type="search" placeholder="Search by name…" maxlength="80" data-q></label>' +
          '<button type="button" class="btn sm" data-selpage>Select page</button></div>' +
          '<div class="mp-grid" data-grid></div><div class="mp-pager" data-pager></div>' +
        '</section>' +
        '<section class="mp-pane" data-pane="upload" hidden>' +
          '<div class="mp-bar"><div class="mp-seg" data-seg="mode"><button type="button" data-m="single"' + (opts.multiple ? '' : ' class="on"') + '>Single</button>' + (opts.multiple ? '<button type="button" data-m="multi" class="on">Multiple</button>' : '') + '</div>' +
          '<span class="mp-note">' + (imageOnly ? 'Images only · ' : '') + 'up to 8 MB each' + (opts.multiple ? '' : ' · one file') + '</span></div>' +
          '<div class="mp-drop" data-drop tabindex="0" role="button" aria-label="Choose files to upload"><div class="mp-drop-ic">' + I.up + '</div>' +
          '<b>Drag & drop ' + (imageOnly ? 'images' : 'files or images') + ' here</b><span>or <u>browse</u> from your computer</span>' +
          '<input type="file" data-file hidden ' + (opts.multiple ? 'multiple' : '') + ' accept="' + (imageOnly ? 'image/*' : ALLOWED.map(e => '.' + e).join(',')) + '"></div>' +
          '<div class="mp-queue" data-queue></div>' +
          '<div class="mp-upbar" data-upbar hidden><div class="mp-prog"><i data-prog></i></div><button type="button" class="btn primary" data-start>Upload</button></div>' +
        '</section>' +
      '</div>' +
      '<div class="mp-foot"><span class="mp-count" data-count>Nothing selected</span><span class="mp-foot-actions" data-actions></span></div>' +
      '</div>';
    if (opts.inline) { opts.inline.innerHTML = ''; opts.inline.appendChild(wrap); } else { document.body.appendChild(wrap); document.body.classList.add('vm-open'); }
    const $ = s => wrap.querySelector(s), $$ = s => Array.from(wrap.querySelectorAll(s));
    let pollT = null, pollLast = null, alive = true;

    const close = () => { alive = false; clearTimeout(pollT); document.removeEventListener('keydown', key, true); wrap.remove(); if (!document.querySelector('.sl-modal,.mp-modal') && document.getElementById('viewer') && document.getElementById('viewer').hidden) document.body.classList.remove('vm-open'); if (prev && prev.focus) try { prev.focus(); } catch (e) {} };
    const key = e => { if (e.key === 'Escape' && !document.querySelector('.sl-modal')) { e.stopPropagation(); close(); } };
    if (!opts.inline) document.addEventListener('keydown', key, true);
    if ($('[data-x]')) $('[data-x]').onclick = close;                 // the ONLY way to close with the mouse - no outside-click close

    /* -------- selection / footer */
    const selCount = () => sel.size;
    function renderFoot() {
      const n = selCount();
      $('[data-count]').innerHTML = n ? '<b>' + n + '</b> selected' + (opts.multiple && !opts.manage ? ' <small>(max ' + opts.max + ')</small>' : '') : (st.view === 'trash' ? 'Removed files stay here until you restore or delete them' : 'Nothing selected');
      const box = $('[data-actions]'); let h = '';
      if (n) h += '<button type="button" class="btn" data-clear>Clear</button>';
      if (st.tab === 'gallery' && st.view === 'library') {
        if (n) h += '<button type="button" class="btn danger" data-bulk="remove">' + I.trash + ' Remove</button>';
        if (!opts.manage) h += '<button type="button" class="btn primary" data-insert ' + (n ? '' : 'disabled') + '>Insert' + (n ? ' (' + n + ')' : '') + '</button>';
      } else if (st.tab === 'gallery' && st.view === 'trash') {
        if (n) h += '<button type="button" class="btn" data-bulk="restore">' + I.restore + ' Restore</button>';
        if (n && (st.admin || st.purge)) h += '<button type="button" class="btn danger-solid" data-bulk="purge">Delete permanently</button>';
      }
      box.innerHTML = h;
    }
    const setSel = (it, on) => {
      if (on) { if (!opts.multiple) sel.clear(); if (opts.multiple && sel.size >= opts.max && !opts.manage && !sel.has(it.id)) { toast('info', 'You can choose up to ' + opts.max + ' files here.'); return false; } sel.set(it.id, it); }
      else sel.delete(it.id);
      return true;
    };

    /* -------- gallery */
    function card(it) {
      const on = sel.has(it.id), isNew = st.fresh.has(it.id);
      const thumb = it.thumb ? '<img src="' + esc(it.thumb) + '" alt="" loading="lazy">' : '<div class="mp-ext" style="--c:' + extColor(it.ext) + '">' + I.file + '<b>' + esc(it.ext.toUpperCase()) + '</b></div>';
      const who = (st.admin && !it.mine && it.uploader) ? '<span class="mp-who" title="Uploaded by ' + esc(it.uploader) + '">' + esc(it.uploader) + '</span>' : '';
      const acts = st.view === 'trash'
        ? '<button type="button" class="mp-ia" data-act="restore" title="Restore">' + I.restore + '</button>' + ((st.admin || (st.purge && it.mine)) ? '<button type="button" class="mp-ia danger" data-act="purge" title="Delete permanently">' + I.trash + '</button>' : '')
        : '<button type="button" class="mp-ia" data-act="open" title="View">' + I.open + '</button><button type="button" class="mp-ia danger" data-act="remove" title="Remove (moves to Trash)">' + I.trash + '</button>';
      const canPurge = st.admin || (st.purge && it.mine);
      const bar = '<div class="mp-bar2">' + (st.view === 'trash'
        ? '<button type="button" class="btn sm" data-act="restore">' + I.restore + ' Restore</button>' + (canPurge ? '<button type="button" class="btn sm danger" data-act="purge">' + I.trash + ' Delete permanently</button>' : '')
        : '<button type="button" class="btn sm" data-act="open">' + I.open + ' View</button><button type="button" class="btn sm danger" data-act="remove">' + I.trash + ' Remove</button>') + '</div>';
      return '<div class="mp-card' + (on ? ' on' : '') + (isNew ? ' fresh' : '') + '" data-id="' + it.id + '" tabindex="0" role="checkbox" aria-checked="' + on + '" aria-label="' + esc(it.name) + '">' +
        '<div class="mp-thumb">' + thumb + '<span class="mp-check" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg></span>' +
        (isNew ? '<span class="mp-new">New</span>' : '') + '<div class="mp-acts">' + acts + '</div></div>' +
        '<div class="mp-meta"><b title="' + esc(it.name) + '">' + esc(it.name) + '</b><small>' + esc(it.size_h) + ' · ' + esc((st.view === 'trash' ? it.deleted : it.date) || '') + '</small>' + who + '</div>' + (opts.inline ? bar : '') + '</div>';
    }
    function renderGrid() {
      const g = $('[data-grid]');
      if (!st.items.length) {
        g.innerHTML = '<div class="mp-empty">' + (st.q ? 'No files match “' + esc(st.q) + '”.' : st.view === 'trash' ? 'Trash is empty.' : (imageOnly ? 'No images yet.' : 'No files yet.') + (st.view === 'library' ? ' <a href="#" data-goup>Upload some</a>.' : '')) + '</div>';
      } else g.innerHTML = st.items.map(card).join('');
      const p = $('[data-pager]');
      if (st.pages > 1) {
        let h = '<button type="button" data-p="' + (st.page - 1) + '" ' + (st.page <= 1 ? 'disabled' : '') + '>‹ Prev</button>';
        const a = Math.max(1, st.page - 2), b = Math.min(st.pages, st.page + 2);
        if (a > 1) h += '<button type="button" data-p="1">1</button>' + (a > 2 ? '<span>…</span>' : '');
        for (let i = a; i <= b; i++) h += '<button type="button" data-p="' + i + '"' + (i === st.page ? ' class="on"' : '') + '>' + i + '</button>';
        if (b < st.pages) h += (b < st.pages - 1 ? '<span>…</span>' : '') + '<button type="button" data-p="' + st.pages + '">' + st.pages + '</button>';
        h += '<button type="button" data-p="' + (st.page + 1) + '" ' + (st.page >= st.pages ? 'disabled' : '') + '>Next ›</button><small>' + st.total + ' item' + (st.total !== 1 ? 's' : '') + '</small>';
        p.innerHTML = h;
      } else p.innerHTML = st.total ? '<small>' + st.total + ' item' + (st.total !== 1 ? 's' : '') + '</small>' : '';
      $$('[data-c=lib]').forEach(e => e.textContent = st.lib); $$('[data-c=trash]').forEach(e => e.textContent = st.trash);
      renderFoot();
    }
    let loading = 0;
    async function load(keep) {
      const my = ++loading; const g = $('[data-grid]'); if (!keep) g.classList.add('busy');
      try {
        const d = await jget('/media/api/list?tab=' + st.view + '&kind=' + st.kind + '&q=' + encodeURIComponent(st.q) + '&page=' + st.page + '&per=' + opts.per);
        if (my !== loading || !alive) return;
        Object.assign(st, { items: d.items, page: d.page, pages: d.pages, total: d.total, lib: d.library, trash: d.trash, admin: d.admin, purge: d.staff_purge });
        renderGrid();
      } catch (e) { g.innerHTML = '<div class="mp-empty err">' + esc(e.message) + '</div>'; }
      g.classList.remove('busy');
    }

    /* -------- gallery events */
    wrap.addEventListener('click', async e => {
      const t = e.target;
      const tab = t.closest('[data-tab]'); if (tab) { switchTab(tab.dataset.tab); return; }
      const v = t.closest('[data-seg=view] button'); if (v) { st.view = v.dataset.v; st.page = 1; $$('[data-seg=view] button').forEach(b => b.classList.toggle('on', b === v)); sel.clear(); load(); return; }
      const k = t.closest('[data-seg=kind] button'); if (k) { st.kind = k.dataset.k; st.page = 1; $$('[data-seg=kind] button').forEach(b => b.classList.toggle('on', b === k)); load(); return; }
      const m = t.closest('[data-seg=mode] button'); if (m) { st.mode = m.dataset.m; $$('[data-seg=mode] button').forEach(b => b.classList.toggle('on', b === m)); const f = $('[data-file]'); f.multiple = opts.multiple && st.mode === 'multi'; if (st.mode === 'single' && st.queue.length > 1) { st.queue = st.queue.slice(0, 1); renderQueue(); } return; }
      const pg = t.closest('[data-p]'); if (pg && !pg.disabled) { st.page = parseInt(pg.dataset.p, 10); load(true); return; }
      if (t.closest('[data-goup]')) { e.preventDefault(); switchTab('upload'); return; }
      if (t.closest('[data-selpage]')) { st.items.forEach(it => setSel(it, true)); renderGrid(); return; }
      if (t.closest('[data-clear]')) { sel.clear(); renderGrid(); return; }
      const act = t.closest('[data-act]');
      if (act) { e.stopPropagation(); const id = parseInt(act.closest('.mp-card').dataset.id, 10);
        if (act.dataset.act === 'open') { const it = st.items.find(x => x.id === id); if (it) preview(it); return; }
        await doAction(act.dataset.act, [id]); return; }
      if (t.closest('a.mp-ia')) return;
      const bulk = t.closest('[data-bulk]'); if (bulk) { await doAction(bulk.dataset.bulk, Array.from(sel.keys())); return; }
      const ins = t.closest('[data-insert]'); if (ins && !ins.disabled) { const items = Array.from(sel.values()); if (opts.onInsert) opts.onInsert(items); close(); return; }
      const c = t.closest('.mp-card'); if (c) toggleCard(c);
    });
    wrap.addEventListener('keydown', e => { const c = e.target.closest && e.target.closest('.mp-card'); if (c && (e.key === ' ' || e.key === 'Enter') && e.target === c) { e.preventDefault(); toggleCard(c); } });
    wrap.addEventListener('dblclick', e => { const c = e.target.closest('.mp-card'); if (c && !opts.manage && !opts.multiple && st.view === 'library') { const it = st.items.find(x => x.id === parseInt(c.dataset.id, 10)); if (it && opts.onInsert) { opts.onInsert([it]); close(); } } });
    function toggleCard(c) { const id = parseInt(c.dataset.id, 10), it = st.items.find(x => x.id === id); if (!it) return; if (setSel(it, !sel.has(id))) renderGrid(); }
    let qt = null; $('[data-q]').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { st.q = e.target.value.trim(); st.page = 1; load(); }, 220); });

    async function doAction(action, ids) {
      if (!ids.length) return;
      const names = ids.map(id => { const it = st.items.find(x => x.id === id) || sel.get(id); return it ? it.name : null; }).filter(Boolean), n = ids.length, what = n > 1 ? n + ' files' : 'this file';
      const CF = {
        remove: { tone: 'warn', title: 'Move to Trash?', msg: 'Move ' + what + ' to Trash? You can restore ' + (n > 1 ? 'them' : 'it') + ' later from the Trash tab.', ok: 'Move to Trash', danger: true },
        restore: { tone: 'restore', title: 'Restore ' + (n > 1 ? 'files' : 'file') + '?', msg: 'Put ' + what + ' back in the Library?', ok: 'Restore', danger: false },
        purge: { tone: 'danger', title: 'Delete permanently?', msg: 'Delete ' + what + ' permanently? This cannot be undone and the ' + (n > 1 ? 'files are' : 'file is') + ' gone for good.', ok: 'Delete permanently', danger: true }
      }[action];
      if (CF) { const ok = await slConfirm(CF.msg, { tone: CF.tone, title: CF.title, ok: CF.ok, danger: CF.danger, items: names }); if (!ok) return; }
      try {
        const r = await fetch('/media/api/action', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() }, body: JSON.stringify({ action, ids }) });
        const d = await r.json();
        toast(d.ok ? 'success' : 'error', d.message || (d.ok ? 'Done.' : 'That did not work.'));
        if (d.ok) { ids.forEach(id => sel.delete(id)); if (action === 'remove') (opts.onRemoved || (() => {}))(ids); await load(true); }
      } catch (e) { toast('error', 'Could not reach the server. Please try again.'); }
    }

    /* -------- tabs */
    function switchTab(name) {
      st.tab = name;
      $$('[data-tab]').forEach(b => { b.classList.toggle('on', b.dataset.tab === name); b.setAttribute('aria-selected', b.dataset.tab === name); });
      $$('.mp-pane').forEach(p => p.hidden = p.dataset.pane !== name);
      if (name === 'gallery') load(true); else renderFoot();
    }

    /* -------- upload */
    const drop = $('[data-drop]'), fileIn = $('[data-file]');
    const okFile = f => {
      const ext = (f.name.split('.').pop() || '').toLowerCase();
      if (ext === 'csv') return f.name + ': CSV files are not kept in the library - use “Import CSV” on the data page instead.';
      if (!ALLOWED.includes(ext)) return f.name + ': .' + ext + ' files are not allowed.';
      if (imageOnly && !IMAGES.includes(ext)) return f.name + ': only images can be used here.';
      if (f.size > MAX) return f.name + ': larger than 8 MB.';
      if (!f.size) return f.name + ': the file is empty.';
      return null;
    };
    function addFiles(list) {
      let files = Array.from(list);
      const single = !opts.multiple || st.mode === 'single';
      if (single && files.length > 1) { toast('info', 'Single mode: only the first file was taken.'); files = files.slice(0, 1); }
      if (single) st.queue = [];
      for (const f of files) {
        const err = okFile(f); if (err) { toast('error', err); continue; }
        if (!st.queue.some(q => q.name === f.name && q.size === f.size)) st.queue.push(f);
      }
      if (st.queue.length > 20) { st.queue = st.queue.slice(0, 20); toast('info', 'At most 20 files can be uploaded at a time.'); }
      renderQueue();
    }
    function renderQueue() {
      const q = $('[data-queue]');
      q.innerHTML = st.queue.map((f, i) => {
        const ext = (f.name.split('.').pop() || '').toLowerCase(), isImg = IMAGES.includes(ext);
        return '<div class="mp-q"><span class="mp-q-ic" style="--c:' + extColor(ext) + '">' + (isImg ? I.img : I.file) + '</span><span class="mp-q-n"><b>' + esc(f.name) + '</b><small>' + (f.size / 1024 < 1024 ? Math.max(1, Math.round(f.size / 1024)) + ' KB' : (f.size / 1048576).toFixed(1) + ' MB') + '</small></span><button type="button" class="modal-x mini" data-rm="' + i + '" aria-label="Remove from list" title="Remove from list"></button></div>';
      }).join('');
      $('[data-upbar]').hidden = !st.queue.length;
      const b = $('[data-start]'); b.disabled = st.busy; b.textContent = 'Upload ' + st.queue.length + ' ' + (st.queue.length === 1 ? 'file' : 'files');
      $('[data-prog]').style.width = '0%';
    }
    wrap.addEventListener('click', e => { const r = e.target.closest('[data-rm]'); if (r) { st.queue.splice(parseInt(r.dataset.rm, 10), 1); renderQueue(); } });
    drop.addEventListener('click', () => fileIn.click());
    drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileIn.click(); } });
    fileIn.addEventListener('change', () => { addFiles(fileIn.files); fileIn.value = ''; });
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => { if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files); });
    wrap.addEventListener('dragover', e => e.preventDefault()); wrap.addEventListener('drop', e => e.preventDefault());   // a missed drop must not navigate away
    $('[data-start]').addEventListener('click', () => {
      if (!st.queue.length || st.busy) return;
      st.busy = true; const fd = new FormData(); st.queue.forEach(f => fd.append('files', f));
      const x = new XMLHttpRequest(); x.open('POST', '/media/api/upload'); x.setRequestHeader('X-CSRF-Token', csrf());
      const btn = $('[data-start]'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Uploading…';
      x.upload.onprogress = e => { if (e.lengthComputable) $('[data-prog]').style.width = Math.round(e.loaded * 100 / e.total) + '%'; };
      x.onload = () => {
        st.busy = false; let d = {}; try { d = JSON.parse(x.responseText); } catch (e) { }
        (d.errors || []).forEach(m => toast('error', m));
        if (d.items && d.items.length) {
          toast('success', d.message || 'Uploaded.');
          if (!opts.multiple || st.mode === 'single') sel.clear();
          d.items.forEach(it => { st.fresh.add(it.id); if (!opts.manage) setSel(it, true); });
          st.queue = []; renderQueue(); st.view = 'library'; st.page = 1; st.q = ''; $('[data-q]').value = '';
          $$('[data-seg=view] button').forEach(b => b.classList.toggle('on', b.dataset.v === 'library'));
          switchTab('gallery');                                      // new files appear in the Gallery, already ticked
        } else { if (!(d.errors || []).length) toast('error', d.error || 'Upload failed. Please try again.'); renderQueue(); }
      };
      x.onerror = () => { st.busy = false; toast('error', 'Upload failed - check your connection and try again.'); renderQueue(); };
      x.send(fd);
    });

    /* -------- live: files added / removed by others show up while the pop-up is open */
    async function poll() {
      if (!alive) return;
      try {
        if (pollLast === null) pollLast = (await jget('/live/poll?since=-1')).last;
        const d = await jget('/live/poll?since=' + pollLast + '&topics=media');
        if (d.events && d.events.length && st.tab === 'gallery' && !st.busy) load(true);
        pollLast = d.last || pollLast;
      } catch (e) { }
      pollT = setTimeout(poll, 3500);
    }
    pollT = setTimeout(poll, 3500);
    renderFoot(); load();
    return { close, selected: () => Array.from(sel.values()) };
  }
  window.SLMedia = { open: openLibrary, preview };

  /* ------------------------------------------------------------------ form fields: <div data-media-picker> */
  function initPicker(box) {
    if (box.dataset.ready) return; box.dataset.ready = '1';
    const name = box.dataset.name || 'media_ids', accept = box.dataset.accept || 'any', multiple = box.dataset.multiple !== '0', max = parseInt(box.dataset.max || '6', 10);
    let items = [];
    const holder = box.querySelector('[data-mp-chosen]') || box.appendChild(Object.assign(document.createElement('div'), { className: 'mp-chosen' }));
    const render = () => {
      holder.innerHTML = items.map(it => '<span class="mp-chip" data-id="' + it.id + '">' + (it.thumb ? '<img src="' + esc(it.thumb) + '" alt="">' : '<i style="--c:' + extColor(it.ext) + '">' + esc((it.ext || 'file').toUpperCase()) + '</i>') +
        '<b title="' + esc(it.name) + '">' + esc(it.name) + '</b><button type="button" class="modal-x mini" aria-label="Remove ' + esc(it.name) + '" title="Remove"></button><input type="hidden" name="' + esc(name) + '" value="' + it.id + '"></span>').join('');
      const b = box.querySelector('[data-mp-open]'); if (b) b.innerHTML = I.clip + ' ' + (items.length ? 'Change selection (' + items.length + ')' : (box.dataset.button || (multiple ? 'Choose from library or upload' : 'Choose or upload')));
      box.dispatchEvent(new CustomEvent('mp:change', { bubbles: true, detail: { items } }));
    };
    box.addEventListener('click', e => {
      if (e.target.closest('[data-mp-open]')) {
        openLibrary({ accept, multiple, max, selected: items, title: box.dataset.title || (accept === 'image' ? 'Choose images' : 'Choose files'), onInsert: sel => { items = sel; render(); } });
      }
      const pv = e.target.closest('.mp-chip img, .mp-chip i, .mp-chip b');
      if (pv) { const it = items.find(i => i.id === parseInt(pv.closest('.mp-chip').dataset.id, 10)); if (it) preview(it); return; }
      const x = e.target.closest('.mp-chip .modal-x'); if (x) { const id = parseInt(x.closest('.mp-chip').dataset.id, 10); items = items.filter(i => i.id !== id); render(); }
    });
    box.slMediaItems = () => items;
    render();
  }
  const init = () => document.querySelectorAll('[data-media-picker]').forEach(initPicker);
  document.addEventListener('DOMContentLoaded', init); if (document.readyState !== 'loading') init();
  window.SLMedia.init = init;

  /* the Media library page shows the gallery right on the page (12 a page, 4 per row) */
  const pg = () => { const h = document.querySelector('[data-library-page]'); if (h && !h.dataset.ready) { h.dataset.ready = '1'; openLibrary({ inline: h, manage: true, multiple: true, max: 500, per: 12, title: 'Media library' }); } };
  document.addEventListener('DOMContentLoaded', pg); if (document.readyState !== 'loading') pg();
  /* "Media library" button elsewhere: browse / manage everything (no Insert) */
  document.addEventListener('click', e => { const b = e.target.closest('[data-open-library]'); if (b) openLibrary({ manage: true, multiple: true, max: 500, title: 'Media library' }); });

  /* links to uploaded files/images elsewhere (announcements, albums, classwork...): same preview pop-up */
  document.addEventListener('click', e => {
    const a = e.target.closest('a[data-popup]'); if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
    const url = a.dataset.popup || a.href, ext = (String((a.dataset.title || '') || url).split('?')[0].split('.').pop() || '').toLowerCase();
    if (!(ALLOWED.includes(ext) || /\/media\/f\//.test(url))) return;
    e.preventDefault(); e.stopImmediatePropagation();
    preview({ url, name: a.dataset.title || '', ext: ALLOWED.includes(ext) ? ext : '', dl: url + (url.includes('?') ? '&' : '?') + (/\/media\/f\//.test(url) ? 'dl=1' : 'download=1') });
  }, true);
})();
