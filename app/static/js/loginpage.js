/* Sign-in page editor: live preview, colour pickers, device size, picture previews. */
(() => {
  const form = document.getElementById('lpForm'), frame = document.getElementById('lpFrame'), iframe = document.getElementById('lpPreview');
  if (!form || !iframe) return;
  const csrf = () => { const m = document.querySelector('meta[name=csrf]'); return m ? m.content : ''; };
  const HEX = /^#[0-9a-fA-F]{6}$/;
  const pending = {};                                        // slot -> object URL of a picture picked but not saved yet
  let timer = null, seq = 0, mode = 'desktop';

  /* colour picker <-> hex box */
  form.querySelectorAll('input[type=color][data-pair]').forEach(pick => {
    const txt = form.elements[pick.dataset.pair]; if (!txt) return;
    pick.addEventListener('input', () => { txt.value = pick.value; txt.classList.remove('bad'); schedule(); });
    txt.addEventListener('input', () => { const v = txt.value.trim(); const ok = HEX.test(v); txt.classList.toggle('bad', !ok); if (ok) { pick.value = v; schedule(); } });
  });
  document.getElementById('lpColorsReset').addEventListener('click', () => {
    form.querySelectorAll('input[data-default]').forEach(t => { t.value = t.dataset.default; t.classList.remove('bad'); const p = form.querySelector('input[type=color][data-pair="' + t.name + '"]'); if (p) p.value = t.dataset.default; });
    schedule();
  });
  const bg = form.elements.bg_strength; if (bg) bg.addEventListener('input', () => { bg.nextElementSibling.textContent = bg.value + '%'; });

  /* pictures: show the chosen file at once (stored only when saved) */
  form.querySelectorAll('input[type=file][data-slot-file]').forEach(inp => inp.addEventListener('change', () => {
    const slot = inp.dataset.slotFile, f = inp.files && inp.files[0];
    if (pending[slot]) URL.revokeObjectURL(pending[slot]); delete pending[slot];
    if (f && /^image\//.test(f.type)) {
      pending[slot] = URL.createObjectURL(f);
      const th = inp.closest('.lp-img').querySelector('.lp-thumb'); th.classList.remove('empty'); th.innerHTML = '<img alt="">'; th.firstChild.src = pending[slot];
    }
    applyPending();
  }));
  function applyPending() {
    let d; try { d = iframe.contentDocument; } catch (e) { return; }
    if (!d) return;
    if (pending.logo) d.querySelectorAll('.lg img').forEach(i => { i.src = pending.logo; i.style.display = ''; });
    if (pending.art) d.querySelectorAll('.education-art img').forEach(i => { i.src = pending.art; });
    if (pending.bg) { d.body.style.background = 'linear-gradient(125deg,#ffffff8c,#ffffff8c),url(' + pending.bg + ') center/cover fixed'; }
  }

  /* device size: the page is drawn at a real width and scaled down to fit the preview box */
  function fit() {
    const w = mode === 'phone' ? 390 : 1360, h = mode === 'phone' ? 820 : 860;
    const box = frame.clientWidth || 480, k = Math.min(1, box / w);
    iframe.style.width = w + 'px'; iframe.style.height = h + 'px'; iframe.style.transform = 'scale(' + k + ')';
    const maxW = mode === 'phone' ? Math.min(box, 300) : box;
    frame.style.width = mode === 'phone' ? Math.round(w * Math.min(k, maxW / w)) + 'px' : '100%';
    frame.style.height = Math.round(h * (mode === 'phone' ? Math.min(k, maxW / w) : k)) + 'px';
    if (mode === 'phone') iframe.style.transform = 'scale(' + Math.min(k, maxW / w) + ')';
    frame.style.margin = mode === 'phone' ? '0 auto' : '0';
  }
  document.querySelectorAll('.lp-modes button').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.lp-modes button').forEach(x => x.classList.toggle('on', x === b)); mode = b.dataset.mode; fit();
  }));
  addEventListener('resize', fit);

  /* live preview: the server renders the page with the unsaved values */
  async function render() {
    const my = ++seq, fd = new FormData();
    new FormData(form).forEach((v, k) => { if (typeof v === 'string') fd.append(k, v); });
    try {
      const r = await fetch(form.dataset.preview, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf() } });
      if (my !== seq || !r.ok) return;
      iframe.onload = () => { applyPending(); };
      iframe.srcdoc = await r.text();
    } catch (e) { /* offline: keep the last preview */ }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(render, 350); }
  form.addEventListener('input', e => { if (e.target.type !== 'file') schedule(); });
  form.addEventListener('change', e => { if (e.target.type !== 'file') schedule(); });
  fit(); render();
})();
