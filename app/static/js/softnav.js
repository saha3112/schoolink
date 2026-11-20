/* Soft page updates for class / section / exam dropdowns (and other GET filter forms).
   Instead of reloading the whole page, the new content is fetched in the background and swapped into <main>.
   - only pages without page-specific scripts take part (body[data-soft="1"]); everything else reloads as before;
   - only the same page with different filters (same path) is updated this way;
   - any problem (network, redirect, login, different page) falls back to a normal page load;
   - URL and Back / Forward keep working. Nothing is polled and nothing extra is loaded. */
(function () {
  const main = document.querySelector('main.content');
  if (!main || !window.fetch || !window.DOMParser) return;
  const eligible = el => !!(el && el.body && el.body.dataset.soft === '1');
  let ctl = null, seq = 0;

  const bar = document.createElement('div'); bar.className = 'soft-bar'; bar.hidden = true; document.body.appendChild(bar);
  const busy = on => { main.classList.toggle('soft-loading', on); bar.hidden = !on; };

  function targetFor(form) {
    if (!eligible(document) || !main.contains(form) || (form.method || 'get').toLowerCase() !== 'get' || form.hasAttribute('data-no-soft') || form.target) return null;
    const url = new URL(form.getAttribute('action') || location.href, location.href);
    if (url.origin !== location.origin || url.pathname !== location.pathname) return null;
    const params = new URLSearchParams();
    new FormData(form).forEach((v, k) => { if (typeof v === 'string') params.append(k, v); });
    url.search = params.toString();
    return url.pathname + url.search;
  }

  function csvButton() { return main.querySelector('button.csv-open'); }

  function formState() {                                                    // the field being typed in, to put the caret back after the swap
    const a = document.activeElement;
    if (!a || !main.contains(a) || !/^(INPUT|TEXTAREA)$/.test(a.tagName) || !a.name || !a.form) return null;
    return { fi: Array.from(main.querySelectorAll('form')).indexOf(a.form), name: a.name, value: a.value, s: a.selectionStart, e: a.selectionEnd };
  }
  function restoreState(st) {
    if (!st || st.fi < 0) return;
    const f = main.querySelectorAll('form')[st.fi], el = f && f.elements[st.name]; if (!el || el.disabled) return;
    const typedMore = el.value !== st.value; el.value = st.value;
    try { el.focus({ preventScroll: true }); if (st.s != null) el.setSelectionRange(st.s, st.e); } catch (e) {}
    if (typedMore) typed(el);                                                 // the user kept typing while we were loading: catch up
  }

  function apply(doc, url, mode) {
    const next = doc.querySelector('main.content');
    const active = document.activeElement, picks = Array.from(main.querySelectorAll('#picker .ps-btn')), idx = picks.indexOf(active);
    const fs = formState();
    const keep = csvButton(); if (keep) keep.remove();                       // the Import CSV button is added by script, keep it
    main.innerHTML = next.innerHTML;
    ['data-live-topics', 'data-live-class', 'data-live-section'].forEach(a => { if (next.hasAttribute(a)) main.setAttribute(a, next.getAttribute(a)); else main.removeAttribute(a); });
    if (keep) { let box = main.querySelector('.page-head .h-actions'); const head = main.querySelector('.page-head');
      if (!box && head) { box = document.createElement('div'); box.className = 'h-actions'; head.appendChild(box); }
      if (box) box.appendChild(keep); }
    document.title = doc.title || document.title;
    if (mode === 'push') history.pushState({ soft: 1 }, '', url); else if (mode === 'replace') history.replaceState({ soft: 1 }, '', url);
    if (window.slAddCsrf) slAddCsrf(main);
    if (window.slPretty) slPretty.init();
    if (window.slUpgradeConfirm) slUpgradeConfirm(main);
    window.dispatchEvent(new CustomEvent('sl:live-updated', { detail: { changed: 1, soft: true } }));   // tables, sticky headers, alignment
    window.dispatchEvent(new CustomEvent('sl:soft-nav', { detail: { url } }));
    restoreState(fs);
    const again = main.querySelectorAll('#picker .ps-btn'); if (idx >= 0 && again[idx]) { try { again[idx].focus({ preventScroll: true }); } catch (e) {} }
  }

  async function go(url, mode) {
    const my = ++seq; if (ctl) ctl.abort(); ctl = new AbortController(); busy(true);
    const hard = () => { location.href = url; };
    try {
      const r = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' }, signal: ctl.signal });
      if (my !== seq) return;
      const sameFinal = (() => { try { return new URL(r.url).pathname === location.pathname; } catch (e) { return false; } })();
      if (!r.ok || !sameFinal || !/text\/html/.test(r.headers.get('content-type') || '')) { hard(); return; }
      const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      if (my !== seq) return;
      if (!doc.querySelector('main.content') || !eligible(doc)) { hard(); return; }
      apply(doc, r.url ? new URL(r.url).pathname + new URL(r.url).search : url, mode);
    } catch (e) { if (e.name !== 'AbortError') hard(); }
    finally { if (my === seq) busy(false); }
  }

  /* inline handlers such as onchange="this.form.submit()" call form.submit(), which fires no event: wrap it */
  const nativeSubmit = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function () {
    const url = targetFor(this);
    if (url) { go(url, 'push'); return; }
    return nativeSubmit.call(this);
  };
  /* pressing Enter in a filter box (real submit event) */
  document.addEventListener('submit', e => {
    if (e.defaultPrevented) return;
    const url = targetFor(e.target); if (!url) return;
    e.preventDefault(); clearTimeout(typeTimer); go(url, 'push');
  });
  window.addEventListener('popstate', () => { if (eligible(document)) go(location.pathname + location.search, 'none'); else location.reload(); });
  window.slSoftGo = url => go(url, 'push');

  /* page links of a list (1 2 3 ...) */
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('.pager a[href],.sl-pager a[href]');
    if (!a || e.defaultPrevented || e.button || e.ctrlKey || e.metaKey || e.shiftKey || a.target || !main.contains(a) || !eligible(document)) return;
    const u = new URL(a.href, location.href); if (u.origin !== location.origin || u.pathname !== location.pathname) return;
    e.preventDefault(); go(u.pathname + u.search, 'push');
  });

  /* type in a search box and the results follow (no Search button needed) */
  let typeTimer = null;
  function typed(el) {
    const form = el.form, url = form && targetFor(form); if (!url) return;
    clearTimeout(typeTimer); typeTimer = setTimeout(() => go(url, 'replace'), 320);
  }
  document.addEventListener('input', e => {
    const el = e.target;
    if (e.isComposing || !(el instanceof HTMLInputElement) || !main.contains(el) || !el.form) return;
    if (el.name === 'q' || el.type === 'search') typed(el);
  });
})();
