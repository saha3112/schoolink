/* Edit / manage pages in a pop-up.
   <a href="…" data-modal>   opens that page's form in a pop-up (no navigation).
     data-modal-whole        show the whole page body (not just the form card)
     data-modal-stay         after a successful save keep the pop-up open and show the result (manage screens)
     data-modal-size="lg"    wider pop-up
   Saving happens in the background; the answer (success / error) comes back as a toast, the list behind updates by itself
   (live sync) and nothing reloads.  [data-cancel] buttons and the ✕ close it; clicking outside never does. */
(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const toast = (t, m) => window.slToast && slToast(t, m);
  const csrf = () => { const m = document.querySelector('meta[name=csrf]'); return m ? m.content : ''; };

  function open(url, opts) {
    opts = opts || {};
    const prev = document.activeElement;
    const wrap = document.createElement('div'); wrap.className = 'sl-modal pg-modal';
    wrap.innerHTML = '<div class="sl-box pg-box' + (opts.size === 'lg' ? ' lg' : '') + '" role="dialog" aria-modal="true" aria-labelledby="pgT"><div class="sl-head"><h3 id="pgT">' + esc(opts.title || 'Loading…') + '</h3><button type="button" class="modal-x" data-x aria-label="Close" title="Close"></button></div><div class="pg-body"><div class="pg-loading"><span class="spin"></span> Loading…</div></div></div>';
    document.body.appendChild(wrap); document.body.classList.add('vm-open');
    const body = wrap.querySelector('.pg-body'), titleEl = wrap.querySelector('#pgT');
    const state = { url, opts, busy: false };
    const close = () => { document.removeEventListener('keydown', key, true); wrap.remove(); if (!document.querySelector('.sl-modal,.mp-modal') && document.getElementById('viewer') && document.getElementById('viewer').hidden) document.body.classList.remove('vm-open'); if (prev && prev.focus) try { prev.focus(); } catch (e) { } };
    const key = e => { if (e.key === 'Escape' && wrap === Array.from(document.querySelectorAll('.sl-modal')).pop()) { e.stopPropagation(); close(); } };
    document.addEventListener('keydown', key, true);
    wrap.querySelector('[data-x]').onclick = close;                      // only ✕ / Cancel close it - never an outside click

    function render(doc) {
      const main = doc.querySelector('main.content');
      if (!main) { body.innerHTML = '<div class="pg-loading">This page cannot be shown here.</div>'; return; }
      let node, title = '';
      const f = main.querySelector('[data-modal-form]');
      if (state.opts.whole || !f) {
        node = main.cloneNode(true);
        node.querySelectorAll('#flashData,.eyebrow,.h-actions').forEach(n => n.remove());
        const h1 = node.querySelector('.page-head h1'); title = h1 ? h1.textContent.trim() : '';
        if (h1) h1.remove();
        const hd = node.querySelector('.page-head'); if (hd && !hd.textContent.trim()) hd.remove();
      } else {
        node = (f.closest('.card') || f).cloneNode(true);
        const h3 = node.querySelector('h3'); if (h3) { title = h3.textContent.trim(); h3.remove(); }
        const hp = main.querySelector('.page-head h1'); if (!title && hp) title = hp.textContent.trim();
        const sub = main.querySelector('.page-head p'); if (sub && hp && state.opts.sub !== false) { const p = document.createElement('p'); p.className = 'pg-sub'; p.textContent = sub.textContent.trim(); node.insertBefore(p, node.firstChild); }
      }
      // "← back" links make no sense inside a pop-up (the ✕ closes it): drop them and the separator that followed
      node.querySelectorAll('a').forEach(l => { if (/^\s*(←|&larr;|‹)/.test(l.textContent)) { const nx = l.nextSibling; if (nx && nx.nodeType === 3) nx.textContent = nx.textContent.replace(/^\s*[·|-]\s*/, ''); l.remove(); } });
      node.querySelectorAll('.page-head p').forEach(pp => { if (!pp.textContent.trim()) pp.remove(); });
      node.querySelectorAll('.page-head').forEach(h => { if (!h.textContent.trim() && !h.querySelector('button,a,form,input')) h.remove(); });
      titleEl.textContent = state.opts.title && state.opts.title !== 'Edit' && state.opts.title !== 'Manage' ? state.opts.title : (title || state.opts.title || 'Edit');
      body.innerHTML = ''; body.appendChild(node);
      node.querySelectorAll('.table-wrap[data-live-html]').forEach(t => t.removeAttribute('data-live-html'));     // the pop-up is not a live region
      node.querySelectorAll('[data-live-html]').forEach(t => t.removeAttribute('data-live-html'));
      // inline scripts of the page (class → section filters etc.) must run here too
      const scripts = Array.from(node.querySelectorAll('script')).concat(Array.from(doc.querySelectorAll('body > script:not([src]):not([type])')).filter(s => /sectionSubjects|bindCascade/.test(s.textContent)));
      scripts.forEach(s => { if (s.type && s.type !== 'text/javascript') return; const n = document.createElement('script'); n.textContent = s.textContent; document.body.appendChild(n); n.remove(); });
      if (window.slUpgradeConfirm) slUpgradeConfirm(body);
      if (window.slPretty) slPretty.init();
      const first = body.querySelector('input:not([type=hidden]):not([disabled]),select:not([disabled]),textarea'); if (first && !state.opts.noFocus) setTimeout(() => { try { first.focus({ preventScroll: true }); } catch (e) { } }, 60);
    }
    async function load(u) {
      state.url = u; body.innerHTML = '<div class="pg-loading"><span class="spin"></span> Loading…</div>';
      try {
        const r = await fetch(u, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
        if (r.redirected && /\/login/.test(r.url)) { location.href = u; return; }
        if (!r.ok) { body.innerHTML = '<div class="pg-loading err">Could not open this (' + r.status + ').</div>'; return; }
        render(new DOMParser().parseFromString(await r.text(), 'text/html'));
      } catch (e) { body.innerHTML = '<div class="pg-loading err">Could not reach the server. Check your connection.</div>'; }
    }

    // navigation inside the pop-up
    wrap.addEventListener('click', e => {
      if (e.target.closest('[data-cancel]')) { e.preventDefault(); close(); return; }
      const a = e.target.closest('a[data-modal]');
      if (a && !e.ctrlKey && !e.metaKey) { e.preventDefault(); e.stopPropagation(); state.opts = Object.assign({}, state.opts, { whole: a.hasAttribute('data-modal-whole'), stay: a.hasAttribute('data-modal-stay'), title: a.dataset.modalTitle || null }); load(a.getAttribute('href')); }
    });
    // saving in the background
    wrap.addEventListener('submit', async e => {
      const form = e.target; if (!form.closest('.pg-body') || (form.method || '').toLowerCase() !== 'post') return;
      e.preventDefault(); if (state.busy) return; state.busy = true;
      const btn = e.submitter || form.querySelector('button:not([type=button])'), label = btn && btn.innerHTML;
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span> Saving…'; }
      const fd = new FormData(form); if (e.submitter && e.submitter.name) fd.append(e.submitter.name, e.submitter.value);
      try {
        const r = await fetch(form.getAttribute('action') || state.url, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf() } });
        const html = await r.text(), doc = new DOMParser().parseFromString(html, 'text/html');
        let flashes = []; try { const fdEl = doc.getElementById('flashData'); if (fdEl) flashes = JSON.parse(fdEl.textContent); } catch (x) { }
        flashes.forEach(m => toast(m[0], m[1]));
        const bad = flashes.some(m => m[0] === 'error' || m[0] === 'danger'), good = r.ok && !bad && (flashes.length ? flashes.some(m => m[0] === 'success' || m[0] === 'info' || m[0] === 'warning') : true);
        if (!flashes.length && !r.ok) toast('error', 'That did not save (' + r.status + '). Please try again.');
        if (good) {
          if (window.slLiveRefresh) slLiveRefresh();
          if (state.opts.stay) { state.url = r.url || state.url; render(doc); } else close();
        } else if (r.ok && doc.querySelector('main.content')) { render(doc); }       // errors: show the page again, nothing is lost
      } catch (err) { toast('error', 'Could not reach the server. Nothing was saved.'); }
      state.busy = false; if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = label; }
    });
    load(url);
    return { close };
  }

  document.addEventListener('click', e => {
    const a = e.target.closest('a[data-modal]'); if (!a || a.closest('.pg-modal') || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
    e.preventDefault();
    open(a.getAttribute('href'), { whole: a.hasAttribute('data-modal-whole'), stay: a.hasAttribute('data-modal-stay'), size: a.dataset.modalSize, title: a.dataset.modalTitle || a.textContent.trim() });
  });
  window.SLModal = { open };
})();
