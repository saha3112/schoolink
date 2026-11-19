/* CSV import UI.  A page-header button (added automatically for marks / class-teacher pages) opens a pop-up:
     1. download a sample CSV (pre-filled with what is saved now) or a blank template,
     2. drop / choose the CSV,
     3. it is checked and imported at once; the file is deleted right away (it is never stored).
   Success / error messages appear as toasts and in the pop-up; other open panels update by themselves (live sync). */
(function () {
  const meta = document.querySelector('meta[name=csv-kind]');
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const csrf = () => { const m = document.querySelector('meta[name=csrf]'); return m ? m.content : ''; };
  const toast = (t, m) => window.slToast && slToast(t, m);
  const ICON = {
    dl: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m-4-4 4 4 4-4"/><path d="M5 17v3h14v-3"/></svg>',
    up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4m-5 5 5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>',
    sheet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8M8 9h2"/></svg>'
  };
  const TITLES = { parents: 'Parents', marks: 'Marks', special: 'Special subject grades', attendance: 'Attendance', comments: 'Teacher comments', development: 'Development skills', rank: 'Ranks', house: 'House points', average: 'Average, award & promotion', students: 'Students' };
  const NOTES = {
    marks: 'One row per student, one column per subject and sub-type. Leave a cell empty to keep the saved mark. Use a number, AB, NS, NA or a grade (A+, B …).',
    special: 'One row per student, one column per special subject (grades like A+, B, or AB).',
    attendance: 'Columns: Total sessions and Attended. Attended cannot be more than the total.',
    comments: 'One comment per student (up to 2000 characters).',
    development: 'Grades allowed: EXCELLENT, GOOD, NEEDS IMPROVEMENT, UNSATISFACTORY, ABSENT.',
    rank: 'One rank per student (up to 20 characters).',
    house: 'Columns: House (name) and Points (whole number).',
    average: 'Columns: Average, Award and Promotion.',
    parents: 'Example rows only. Email ID (email column) and occupation are optional. Enter student_codes and/or admission_numbers; separate siblings with semicolons in the same order (one, two, three or more children). Both identifiers must match the same child when supplied. Child links are optional; blank cells keep existing links. children_names is for reference. Existing parents match by mobile. New parents need first_name and initial_password (at least 6 characters).',
    students: 'Columns: student_id, student_code, first_name, last_name, roll (optional), class_name, section_name. Codes that already exist are skipped.'
  };

  function panel(kind, params) {
    const q = new URLSearchParams(params).toString();
    const root = document.createElement('div'); root.className = 'csv-panel';
    root.innerHTML =
      '<div class="csv-steps">' +
        '<div class="csv-step"><span class="step-n">1</span><div><b>Download a sample</b><p>' + esc(NOTES[kind] || '') + '</p>' +
          '<div class="csv-dl"><a class="btn" data-csvdl href="/csv/sample/' + kind + '?' + q + '">' + ICON.dl + ' Sample data</a>' +
          (['students', 'parents'].includes(kind) ? '' : '<a class="btn" data-csvdl href="/csv/sample/' + kind + '?' + q + '&blank=1">' + ICON.sheet + ' Blank template</a>') + '</div></div></div>' +
        '<div class="csv-step"><span class="step-n">2</span><div><b>Upload your CSV</b><p>Edit the file in Excel or Google Sheets, save as <b>CSV</b>, then drop it here.</p>' +
          '<div class="mp-drop csv-drop" data-drop tabindex="0" role="button" aria-label="Choose a CSV file"><div class="mp-drop-ic">' + ICON.up + '</div><b>Drag &amp; drop your CSV here</b><span>or <u>browse</u> from your computer</span><input type="file" data-file hidden accept=".csv,text/csv,.txt"></div>' +
          '<div class="csv-file" data-fileinfo hidden></div>' +
          '<div class="csv-go"><button type="button" class="btn primary" data-import disabled>' + ICON.up + ' Import CSV</button><small class="muted">The file is checked first — if anything is wrong, nothing is changed — and it is deleted as soon as the import finishes.</small></div></div></div>' +
      '</div><div class="csv-result" data-result aria-live="polite"></div>';
    const $ = s => root.querySelector(s);
    let file = null, busy = false;
    const drop = $('[data-drop]'), inp = $('[data-file]'), info = $('[data-fileinfo]'), go = $('[data-import]'), res = $('[data-result]');
    const setFile = f => {
      res.innerHTML = '';
      if (!f) { file = null; info.hidden = true; go.disabled = true; return; }
      if (!/\.(csv|txt)$/i.test(f.name)) { toast('error', 'Please choose a .csv file (save your sheet as “CSV”).'); return; }
      if (f.size > 2 * 1024 * 1024) { toast('error', 'That file is larger than 2 MB.'); return; }
      file = f; info.hidden = false;
      info.innerHTML = '<span class="mp-q-ic" style="--c:#19a889">' + ICON.sheet + '</span><span class="mp-q-n"><b>' + esc(f.name) + '</b><small>' + Math.max(1, Math.round(f.size / 1024)) + ' KB · ready to import</small></span><button type="button" class="modal-x mini" data-rmfile aria-label="Remove file" title="Remove file"></button>';
      go.disabled = false;
    };
    drop.addEventListener('click', () => inp.click());
    drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inp.click(); } });
    inp.addEventListener('change', () => { setFile(inp.files[0]); inp.value = ''; });
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => { if (e.dataTransfer.files.length > 1) toast('info', 'Only one CSV at a time — the first file was taken.'); setFile(e.dataTransfer.files[0]); });
    info.addEventListener('click', e => { if (e.target.closest('[data-rmfile]')) setFile(null); });
    root.addEventListener('click', async e => {
      const a = e.target.closest('[data-csvdl]'); if (!a) return;
      e.preventDefault();
      try {
        const r = await fetch(a.href, { credentials: 'same-origin' });
        if (!r.ok) { let m = 'Could not create the sample.'; try { m = (await r.json()).message || m; } catch (x) { } toast('error', m); return; }
        const blob = await r.blob(), cd = r.headers.get('Content-Disposition') || '', nm = (/filename="([^"]+)"/.exec(cd) || [])[1] || 'sample.csv';
        const u = URL.createObjectURL(blob), l = document.createElement('a'); l.href = u; l.download = nm; document.body.appendChild(l); l.click(); l.remove(); setTimeout(() => URL.revokeObjectURL(u), 2000);
        toast('success', 'Sample CSV downloaded.');
      } catch (err) { toast('error', 'Could not download the sample. Check your connection.'); }
    });
    go.addEventListener('click', async () => {
      if (!file || busy) return; busy = true; go.disabled = true; go.innerHTML = '<span class="spin"></span> Importing…'; res.innerHTML = '';
      const fd = new FormData(); fd.append('file', file); Object.keys(params).forEach(k => fd.append(k, params[k]));
      let d = {}, ok = false;
      try {
        const r = await fetch('/csv/import/' + kind, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf() } });
        try { d = await r.json(); } catch (x) { d = { message: 'The server sent an unexpected reply. Nothing was imported.' }; }
        ok = r.ok && d.ok;
      } catch (err) { d = { message: 'Could not reach the server. Nothing was imported.' }; }
      busy = false; go.innerHTML = ICON.up + ' Import CSV'; go.disabled = !file;
      toast(ok ? 'success' : 'error', d.message || (ok ? 'Imported.' : 'The import failed.'));
      let h = '<div class="csv-msg ' + (ok ? 'ok' : 'bad') + '"><b>' + esc(d.message || '') + '</b></div>';
      if (d.warnings && d.warnings.length) h += '<details class="csv-list warn"><summary>' + d.warnings.length + ' note' + (d.warnings.length > 1 ? 's' : '') + '</summary><ul>' + d.warnings.map(w => '<li>' + esc(w) + '</li>').join('') + '</ul></details>';
      if (d.errors && d.errors.length) h += '<div class="csv-list err"><b>Please fix these and upload again</b><ul>' + d.errors.map(w => '<li>' + esc(w) + '</li>').join('') + '</ul>' + (d.more ? '<small>…and ' + d.more + ' more.</small>' : '') + '</div>';
      res.innerHTML = h;
      if (ok) { file = null; info.hidden = true; go.disabled = true; if (window.slLiveRefresh) slLiveRefresh(); else if (root.dataset.reload) setTimeout(() => location.reload(), 900); }
    });
    return root;
  }

  function openPopup(kind, params) {
    const prev = document.activeElement;
    const wrap = document.createElement('div'); wrap.className = 'sl-modal';
    wrap.innerHTML = '<div class="sl-box csv-box" role="dialog" aria-modal="true" aria-labelledby="csvT"><div class="sl-head"><h3 id="csvT">Import ' + esc(TITLES[kind] || 'data') + ' from CSV</h3><button type="button" class="modal-x" data-x aria-label="Close" title="Close"></button></div><div class="sl-body csv-body"></div></div>';
    wrap.querySelector('.csv-body').appendChild(panel(kind, params));
    document.body.appendChild(wrap); document.body.classList.add('vm-open');
    const close = () => { document.removeEventListener('keydown', key, true); wrap.remove(); if (!document.querySelector('.sl-modal,.mp-modal') && document.getElementById('viewer') && document.getElementById('viewer').hidden) document.body.classList.remove('vm-open'); if (prev && prev.focus) try { prev.focus(); } catch (e) { } };
    const key = e => { if (e.key === 'Escape' && !document.querySelector('.sl-modal ~ .sl-modal')) { e.stopPropagation(); close(); } };
    document.addEventListener('keydown', key, true);
    wrap.querySelector('[data-x]').onclick = close;          // closes only with ✕ (never by clicking outside)
    wrap.addEventListener('dragover', e => e.preventDefault()); wrap.addEventListener('drop', e => e.preventDefault());
  }

  function pageParams() {
    const f = document.getElementById('picker'); const p = {};
    ['class_id', 'section_id', 'exam_id'].forEach(k => { const el = f && f.elements[k]; if (el && el.value) p[k] = el.value; });
    return p;
  }

  document.addEventListener('DOMContentLoaded', () => {
    // pages whose only job is an import (student upload): the pop-up opens by itself and can be re-opened with the button
    const auto = document.querySelector('[data-csv-auto]');
    if (auto) setTimeout(() => openPopup(auto.dataset.csvOpen, {}), 250);
    if (!meta) return;
    const kind = meta.content, head = document.querySelector('.page-head');
    if (!head || document.querySelector('[data-csv-open]')) return;
    const ADMIN_ONLY = kind === 'students' || kind === 'parents';
    const need = ADMIN_ONLY ? [] : ['class_id', 'section_id'].concat(kind === 'average' ? [] : ['exam_id']);
    const b = document.createElement('button'); b.type = 'button'; b.className = 'btn csv-open';
    b.innerHTML = ICON.sheet + ' Import CSV'; b.title = 'Import ' + (TITLES[kind] || '') + ' from a CSV file · download a sample';
    b.addEventListener('click', () => {
      const p = pageParams();
      if (!need.every(k => p[k])) { toast('info', 'Choose the class' + (need.includes('exam_id') ? ', section and exam' : ' and section') + ' first, then import.'); return; }
      openPopup(kind, p);
    });
    let box = head.querySelector('.h-actions'); if (!box) { box = document.createElement('div'); box.className = 'h-actions'; head.appendChild(box); }
    box.appendChild(b);
  });
  document.addEventListener('click', e => { const b = e.target.closest('[data-csv-open]'); if (b) { e.preventDefault(); openPopup(b.dataset.csvOpen, {}); } });
  window.SLCsv = { open: openPopup };
})();
