/* Real-time sync: other people's changes show up here without a refresh.
   - every logged-in page asks /live/poll every few seconds (only while the tab is visible);
   - when an event concerns this page (or changes what the user may see - assignments, classes) the page is re-read in the
     background and merged:
       * [data-live-html="name"] blocks are replaced when nothing inside is being edited (the sidebar menu is one of them);
       * form fields you have NOT touched take the new value (and flash); fields you ARE editing are left alone and marked.
   - if the change takes away your access to this page you are taken back to the dashboard with a notice. */
(function () {
  const main = document.querySelector('main.content'); if (!main || !main.hasAttribute('data-live-since')) return;
  const topics = (main.dataset.liveTopics || '').split(',').filter(Boolean);
  const GLOBAL = ['admin', 'students'];                               // can change menus / scopes -> every page re-checks
  let last = parseInt(main.dataset.liveSince || '0', 10) || 0, busy = false, again = false, timer = null, fails = 0, debounce = null;
  const SKIP = new Set(['hidden', 'file', 'password', 'submit', 'button', 'checkbox', 'radio', 'search']);
  const tracked = el => el.name && !SKIP.has(el.type) && el.name !== 'csrf_token' && !el.closest('#tsPanel,.sl-modal,.mp-modal,#viewer');
  const fields = () => Array.from(main.querySelectorAll('input[name],textarea[name],select[name]')).filter(tracked);
  fields().forEach(el => { el.dataset.orig = el.value; });
  main.addEventListener('input', e => { if (e.target.dataset && 'orig' in e.target.dataset && e.target.value !== e.target.dataset.orig) e.target.classList.remove('live-conflict'); });

  const flash = el => { el.classList.remove('live-flash'); void el.offsetWidth; el.classList.add('live-flash'); };
  const editing = el => el.contains(document.activeElement) && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  const norm = h => h.replace(/\s+/g, ' ').trim();
  const hrefs = el => Array.from(el.querySelectorAll('a[href]')).map(a => a.getAttribute('href')).join('|');

  function swapNav(el, n) {
    if (hrefs(el) === hrefs(n)) return 0;                              // same menu -> leave it (keeps the groups you opened)
    const open = new Set(Array.from(el.querySelectorAll('.sb-group.open > .sb-parent')).map(b => b.textContent.trim()));
    el.innerHTML = n.innerHTML;
    el.querySelectorAll('.sb-group').forEach(g => { const b = g.querySelector(':scope > .sb-parent'); if (b && open.has(b.textContent.trim())) g.classList.add('open'); });
    flash(el); return 1;
  }

  async function refresh() {
    if (busy) { again = true; return; }
    busy = true;
    try {
      const r = await fetch(location.href, { credentials: 'same-origin', headers: { 'X-Live': '1' } });
      if (r.status === 403 || r.status === 404) {                      // access to this page was taken away
        if (window.slToast) slToast('warning', 'Your access to this page has changed. Taking you back to the dashboard.');
        setTimeout(() => { location.href = '/dashboard'; }, 1800); return;
      }
      if (!r.ok || (r.redirected && /\/login/.test(r.url))) return;
      const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      let changed = 0;
      document.querySelectorAll('[data-live-html]').forEach(el => {
        if (el.closest('.sl-modal,.mp-modal')) return;
        const n = doc.querySelector('[data-live-html="' + el.dataset.liveHtml + '"]');
        if (!n || editing(el)) return;
        if (el.dataset.liveHtml === 'nav') { changed += swapNav(el, n); return; }
        if (norm(el.innerHTML) !== norm(n.innerHTML)) {
          el.innerHTML = n.innerHTML; flash(el); changed++;
          if (window.slUpgradeConfirm) slUpgradeConfirm(el);
          if (window.slPretty) slPretty.init();
        }
      });
      fields().forEach(el => {
        const n = doc.querySelector(el.tagName.toLowerCase() + '[name="' + (window.CSS && CSS.escape ? CSS.escape(el.name) : el.name) + '"]');
        if (!n) return;
        const untouched = el.value === (el.dataset.orig != null ? el.dataset.orig : el.value);
        if (n.value === el.dataset.orig) return;
        if (untouched) { el.value = n.value; el.dataset.orig = n.value; flash(el); changed++; }
        else if (!el.classList.contains('live-conflict')) { el.classList.add('live-conflict'); el.title = 'Someone else changed this to “' + n.value + '”. Your edit is kept until you save.'; }
      });
      if (changed) window.dispatchEvent(new CustomEvent('sl:live-updated', { detail: { changed } }));
    } catch (e) { /* offline - try again later */ } finally { busy = false; if (again) { again = false; schedule(); } }
  }
  const schedule = () => { clearTimeout(debounce); debounce = setTimeout(refresh, 350); };
  window.slLiveRefresh = schedule;

  const relevant = ev => {
    if (GLOBAL.includes(ev.t)) return true;
    if (!topics.includes(ev.t)) return false;
    if (ev.c && main.dataset.liveClass && String(ev.c) !== main.dataset.liveClass) return false;
    if (ev.s && main.dataset.liveSection && String(ev.s) !== main.dataset.liveSection) return false;
    return true;
  };
  async function poll() {
    if (document.hidden) { timer = setTimeout(poll, 4000); return; }
    try {
      const r = await fetch('/live/poll?since=' + last, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (r.status === 401 || r.status === 403 || r.redirected) { return; }
      const d = await r.json(); fails = 0; last = d.last || last;
      if (d.events && d.events.length) {
        window.dispatchEvent(new CustomEvent('sl:live-events', { detail: d.events }));
        if (d.events.some(relevant)) schedule();
      }
    } catch (e) { fails = Math.min(fails + 1, 5); }
    timer = setTimeout(poll, 2500 + fails * 2500);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { clearTimeout(timer); poll(); } });
  timer = setTimeout(poll, 1500);
})();
