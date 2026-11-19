(function () {
  const root = document.documentElement, body = document.body;
  const isMobile = () => window.innerWidth <= 992;
  document.getElementById('sbToggle').addEventListener('click', function () {
    if (isMobile()) { body.classList.toggle('sb-open'); return; }
    const c = root.classList.toggle('sb-collapsed');
    try { localStorage.setItem('sb-collapsed', c ? '1' : '0'); } catch (e) {}
  });
  document.getElementById('sbBackdrop').addEventListener('click', () => body.classList.remove('sb-open'));
  document.getElementById('sidebar').addEventListener('click', e => {
    const b = e.target.closest('.sb-parent'); if (!b) return;
    if (root.classList.contains('sb-collapsed') && !isMobile()) { root.classList.remove('sb-collapsed'); try { localStorage.setItem('sb-collapsed', '0'); } catch (x) {} }
    b.parentElement.classList.toggle('open');
  });
  // profile dropdown
  const pb = document.getElementById('profileBtn'), pm = document.getElementById('profileMenu');
  pb.addEventListener('click', e => { e.stopPropagation(); const s = pm.classList.toggle('show'); pb.setAttribute('aria-expanded', s); });
  document.addEventListener('click', e => { if (!pm.contains(e.target)) { pm.classList.remove('show'); pb.setAttribute('aria-expanded', 'false'); } });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { pm.classList.remove('show'); body.classList.remove('sb-open'); } });
})();

/* small helpers used by pages */
window.fillSelect = function (sel, items, valKey, textKey, placeholder) {
  sel.innerHTML = '';
  if (placeholder !== null) { const o = document.createElement('option'); o.value = ''; o.textContent = placeholder || 'Select'; sel.appendChild(o); }
  items.forEach(i => { const o = document.createElement('option'); o.value = i[valKey]; o.textContent = i[textKey]; sel.appendChild(o); });
};
/* Audience picker for announcement / gallery style forms:
   whole school <-> class / section. The section list follows the class, stays disabled until a class is chosen, is pre-filled when
   there is only one choice, and is required for teachers (an administrator may leave it on "all sections"). */
window.audiencePicker = function (o) {
  const aud = o.aud, cls = o.cls, sec = o.sec, admin = !!o.admin, all = o.allLabel || 'All sections';
  const fire = el => el.dispatchEvent(new Event('change', { bubbles: true }));
  const box = el => el.closest('label') || el.parentElement;
  const reset = (text, disabled) => { fillSelect(sec, [], 'sectionId', 'section_name', text); sec.disabled = disabled; sec.required = false; fire(sec); };
  let seq = 0;
  const load = () => {
    if (!cls.value) { reset('Choose a class first', true); return; }
    const my = ++seq; reset('Loading…', true);
    getJSON('/school/api/sections?class_id=' + encodeURIComponent(cls.value)).then(r => {
      if (my !== seq) return;
      fillSelect(sec, r, 'sectionId', 'section_name', admin ? all : 'Select section');
      sec.disabled = false; sec.required = !admin && !!r.length;
      if (!r.length) reset('No sections', true);
      else if (!admin && r.length === 1) sec.value = String(r[0].sectionId);
      fire(sec);
    }).catch(() => reset('Could not load sections', true));
  };
  const sync = () => {
    const school = aud ? aud.value === 'school' : false;
    [cls, sec].forEach(el => { box(el).style.display = school ? 'none' : ''; el.disabled = school || (el === sec && el.disabled); });
    cls.required = !school && (aud ? true : !admin);
    if (school) { sec.required = false; cls.value = ''; fire(cls); return; }
    cls.disabled = false;
    const real = Array.from(cls.options).filter(x => x.value);
    if (!cls.value && real.length === 1 && (aud || !admin)) cls.value = real[0].value;      // a single class is chosen for you
    fire(cls); load();
  };
  cls.addEventListener('change', load);
  if (aud) aud.addEventListener('change', sync);
  sync();
};
window.getJSON = (url) => fetch(url, { headers: { 'X-Requested-With': 'fetch' } }).then(r => r.json());
window.confirmForm = (msg) => confirm(msg || 'Are you sure?');   // legacy; forms using confirm() are upgraded to the styled dialog below

/* ---- checklist (multi select) helpers ---- */
window.renderChecklist = function (box, items, name, valKey, textKey, checkedAll) {
  box.innerHTML = '';
  if (!items.length) { box.innerHTML = '<div class="muted" style="padding:6px">Nothing available</div>'; return; }
  items.forEach(i => {
    const l = document.createElement('label');
    l.innerHTML = '<input type="checkbox" name="' + name + '" value="' + i[valKey] + '"' + (checkedAll ? ' checked' : '') + '> <span></span>';
    l.querySelector('span').textContent = i[textKey];
    box.appendChild(l);
  });
};
window.selectedValues = (box) => Array.from(box.querySelectorAll('input:checked')).map(i => i.value);
/* class -> sections(checklist) -> subjects(checklist) cascade used by mapping pages */
window.bindCascade = function (o) {
  const cls = document.querySelector(o.cls), secBox = document.querySelector(o.sec), subBox = o.sub ? document.querySelector(o.sub) : null;
  const loadSubjects = () => {
    if (!subBox) return;
    const ids = selectedValues(secBox);
    if (!ids.length) { renderChecklist(subBox, [], 'subject_id', 'subjectId', 'subject_name'); return; }
    getJSON('/admin/api/subjects?class_id=' + cls.value + '&' + ids.map(i => 'section_id=' + i).join('&'))
      .then(r => renderChecklist(subBox, r, 'subject_id', 'subjectId', 'subject_name'));
  };
  cls.addEventListener('change', () => {
    renderChecklist(secBox, [], 'section_id', 'sectionId', 'section_name'); if (subBox) renderChecklist(subBox, [], 'subject_id', 'subjectId', 'subject_name');
    if (!cls.value) return;
    getJSON('/admin/api/sections?class_id=' + cls.value + (o.mapped ? '&mapped=1' : '')).then(r => renderChecklist(secBox, r, 'section_id', 'sectionId', 'section_name'));
  });
  secBox.addEventListener('change', loadSubjects);
  document.querySelectorAll('[data-toggle-all]').forEach(b => b.addEventListener('click', e => {
    e.preventDefault(); const box = document.querySelector(b.dataset.toggleAll); const all = box.querySelectorAll('input[type=checkbox]');
    const on = Array.from(all).some(i => !i.checked); all.forEach(i => i.checked = on); box.dispatchEvent(new Event('change', { bubbles: true }));
  }));
};

/* CSRF: add the token to every POST form (also called again after a soft page update) */
window.slAddCsrf = function (root) {
  const t = document.querySelector('meta[name=csrf]'); if (!t) return;
  (root || document).querySelectorAll('form').forEach(f => {
    if ((f.method || '').toLowerCase() !== 'post' || f.querySelector('input[name=csrf_token]')) return;
    const i = document.createElement('input'); i.type = 'hidden'; i.name = 'csrf_token'; i.value = t.content; f.appendChild(i);
  });
};
window.slAddCsrf(document);

/* ---- document viewer popup: <a data-popup="/url" data-title="..."> ---- */
(function () {
  const vm = document.getElementById('viewer'); if (!vm) return;
  const frame = document.getElementById('vmFrame'), body = vm.querySelector('.vm-body'), pct = document.getElementById('vmPct');
  let zoom = 1, fitMode = true, current = null;
  const doc = () => { try { return frame.contentDocument; } catch (e) { return null; } };
  const apply = () => { const d = doc(); if (!d || !d.documentElement) return; d.documentElement.style.zoom = zoom; pct.textContent = Math.round(zoom * 100) + '%'; };
  const fit = () => {
    const d = doc(); if (!d || !d.documentElement) return;
    d.documentElement.style.zoom = 1;
    const w = Math.max(d.documentElement.scrollWidth, d.body ? d.body.scrollWidth : 0, 1);
    zoom = Math.min(1, Math.max(0.1, (frame.clientWidth - 2) / w)); fitMode = true; apply();
  };
  const open = (url, title) => {
    current = url; body.classList.remove('loaded'); frame.removeAttribute('srcdoc'); frame.src = url;
    document.getElementById('vmTitle').textContent = title || 'Preview';
    const sep = url.includes('?') ? '&' : '?';
    document.getElementById('vmPdf').href = url + sep + 'pdf=1&dl=1';
    vm.hidden = false; document.body.classList.add('vm-open'); document.getElementById('vmClose').focus();
  };
  const close = () => { vm.hidden = true; document.body.classList.remove('vm-open'); frame.src = 'about:blank'; };
  frame.addEventListener('load', () => { if (frame.src === 'about:blank' || vm.hidden) return; body.classList.add('loaded'); fit(); });
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-popup]'); if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault(); open(a.dataset.popup || a.href, a.dataset.title || a.textContent.trim());
  });
  document.getElementById('vmClose').addEventListener('click', close);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !vm.hidden) close(); });
  document.getElementById('vmIn').addEventListener('click', () => { zoom = Math.min(3, zoom * 1.2); fitMode = false; apply(); });
  document.getElementById('vmOut').addEventListener('click', () => { zoom = Math.max(0.1, zoom / 1.2); fitMode = false; apply(); });
  document.getElementById('vmFit').addEventListener('click', fit);
  window.addEventListener('resize', () => { if (!vm.hidden && fitMode) fit(); });
  document.getElementById('vmPrint').addEventListener('click', () => {
    const d = doc(); if (!d) return; const z = zoom; d.documentElement.style.zoom = 1;
    frame.contentWindow.focus(); frame.contentWindow.print(); setTimeout(() => { zoom = z; apply(); }, 600);
  });
})();

/* ---- in-app downloads: <a data-download href="...">  (no new tab; shows progress, saves the file) ---- */
document.addEventListener('click', async e => {
  const a = e.target.closest('[data-download]'); if (!a) return;
  e.preventDefault(); if (a.classList.contains('busy') || !a.getAttribute('href') || a.getAttribute('href') === '#') return;
  const label = a.innerHTML; a.classList.add('busy'); a.setAttribute('aria-busy', 'true'); a.innerHTML = '<span class="spin"></span> Preparing PDF…';
  try {
    const r = await fetch(a.href, { credentials: 'same-origin' });
    if (!r.ok) throw new Error('The server could not create the file (' + r.status + ').');
    const blob = await r.blob();
    const m = /filename="?([^";]+)"?/i.exec(r.headers.get('Content-Disposition') || '');
    const l = document.createElement('a'); l.href = URL.createObjectURL(blob); l.download = m ? m[1] : 'download.pdf';
    document.body.appendChild(l); l.click(); l.remove(); setTimeout(() => URL.revokeObjectURL(l.href), 4000);
  } catch (err) { slAlert(err.message || 'Download failed.'); }
  finally { a.classList.remove('busy'); a.removeAttribute('aria-busy'); a.innerHTML = label; }
});

/* ---- bulk ZIP jobs: <button data-bulk data-kind="cards|tab|wtd|sheets" data-class data-section data-exam> ---- */
(function () {
  const meta = document.querySelector('meta[name=csrf]'); if (!meta) return;
  const box = document.createElement('div'); box.className = 'bulk-toast'; box.hidden = true; document.body.appendChild(box);
  let timer = null;
  const bar = (d, t) => '<div class="progress"><i style="width:' + (t ? Math.round(d * 100 / t) : 0) + '%"></i></div>';
  const hdr = (t) => '<div class="bt-head"><b>' + t + '</b><button type="button" class="bt-x modal-x" aria-label="Hide" title="Hide"></button></div>';
  const wire = () => { const x = box.querySelector('.bt-x'); if (x) x.onclick = () => { box.hidden = true; clearInterval(timer); }; };
  async function poll(id, title) {
    const r = await fetch('/reports/bulk/' + id + '/status'); if (!r.ok) { clearInterval(timer); return; } const j = await r.json();
    if (j.status === 'running' || j.status === 'queued') {
      box.innerHTML = hdr(title) + '<div class="muted">' + (j.status === 'queued' ? 'Waiting for another download to finish…' : 'Preparing ' + j.done + ' of ' + j.total) + '</div>' + bar(j.done, j.total) +
        '<div class="muted bt-cur">' + (j.current || '') + '</div><button class="btn sm" id="btCancel">Cancel</button>'; wire();
      box.querySelector('#btCancel').onclick = () => fetch('/reports/bulk/' + id + '/cancel', { method: 'POST', headers: { 'X-CSRF-Token': meta.content } });
    } else {
      clearInterval(timer);
      box.innerHTML = hdr(title) + (j.status === 'error' ? '<div class="alert alert-error">' + j.error + '</div>' :
        '<div class="alert alert-success" style="margin:8px 0">' + (j.status === 'cancelled' ? 'Cancelled — partial ZIP ready. ' : 'Ready. ') + j.done + ' file(s)' + (j.skipped ? ', ' + j.skipped + ' skipped (listed inside the ZIP)' : '') + '.</div>' +
        '<a class="btn primary" href="/reports/bulk/' + id + '/download">Download ZIP</a>'); wire();
    }
  }
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-bulk]'); if (!b) return; e.preventDefault();
    const fd = new FormData(); fd.append('kind', b.dataset.kind); fd.append('class_id', b.dataset.class || ''); fd.append('section_id', b.dataset.section || '');
    if (b.dataset.exam) fd.append('exam_id', b.dataset.exam);
    if (b.hasAttribute('data-exam-boxes')) b.closest('.card').querySelectorAll('.exam:checked').forEach(c => fd.append('exam_id', c.value));
    box.hidden = false; box.innerHTML = hdr('Starting…') + '<div class="muted">Please wait…</div>'; wire();
    const r = await fetch('/reports/bulk/start', { method: 'POST', body: fd, headers: { 'X-CSRF-Token': meta.content } }); const j = await r.json();
    if (!r.ok) { box.innerHTML = hdr('Download') + '<div class="alert alert-error">' + (j.error || 'Could not start.') + '</div>'; wire(); return; }
    const title = { cards: 'Report cards ZIP', cardbook: 'Section PDFs ZIP', tab: 'Tabulation sheets ZIP', wtd: 'Weighted average ZIP', sheets: 'Sheets ZIP' }[b.dataset.kind];
    clearInterval(timer); poll(j.id, title); timer = setInterval(() => poll(j.id, title), 1500);
  });
})();

/* ---- Section-wise subject picker: one card per section, subjects ticked inside it ---- */
window.sectionSubjects = function (o) {
  const cls = document.querySelector(o.cls), box = document.querySelector(o.box);
  const need = [cls].concat((o.need || []).map(s => document.querySelector(s)).filter(Boolean));       // every one of these must be chosen first
  const M = o.marks ? { def: document.querySelector(o.marks.def), exam: document.querySelector(o.marks.exam), sub: document.querySelector(o.marks.sub) } : null;
  const draw = data => {
    if (!data.length) { box.innerHTML = '<div class="ss-empty">This class has no sections yet.</div>'; return; }
    box.innerHTML = '<div class="ss-tools"><button type="button" class="btn sm" data-all="1">Tick everything</button><button type="button" class="btn sm" data-all="0">Clear</button><span class="muted ss-count"></span></div><div class="ss-grid"></div>';
    const grid = box.querySelector('.ss-grid');
    data.forEach(sec => {
      const card = document.createElement('div'); card.className = 'ss-card';
      const usable = sec.subjects.filter(s => !(o.all && s.mapped));
      card.innerHTML = '<div class="ss-head"><label class="ss-all"><input type="checkbox" class="sec-all"> <b></b></label><button type="button" class="ss-copy" title="Copy this section ticks to every section">copy to all</button></div><div class="ss-list"></div>';
      card.querySelector('b').textContent = 'Section ' + sec.section_name;
      const list = card.querySelector('.ss-list');
      if (!sec.subjects.length) list.innerHTML = '<div class="muted" style="padding:8px">No subjects mapped to this section.</div>';
      sec.subjects.forEach(s => {
        const l = document.createElement('label'); const dis = o.all && s.mapped;
        l.innerHTML = '<input type="checkbox" name="pair" value="' + sec.sectionId + ':' + s.subjectId + '"' + (dis ? ' disabled' : '') + '> <span></span>' + (dis ? ' <em>already mapped</em>' : '') +
          (M ? '<input type="number" class="ss-fm" min="0" step="1" inputmode="numeric" name="fm_' + sec.sectionId + '_' + s.subjectId + '" placeholder="marks" disabled hidden title="Full marks for this subject">' : '');
        l.querySelector('span').textContent = s.subject_name; if (dis) l.classList.add('is-mapped');
        if (M) { const fm = l.querySelector('.ss-fm'); if (s.fullmarks != null) { fm.dataset.cur = s.fullmarks; l.insertAdjacentHTML('beforeend', ''); l.querySelector('span').insertAdjacentHTML('afterend', ' <em class="ss-now">now ' + String(s.fullmarks).replace(/[<>&]/g, '') + '</em>'); } }
        list.appendChild(l);
      });
      card.querySelector('.sec-all').addEventListener('change', e => { card.querySelectorAll('.ss-list input:not(:disabled)').forEach(i => i.checked = e.target.checked); count(); });
      card.querySelector('.ss-copy').addEventListener('click', () => {
        const names = new Set(Array.from(card.querySelectorAll('.ss-list input:checked')).map(i => i.value.split(':')[1]));
        grid.querySelectorAll('.ss-card').forEach(c => c.querySelectorAll('.ss-list input:not(:disabled)').forEach(i => i.checked = names.has(i.value.split(':')[1]))); count();
      });
      if (!usable.length) card.querySelector('.sec-all').disabled = true;
      grid.appendChild(card);
    });
    box.querySelectorAll('[data-all]').forEach(b => b.addEventListener('click', () => { box.querySelectorAll('.ss-list input:not(:disabled), .sec-all').forEach(i => i.checked = b.dataset.all === '1'); count(); }));
    grid.addEventListener('change', e => { if (M && e.target.name === 'pair') syncFm(e.target); count(); });
    if (M) { grid.addEventListener('input', e => { if (e.target.classList.contains('ss-fm')) e.target.dataset.touched = '1'; }); }
    count();
  };
  // full marks: a ticked subject shows its own box, pre-filled with what is saved, else with the default above; typing in it overrides
  const syncFm = cb => {
    const fm = cb.closest('label').querySelector('.ss-fm'); if (!fm) return;
    fm.hidden = !cb.checked; fm.disabled = !cb.checked; fm.required = cb.checked;
    if (cb.checked && !fm.value) { fm.value = fm.dataset.cur != null ? fm.dataset.cur : (M.def && M.def.value) || ''; if (fm.dataset.cur == null) fm.dataset.fromDefault = '1'; }
    if (cb.checked && !fm.value) fm.focus();
  };
  const count = () => { const n = box.querySelectorAll('.ss-list input:checked').length, c = box.querySelector('.ss-count'); if (c) c.textContent = n + ' selected'; };
  const load = () => {
    if (!need.every(el => el.value)) { box.innerHTML = '<div class="ss-empty">' + (o.hint || 'Choose a class to see its sections.') + '</div>'; return; }
    box.innerHTML = '<div class="ss-empty">Loading…</div>';
    getJSON('/admin/api/section_subjects?class_id=' + cls.value + (o.all ? '&all=1' : '') + (M && M.exam && M.sub ? '&exam_id=' + M.exam.value + '&subtype_id=' + M.sub.value : '')).then(draw);
  };
  need.forEach(el => el.addEventListener('change', load));
  if (M && M.def) M.def.addEventListener('input', () => box.querySelectorAll('.ss-fm[data-from-default="1"]:not([data-touched])').forEach(i => { if (!i.disabled) i.value = M.def.value; }));
  // "tick everything / a whole section" use programmatic ticks -> make the boxes follow
  box.addEventListener('click', () => { if (M) setTimeout(() => box.querySelectorAll('input[name=pair]').forEach(syncFm), 0); });
  load();
};

/* ---- notification bell ---- */
(function () {
  const btn = document.getElementById('bellBtn'); if (!btn) return;
  const menu = document.getElementById('bellMenu'), list = document.getElementById('bellList'), badge = document.getElementById('bellBadge'), clear = document.getElementById('bellClear');
  const token = (document.querySelector('meta[name=csrf]') || {}).content || '';
  const post = (url, body) => fetch(url, { method: 'POST', headers: { 'X-CSRF-Token': token, 'Content-Type': 'application/x-www-form-urlencoded' }, body: body || '' });
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const setBadge = n => { badge.hidden = !n; badge.textContent = n > 99 ? '99+' : n; };
  async function load() {
    const j = await (await fetch('/notifications/')).json(); setBadge(j.unread); clear.hidden = !j.items.length;
    list.innerHTML = j.items.length ? j.items.map(n => '<div class="bm-item ' + (n.is_read ? '' : 'unread') + '" data-id="' + n.id + '" data-link="' + esc(n.link || '') + '"><span class="bm-dot"></span><div class="bm-main"><div class="bm-title">' + esc(n.title) + '</div>' +
      (n.body ? '<div class="bm-body">' + esc(n.body) + '</div>' : '') + '<div class="bm-time">' + esc(n.at) + '</div></div><button class="bm-x" title="Remove" aria-label="Remove">×</button></div>').join('') : '<div class="bm-empty">You are all caught up 🎉</div>';
  }
  btn.addEventListener('click', e => {
    e.stopPropagation(); const s = menu.classList.toggle('show'); btn.setAttribute('aria-expanded', s);
    document.getElementById('profileMenu').classList.remove('show');
    if (s) load();
  });
  document.addEventListener('click', e => { if (!document.getElementById('bell').contains(e.target)) menu.classList.remove('show'); });
  document.getElementById('profileBtn').addEventListener('click', () => menu.classList.remove('show'));
  list.addEventListener('click', async e => {
    const item = e.target.closest('.bm-item'); if (!item) return; const id = item.dataset.id;
    if (e.target.closest('.bm-x')) { e.stopPropagation(); await post('/notifications/' + id + '/delete'); item.remove(); if (!list.querySelector('.bm-item')) { list.innerHTML = '<div class="bm-empty">You are all caught up 🎉</div>'; clear.hidden = true; } refreshCount(); return; }
    await post('/notifications/read', 'id=' + id); if (item.dataset.link) location.href = item.dataset.link; else { item.classList.remove('unread'); refreshCount(); }
  });
  clear.addEventListener('click', async () => { if (!(await slConfirm('Remove all notifications?'))) return; await post('/notifications/clear'); list.innerHTML = '<div class="bm-empty">You are all caught up 🎉</div>'; clear.hidden = true; setBadge(0); });
  async function refreshCount() { try { setBadge((await (await fetch('/notifications/count')).json()).unread); } catch (e) {} }
  refreshCount(); setInterval(() => { if (!document.hidden) refreshCount(); }, 60000);
  window.addEventListener('sl:live-events', e => { if (e.detail.some(x => ['school', 'leave', 'reports', 'marks', 'classteacher', 'parentpanel', 'admin', 'students'].includes(x.t))) { refreshCount(); if (menu.classList.contains('show')) load(); } });
})();

/* ---- theme toggle + quick-navigation palette (Ctrl/⌘ K) ---- */
(function () {
  const root = document.documentElement;
  const lbl = document.getElementById('themeLbl');
  const sync = () => { if (lbl) lbl.textContent = 'Switch to ' + (root.dataset.theme === 'dark' ? 'light' : 'dark') + ' mode'; };
  const toggle = () => { const n = root.dataset.theme === 'dark' ? 'light' : 'dark'; root.dataset.theme = n;
    try { localStorage.setItem('sl-theme', n); } catch (e) {} sync(); };
  ['themeBtn', 'themeBtn2'].forEach(id => { const el = document.getElementById(id); if (el) el.addEventListener('click', toggle); });
  sync();
})();

/* ---- top bar live search ---- */
(function () {
  const box = document.getElementById('ts'); if (!box) return;
  const inp = document.getElementById('tsInput'), panel = document.getElementById('tsPanel'), clr = document.getElementById('tsClear');
  const pages = Array.from(document.querySelectorAll('#pageIndex a')).map(a => ({ title: a.childNodes[1] ? a.childNodes[1].textContent.trim() : a.textContent.trim(), sub: (a.querySelector('small') || {}).textContent || '', url: a.href, t: a.dataset.t, icon: a.querySelector('svg') ? a.querySelector('svg').outerHTML : '' }));
  pages.forEach(p => { if (p.sub) p.title = p.title.replace(p.sub, '').trim(); });
  const ICON = {
    users: '<svg class="ic" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/></svg>',
    layers: '<svg class="ic" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>',
    edit: '<svg class="ic" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>'
  };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let timer = null, ctl = null, seq = 0, cur = -1;
  const mains = () => Array.from(panel.querySelectorAll('.ts-main'));
  const open = () => { panel.hidden = false; inp.setAttribute('aria-expanded', 'true'); };
  const close = () => { panel.hidden = true; inp.setAttribute('aria-expanded', 'false'); cur = -1; box.classList.remove('mobile-open'); };
  const mark = () => { const m = mains(); m.forEach(x => x.classList.remove('on')); if (m[cur]) { m[cur].classList.add('on'); m[cur].scrollIntoView({ block: 'nearest' }); } };
  const pageMatches = q => { const w = q.toLowerCase().split(/\s+/).filter(Boolean); return pages.filter(p => w.length && w.every(x => p.t.includes(x))).slice(0, 5); };
  const link = (a, cls) => '<a class="' + cls + '" href="' + esc(a.url) + '"' + (a.popup ? ' data-popup="' + esc(a.url) + '" data-title="' + esc(a.label) + '"' : '') + '>' + esc(a.label) + '</a>';
  const marksHtml = m => {
    if (!m) return '';
    if (!m.rows.length) return '<div class="ts-marks muted">No marks entered yet.</div>';
    return '<div class="ts-marks">' + m.rows.map(r => '<div class="ts-mrow"><span>' + esc(r.subject) + '</span><span>' + r.parts.map(p => '<i>' + esc(p.n) + ' ' + esc(p.m) + '/' + esc(p.f) + '</i>').join('') + '</span><b>' + (r.total != null ? esc(r.total) + '/' + esc(r.full) : '') + '</b></div>').join('') +
      '<div class="ts-mrow ts-mtot"><span>Total</span><span></span><b>' + esc(m.total) + '/' + esc(m.full) + (m.pct != null ? ' · ' + m.pct + '%' : '') + '</b></div></div>';
  };
  const factsHtml = f => !f ? '' : '<div class="ts-facts">' + f.map(x => '<div class="ts-fact"><span>' + esc(x.k) + '</span>' + (x.v == null ? '<i>Not available</i>' : (x.tel ? '<a href="tel:' + esc(String(x.v).replace(/[^+\d]/g, '')) + '">' + esc(x.v) + '</a>' : '<b>' + esc(x.v) + '</b>')) + '</div>').join('') + '</div>';
  const itemHtml = it => '<div class="ts-item"><' + (it.url ? 'a class="ts-main" href="' + esc(it.url) + '"' : 'div class="ts-main"') + '><span class="ts-ico">' + (it.iconHtml || ICON[it.icon] || ICON.layers) + '</span><span class="ts-txt"><b>' + esc(it.title) + '</b><small>' + esc(it.sub || '') + '</small></span>' + (it.badge ? '<em>' + esc(it.badge) + '</em>' : '') + '</' + (it.url ? 'a' : 'div') + '>' +
    ((it.actions && it.actions.length) ? '<div class="ts-acts">' + it.actions.map(a => link(a, 'ts-act')).join('') + '</div>' : '') + factsHtml(it.facts) + marksHtml(it.marks) + '</div>';
  const tableGroup = g => {
    const tel = new Set((g.table.tel || []));
    const head = '<tr>' + g.table.cols.map(c => '<th>' + esc(c) + '</th>').join('') + '</tr>';
    const body = g.table.rows.map(r => '<tr>' + r.map((v, i) => '<td>' + (tel.has(i) && v && v !== '-' ? '<a href="tel:' + esc(String(v).replace(/[^+\d]/g, '')) + '">' + esc(v) + '</a>' : esc(v)) + '</td>').join('') + '</tr>').join('');
    return '<div class="ts-group"><div class="ts-gh">' + esc(g.title) + '</div><div class="ts-tbl"><table><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div>' + (g.more ? '<a class="ts-more" href="' + esc(g.more) + '">Open full list →</a>' : '') + '</div>';
  };
  const group = (title, items, extra) => '<div class="ts-group"><div class="ts-gh">' + esc(title) + '</div>' + items.map(itemHtml).join('') + (extra || '') + '</div>';
  const render = (d, q) => {
    let html = '';
    if (d && d.say) html += '<div class="ts-say">' + esc(d.say) + '</div>';
    if (d && d.understood && d.understood.length) html += '<div class="ts-chips">Showing: ' + d.understood.map(x => '<span>' + esc(x) + '</span>').join('') + '</div>';
    const pg = pageMatches(q).map(p => ({ title: p.title, sub: p.sub || 'Page', url: p.url, iconHtml: p.icon }));
    const groups = (d && d.groups) || [];
    const pageHtml = pg.length ? group('Go to page', pg) : '';
    if (!groups.length || groups.every(g => !g.items.length)) html += pageHtml;
    groups.forEach(g => { if (g.table) { html += tableGroup(g); return; } if (!g.items.length && pg.length) return; html += g.items.length ? group(g.title, g.items, g.more ? '<a class="ts-more" href="' + esc(g.more) + '">See all results →</a>' : '') : '<div class="ts-group"><div class="ts-gh">' + esc(g.title) + '</div><div class="ts-empty">' + esc(g.empty || 'Nothing found.') + '</div></div>'; });
    if (groups.some(g => g.items.length || g.table)) html += pageHtml;
    if (!html.trim()) html = '<div class="ts-empty">No results for “' + esc(q) + '”. Try a student name, or something like <i>class 1 section a</i>.</div>';
    panel.innerHTML = html; cur = -1; open();
    panel.style.width = '';                                   // wide answers (tables) grow leftwards, but never under the sidebar
    if (panel.querySelector('.ts-tbl')) {
      const sb = document.querySelector('.sidebar'), left = sb && sb.offsetWidth ? sb.getBoundingClientRect().right : 0;
      const room = box.getBoundingClientRect().right - left - 16;
      panel.style.width = Math.max(360, Math.min(780, room)) + 'px';
    }
  };
  const idle = () => { panel.innerHTML = ''; panel.hidden = true; inp.setAttribute('aria-expanded', 'false'); cur = -1; };          // nothing is shown until something is typed
  const search = q => {
    if (ctl) ctl.abort(); ctl = new AbortController(); const my = ++seq;
    panel.classList.add('loading');
    fetch('/search/api?q=' + encodeURIComponent(q), { signal: ctl.signal, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(d => { if (my === seq) { panel.classList.remove('loading'); render(d, q); } })
      .catch(e => { if (e.name === 'AbortError') return; panel.classList.remove('loading'); render(null, q); });
  };
  inp.addEventListener('input', () => {
    const q = inp.value.trim(); clr.hidden = !inp.value;
    clearTimeout(timer);
    if (!q) { if (ctl) ctl.abort(); idle(); return; }
    timer = setTimeout(() => search(q), 160);
  });
  inp.addEventListener('focus', () => { if (inp.value.trim() && panel.innerHTML) open(); });
  clr.addEventListener('click', () => { inp.value = ''; clr.hidden = true; inp.focus(); idle(); });
  panel.addEventListener('click', e => {
    const h = e.target.closest('.ts-hint'); if (h) { inp.value = h.dataset.q; inp.dispatchEvent(new Event('input')); inp.focus(); return; }
    if (e.target.closest('[data-popup]')) close();
  });
  inp.addEventListener('keydown', e => {
    const m = mains();
    if (e.key === 'ArrowDown') { e.preventDefault(); cur = Math.min(cur + 1, m.length - 1); mark(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); cur = Math.max(cur - 1, 0); mark(); }
    else if (e.key === 'Enter') { const t = m[cur] || m[0]; if (t && t.href) { e.preventDefault(); location.href = t.href; } }
  });
  document.addEventListener('mousedown', e => { if (!box.contains(e.target) && e.target.id !== 'tsOpen' && !e.target.closest('#tsOpen')) close(); });
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); box.classList.add('mobile-open'); inp.focus(); inp.select(); }
    else if (e.key === 'Escape' && !panel.hidden) { close(); inp.blur(); }
  });
  const o = document.getElementById('tsOpen'); if (o) o.addEventListener('click', () => { box.classList.add('mobile-open'); inp.focus(); });
  const pb2 = document.getElementById('palBtn2'); if (pb2) pb2.addEventListener('click', () => { document.getElementById('profileMenu').classList.remove('show'); box.classList.add('mobile-open'); inp.focus(); });
})();

/* ---- dashboard: count-up numbers + staggered bars ---- */
(function () {
  document.querySelectorAll('.chart-group').forEach((g, i) => g.style.setProperty('--i', i));
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.querySelectorAll('.countup').forEach(el => {
    const to = parseFloat(el.dataset.to); if (isNaN(to)) return;
    const suf = el.dataset.suffix || '', t0 = performance.now(), dur = 900;
    const step = t => { const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(to * e).toLocaleString() + suf; if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
})();

/* ---- styled dialogs: replaces the browser's confirm()/alert(). A dialog closes ONLY with its ✕ button, Cancel/OK or Esc - never by clicking outside. ---- */
(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function dialog(o) {
    return new Promise(resolve => {
      const prev = document.activeElement;
      const wrap = document.createElement('div'); wrap.className = 'sl-modal';
      if (o.tone) {
        const IC = { danger: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M10 11v6M14 11v6"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.6 2.6 0 1 1 3.6 2.4c-.7.4-1.1.9-1.1 1.7M12 17h.01"/>', restore: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>', warn: '<path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>' };
        wrap.innerHTML = '<div class="sl-box sl-fancy tone-' + o.tone + '" role="alertdialog" aria-modal="true" aria-labelledby="slT">' +
          '<button type="button" class="modal-x sl-fx" data-x aria-label="Close" title="Close"></button>' +
          '<div class="sl-hero"><span class="sl-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' + (IC[o.tone] || IC.warn) + '</svg></span>' +
          '<h3 id="slT">' + esc(o.title) + '</h3><p>' + esc(o.message).replace(/\n/g, '<br>') + '</p>' +
          (o.items && o.items.length ? '<ul class="sl-items">' + o.items.slice(0, 4).map(n => '<li>' + esc(n) + '</li>').join('') + (o.items.length > 4 ? '<li class="more">+ ' + (o.items.length - 4) + ' more</li>' : '') + '</ul>' : '') + '</div>' +
          '<div class="sl-foot2">' + (o.cancel ? '<button type="button" class="btn" data-no>' + esc(o.cancel) + '</button>' : '') +
          '<button type="button" class="btn ' + (o.danger ? 'danger-solid' : 'primary') + '" data-ok>' + esc(o.ok) + '</button></div></div>';
      } else
      wrap.innerHTML = '<div class="sl-box" role="alertdialog" aria-modal="true" aria-labelledby="slT"><div class="sl-head"><h3 id="slT">' + esc(o.title) + '</h3>' +
        '<button type="button" class="modal-x" data-x aria-label="Close" title="Close"></button></div><div class="sl-body">' + esc(o.message).replace(/\n/g, '<br>') + '</div>' +
        '<div class="sl-foot">' + (o.cancel ? '<button type="button" class="btn" data-no>' + esc(o.cancel) + '</button>' : '') +
        '<button type="button" class="btn ' + (o.danger ? 'danger-solid' : 'primary') + '" data-ok>' + esc(o.ok) + '</button></div></div>';
      document.body.appendChild(wrap); document.body.classList.add('vm-open');
      const done = v => { document.removeEventListener('keydown', key, true); wrap.remove(); if (!document.querySelector('.sl-modal') && document.getElementById('viewer') && document.getElementById('viewer').hidden) document.body.classList.remove('vm-open'); if (prev && prev.focus) try { prev.focus(); } catch (e) {} resolve(v); };
      const key = e => { if (e.key === 'Escape') { e.stopPropagation(); done(false); } else if (e.key === 'Tab') { const f = wrap.querySelectorAll('button'); const first = f[0], last = f[f.length - 1]; if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); } } };
      document.addEventListener('keydown', key, true);
      wrap.querySelector('[data-x]').onclick = () => done(false);
      const no = wrap.querySelector('[data-no]'); if (no) no.onclick = () => done(false);
      wrap.querySelector('[data-ok]').onclick = () => done(true);
      (o.danger && no ? no : wrap.querySelector('[data-ok]')).focus();
    });
  }
  window.slConfirm = (message, o) => {
    o = o || {}; message = message || 'Are you sure?';
    // every confirmation uses the same card: round icon, title, message, two buttons. The look follows the wording unless given.
    const t = o.tone || (/restore/i.test(message) ? 'restore' : /delet|discard/i.test(message) ? 'danger' : /remov|hide|replace|clear|reject|cancel/i.test(message) ? 'warn' : 'info');
    const danger = o.danger != null ? o.danger : (t === 'danger' || t === 'warn');
    const T = { restore: ['Restore?', 'Yes, restore'], danger: [/permanent/i.test(message) ? 'Delete permanently?' : 'Delete this?', 'Yes, delete'], warn: ['Are you sure?', 'Yes, continue'], info: ['Please confirm', 'Confirm'] }[t];
    return dialog({ title: o.title || T[0], message, ok: o.ok || T[1], cancel: o.cancel || 'Cancel', danger, tone: t, items: o.items });
  };
  window.slAlert = (message, o) => { o = o || {}; return dialog({ title: o.title || 'Notice', message, ok: o.ok || 'OK', cancel: null, danger: false }); };

  // upgrade inline  onsubmit="return confirm('…')"  /  onclick="return confirm('…')"
  const RX = /confirm\(\s*(['"])([\s\S]*?)\1\s*\)/;
  const upgrade = root => (root || document).querySelectorAll('[onsubmit*="confirm("],[onclick*="confirm("]').forEach(el => {
    ['onsubmit', 'onclick'].forEach(a => { const v = el.getAttribute(a); const m = v && RX.exec(v); if (m) { el.dataset.confirm = m[2].replace(/\\'/g, "'"); el.removeAttribute(a); } });
  });
  upgrade(document); window.slUpgradeConfirm = upgrade;
  let bypass = null;
  document.addEventListener('submit', e => {
    const f = e.target; if (!f.dataset || !f.dataset.confirm || bypass === f) return;
    e.preventDefault(); const sub = e.submitter;
    const options={tone:f.dataset.confirmTone,title:f.dataset.confirmTitle,ok:f.dataset.confirmOk};
    try { options.items=JSON.parse(f.dataset.confirmItems || '[]'); } catch (_) { options.items=[]; }
    slConfirm(f.dataset.confirm,options).then(ok => { if (ok) { bypass = f; f.requestSubmit ? f.requestSubmit(sub || undefined) : f.submit(); bypass = null; } });
  }, true);
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-confirm]'); if (!b || b.tagName === 'FORM' || bypass === b) return;
    e.preventDefault(); e.stopPropagation();
    slConfirm(b.dataset.confirm).then(ok => { if (!ok) return; bypass = b; b.click(); bypass = null; });
  }, true);
})();

/* ---- every page header gets the small "School / Section" eyebrow like the reference ---- */
(function () {
  const sub = document.querySelector('.path-sub'); const label = sub ? sub.textContent.trim() : '';
  document.querySelectorAll('.page-head').forEach(h => {
    const first = h.firstElementChild; if (!first || first.querySelector('.eyebrow')) return;
    const t = first.querySelector('h1'); if (!t) return;
    const e = document.createElement('div'); e.className = 'eyebrow'; e.innerHTML = '<i></i> ' + (label || 'Workspace');
    first.insertBefore(e, t);
  });
})();

/* ---- toast messages: success / error / warning / info. They hide on their own; hovering pauses them. ---- */
(function () {
  const ICON = {
    success: '<path d="M20 6 9 17l-5-5"/>', error: '<path d="M12 8v5M12 16.5v.01"/><circle cx="12" cy="12" r="9"/>',
    warning: '<path d="M12 9v4M12 17v.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.01"/>'
  };
  const NORM = { success: 'success', ok: 'success', error: 'error', danger: 'error', warning: 'warning', warn: 'warning', info: 'info', message: 'info' };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let host = null;
  const DUR = { success: 4000, info: 5000, warning: 6500, error: 8000 };
  window.slToast = function (type, message, opts) {
    type = NORM[type] || 'info'; opts = opts || {};
    if (!host) { host = document.createElement('div'); host.id = 'slToasts'; host.setAttribute('aria-live', 'polite'); host.setAttribute('role', 'status'); document.body.appendChild(host); }
    // identical message already showing -> just restart it
    const dup = Array.from(host.children).find(t => t.dataset.msg === message && t.dataset.type === type);
    if (dup) dup.remove();
    const el = document.createElement('div'); el.className = 'sl-toast ' + type; el.dataset.msg = message; el.dataset.type = type;
    const ms = opts.duration || DUR[type];
    el.innerHTML = '<span class="st-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' + ICON[type] + '</svg></span>' +
      '<div class="st-body">' + (opts.title ? '<b>' + esc(opts.title) + '</b>' : '') + '<span>' + esc(message) + '</span></div>' +
      '<button type="button" class="modal-x" aria-label="Dismiss" title="Dismiss"></button><i class="st-bar" style="animation-duration:' + ms + 'ms"></i>';
    host.appendChild(el);
    while (host.children.length > 5) host.firstChild.remove();
    let left = ms, started = Date.now(), timer = null;
    const kill = () => { clearTimeout(timer); el.classList.add('out'); setTimeout(() => el.remove(), 260); };
    const run = () => { started = Date.now(); timer = setTimeout(kill, left); };
    el.addEventListener('mouseenter', () => { clearTimeout(timer); left -= Date.now() - started; el.classList.add('paused'); });
    el.addEventListener('mouseleave', () => { el.classList.remove('paused'); run(); });
    el.querySelector('.modal-x').onclick = kill;
    run(); return el;
  };
  const fd = document.getElementById('flashData');
  if (fd) { try { JSON.parse(fd.textContent).forEach((m, i) => setTimeout(() => slToast(m[0], m[1]), i * 120)); } catch (e) {} }
})();

/* ---- pretty dropdowns: <select data-pretty> keeps working as a normal field (value, form post, live sync) but shows icons / grade badges ---- */
(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let pop = null, openFor = null, openedAt = 0;
  const enhanced = new WeakSet();
  const selector = 'select:not([multiple]):not([size]),select[size="1"]:not([multiple])';
  const face = (o, forPop) => {
    if (!o) return '<span class="ps-empty">—</span>';
    const icon = o.dataset.icon ? '<img class="ps-ic" src="' + esc(o.dataset.icon) + '" alt="">' : '';
    const tone = o.dataset.tone ? ' tone-' + o.dataset.tone : '';
    if (!o.value) return '<span class="ps-empty">' + esc(o.textContent.trim() || (forPop ? 'Not set' : '—')) + '</span>';
    if (o.parentNode.dataset.pretty === 'grade') return '<span class="gb' + tone + '">' + esc(o.textContent.trim()) + '</span>' + (forPop && o.dataset.note ? '<small>' + esc(o.dataset.note) + '</small>' : '');
    return icon + '<span class="ps-t">' + esc(o.textContent.trim()) + '</span>' + (forPop && o.dataset.note ? '<small>' + esc(o.dataset.note) + '</small>' : '');
  };
  function refresh(sel) { const b = sel.nextElementSibling; if (b && b.classList.contains('ps-btn')) { b.querySelector('.ps-face').innerHTML = face(sel.options[sel.selectedIndex], false); b.disabled = sel.disabled; } }
  function enhance(sel) {
    if (enhanced.has(sel)) return; enhanced.add(sel); sel.dataset.psReady = '1';
    if (sel.nextElementSibling && sel.nextElementSibling.classList.contains('ps-btn')) sel.nextElementSibling.remove();
    sel.classList.add('ps-native'); sel.tabIndex = -1; sel.setAttribute('aria-hidden', 'true');
    const b = document.createElement('button'); b.type = 'button'; b.className = 'ps-btn' + (sel.dataset.pretty === 'grade' ? ' ps-grade' : sel.dataset.pretty ? ' ps-dev' : ' ps-standard');
    b.setAttribute('aria-haspopup', 'listbox'); b.setAttribute('aria-expanded', 'false');
    b.innerHTML = '<span class="ps-face"></span><svg class="ps-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
    const label = sel.labels && sel.labels[0];
    const labelText = sel.getAttribute('aria-label') || (label && Array.from(label.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').trim()) || sel.name || 'Choose an option';
    b.setAttribute('aria-label', labelText);
    sel.insertAdjacentElement('afterend', b); refresh(sel);
    sel.addEventListener('invalid', e => { e.preventDefault(); b.focus(); b.setAttribute('aria-invalid', 'true'); });
    sel.addEventListener('change', () => b.removeAttribute('aria-invalid'));
    if (sel.form) sel.form.addEventListener('reset', () => setTimeout(() => refresh(sel), 0));
    sel.addEventListener('change', () => refresh(sel));
    b.addEventListener('click', () => (openFor === sel ? closePop() : openPop(sel, b)));
    b.addEventListener('keydown', e => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); openPop(sel, b); } });
  }
  function closePop(focusBack) { if (!pop) return; const b = openFor && openFor.nextElementSibling; pop.remove(); pop = null; if (b) { b.setAttribute('aria-expanded', 'false'); if (focusBack) b.focus(); } openFor = null; }
  function openPop(sel, btn) {
    closePop(); openFor = sel; openedAt = Date.now(); btn.setAttribute('aria-expanded', 'true');
    pop = document.createElement('div'); pop.className = 'ps-pop'; pop.setAttribute('role', 'listbox'); pop.setAttribute('aria-label', btn.getAttribute('aria-label') || 'Options');
    pop.innerHTML = Array.from(sel.options).map((o, i) => '<button type="button" class="ps-opt' + (o.selected ? ' on' : '') + '" role="option" aria-selected="' + o.selected + '" data-i="' + i + '"' + (o.disabled || (o.parentElement.tagName === 'OPTGROUP' && o.parentElement.disabled) ? ' disabled' : '') + '><span class="ps-of">' + face(o, true) + '</span>' +
      (o.selected ? '<svg class="ps-ok" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg>' : '') + '</button>').join('');
    document.body.appendChild(pop);
    const r = btn.getBoundingClientRect(), pw = Math.min(Math.max(r.width, 180), innerWidth - 16), ph = Math.min(pop.scrollHeight, 320);
    pop.style.width = pw + 'px'; pop.style.minWidth = pw + 'px';
    let top = r.bottom + 6; if (top + ph > innerHeight - 8 && r.top - ph - 6 > 8) top = r.top - ph - 6;
    top = Math.max(8, Math.min(top, innerHeight - Math.min(ph, innerHeight - 16) - 8));
    pop.style.maxHeight = Math.min(320, innerHeight - top - 8) + 'px';
    pop.style.top = top + 'px'; pop.style.left = Math.min(Math.max(8, r.left), innerWidth - pw - 8) + 'px';
    const cur = pop.querySelector('.on:not(:disabled)') || pop.querySelector('.ps-opt:not(:disabled)'); cur && cur.focus({ preventScroll: true });
    pop.addEventListener('click', e => { const o = e.target.closest('.ps-opt'); if (!o || o.disabled) return; sel.selectedIndex = parseInt(o.dataset.i, 10); sel.dispatchEvent(new Event('input', { bubbles: true })); sel.dispatchEvent(new Event('change', { bubbles: true })); refresh(sel); closePop(true); });
    pop.addEventListener('keydown', e => {
      const items = Array.from(pop.querySelectorAll('.ps-opt:not(:disabled)')), i = items.indexOf(document.activeElement);
      if (!items.length) return;
      if (e.key === 'Home') { e.preventDefault(); items[0].focus(); }
      else if (e.key === 'End') { e.preventDefault(); items[items.length - 1].focus(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); items[Math.min(i + 1, items.length - 1)].focus(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); items[Math.max(i - 1, 0)].focus(); }
      else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closePop(true); }
      else if (e.key === 'Tab') closePop();
      else if (e.key.length === 1) { const k = e.key.toLowerCase(); const n = items.find((x, j) => j > i && x.textContent.trim().toLowerCase().startsWith(k)) || items.find(x => x.textContent.trim().toLowerCase().startsWith(k)); n && n.focus(); }
    });
  }
  // Runs before modal Escape handlers: dismiss the menu, keep its form open.
  document.addEventListener('keydown', e => {
    if (pop && e.key === 'Escape') {
      e.preventDefault(); e.stopImmediatePropagation(); closePop(true);
    }
  }, true);
  document.addEventListener('mousedown', e => { if (pop && !pop.contains(e.target) && !(openFor && openFor.nextElementSibling.contains(e.target))) closePop(); });
  window.addEventListener('resize', () => closePop()); document.addEventListener('scroll', e => { if (pop && Date.now() - openedAt > 300 && !pop.contains(e.target)) closePop(); }, true);
  const init = () => document.querySelectorAll(selector).forEach(enhance);
  const all = () => document.querySelectorAll(selector).forEach(refresh);
  document.addEventListener('DOMContentLoaded', init); if (document.readyState !== 'loading') init();
  window.addEventListener('sl:live-updated', () => { init(); all(); });
  new MutationObserver(records => {
    if (openFor && !openFor.isConnected) closePop();
    let added = false;
    records.forEach(record => {
      const target = record.target.nodeType === 1 ? record.target : record.target.parentElement;
      const select = target && target.closest('select');
      if (select && enhanced.has(select)) { refresh(select); if (openFor === select) closePop(); }
      if (Array.from(record.addedNodes).some(node => node.nodeType === 1 && (node.matches(selector) || node.querySelector(selector)))) added = true;
    });
    if (added) init();
  }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['disabled', 'selected', 'label'] });
  window.slPretty = { init, refresh: all };
})();
