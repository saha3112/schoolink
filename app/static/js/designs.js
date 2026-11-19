/* "Use in a class" pop-up on Report setup > Card designs.
   Pick whole classes or single sections -> the chosen built-in design is applied there. The server test-renders a real card
   for every change and undoes it on the spot if the card cannot be produced. Closes only with ✕ / Cancel. */
(function () {
  const csrf = () => (document.querySelector('meta[name=csrf]') || {}).content || '';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function openUse(view, label) {
    const prev = document.activeElement, wrap = document.createElement('div'); wrap.className = 'sl-modal pg-modal';
    wrap.innerHTML = '<div class="sl-box pg-box lg" role="dialog" aria-modal="true" aria-labelledby="useT"><div class="sl-head"><h3 id="useT">Use “' + esc(label) + '” in…</h3><button type="button" class="modal-x" data-x aria-label="Close" title="Close"></button></div>' +
      '<div class="pg-body"><div class="pg-loading"><span class="spin"></span> Loading classes…</div></div>' +
      '<div class="sl-foot"><span class="muted" data-count style="margin-right:auto;font-size:12.5px">Nothing selected</span><button type="button" class="btn" data-x2>Cancel</button><button type="button" class="btn primary" data-apply disabled>Apply</button></div></div>';
    document.body.appendChild(wrap); document.body.classList.add('vm-open');
    const body = wrap.querySelector('.pg-body'), apply = wrap.querySelector('[data-apply]'), count = wrap.querySelector('[data-count]');
    const close = () => { document.removeEventListener('keydown', key, true); wrap.remove(); if (!document.querySelector('.sl-modal,.mp-modal') && document.getElementById('viewer') && document.getElementById('viewer').hidden) document.body.classList.remove('vm-open'); if (prev && prev.focus) try { prev.focus(); } catch (e) { } };
    const key = e => { if (e.key === 'Escape' && wrap === Array.from(document.querySelectorAll('.sl-modal')).pop()) { e.stopPropagation(); close(); } };
    document.addEventListener('keydown', key, true);
    wrap.querySelector('[data-x]').onclick = close; wrap.querySelector('[data-x2]').onclick = close;

    const selected = () => {
      const t = [];
      body.querySelectorAll('.use-class').forEach(row => {
        const all = row.querySelector('.use-all');
        const fit = row.dataset.fit === '1';
        if (all.checked) t.push({ class_id: +all.value, section_id: 0, label: all.dataset.n, fit });
        else row.querySelectorAll('.use-sec:checked').forEach(s => t.push({ class_id: +all.value, section_id: +s.value, label: all.dataset.n + ' ' + s.dataset.n, fit }));
      });
      return t;
    };
    const upd = () => { const n = selected().length; count.textContent = n ? n + ' selected' : 'Nothing selected'; apply.disabled = !n; apply.textContent = n ? 'Apply to ' + n : 'Apply'; };

    fetch('/admin/layouts/designs/targets?view=' + encodeURIComponent(view), { credentials: 'same-origin' }).then(r => r.json()).then(d => {
      body.innerHTML = '<p class="pg-sub">Tick a whole class, or just some sections. “now” shows the design each one uses today. Every change is tested with a real student and undone automatically if the card cannot be made.</p><div class="use-list">' +
        d.classes.map(c => '<div class="use-class' + (c.fit ? '' : ' nofit') + '" data-fit="' + (c.fit ? 1 : 0) + '"><label class="use-head"><input type="checkbox" class="use-all" value="' + c.id + '" data-n="' + esc(c.name) + '"> <b>' + esc(c.name) + '</b> <small>whole class</small>' + (c.fit ? '<span class="chip green">made for this class</span>' : '<span class="chip orange">not made for this class</span>') + '</label>' +
          '<div class="use-secs">' + c.sections.map(s => '<label class="use-sec-l"><input type="checkbox" class="use-sec" value="' + s.id + '" data-n="' + esc(s.name) + '"> <span>' + esc(s.name) + '</span><small>now: ' + esc(s.current || 'no card') + '</small></label>').join('') + '</div></div>').join('') + '</div>';
      body.addEventListener('change', e => {
        const row = e.target.closest('.use-class'); if (!row) return;
        if (e.target.classList.contains('use-all') && e.target.checked) row.querySelectorAll('.use-sec').forEach(s => { s.checked = false; });
        if (e.target.classList.contains('use-sec') && e.target.checked) row.querySelector('.use-all').checked = false;
        upd();
      });
    }).catch(() => { body.innerHTML = '<div class="pg-loading err">Could not load the classes.</div>'; });

    apply.addEventListener('click', async () => {
      const t = selected(); if (!t.length) return;
      const odd = t.filter(x => !x.fit);
      if (odd.length && !(await slConfirm('This design was not made for: ' + odd.map(x => x.label).join(', ') + '.\n\nIt may print with empty or missing parts. Use it anyway? (You can switch back at any time.)', { danger: true, title: 'Not made for this class', ok: 'Use anyway' }))) return;
      apply.disabled = true; apply.innerHTML = '<span class="spin"></span> Applying…';
      fetch('/admin/layouts/designs/builtin/' + encodeURIComponent(view) + '/apply', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() }, body: JSON.stringify({ targets: t }) })
        .then(r => r.json()).then(d => {
          (d.applied || []).forEach(a => slToast('success', a.label + ': ' + a.before + ' → ' + a.after));
          (d.failed || []).forEach(f => slToast('error', f.label + ' was left unchanged — ' + f.reason + '.'));
          if (!(d.applied && d.applied.length)) { if (!(d.failed && d.failed.length)) slToast('error', d.message || 'Nothing was changed.'); apply.disabled = false; upd(); return; }
          close(); if (window.slLiveRefresh) slLiveRefresh();
        }).catch(() => { slToast('error', 'Could not reach the server. Nothing was changed.'); apply.disabled = false; upd(); });
    });
  }
  document.addEventListener('click', e => { const b = e.target.closest('[data-use-view]'); if (b) { e.preventDefault(); openUse(b.dataset.useView, b.dataset.useLabel); } });
})();
