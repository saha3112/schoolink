/* Colour-codes action buttons from their label, everywhere (tables, cards, pop-ups), so Edit / Delete / Restore /
   Delete permanently / View look the same on every page without touching each template. */
(() => {
  const RULES = [
    [/^(delete\s+(permanently|forever)|permanent|purge)/i, 'purge'],
    [/^restore/i, 'restore'],
    [/^(delete|remove|trash|move to trash)\b/i, 'delete'],
    [/^(edit|manage|rename|change|modify|set)\b/i, 'edit'],
    [/^(view|open|preview|download|export|see)\b/i, 'view'],
  ];
  const SKIP = '.primary,.act,[data-no-act],.icon-btn,.ps-btn,.ps-opt,.sl-pager button,.modal-x,.pager a,.tabs a';
  const label = el => (el.getAttribute('aria-label') || el.textContent || '').replace(/\s+/g, ' ').trim();
  function tag(root) {
    (root || document).querySelectorAll('.btn,td button,td a.btn').forEach(el => {
      if (el.matches(SKIP) || el.closest('.ps-pop,[data-media-picker]')) return;
      const t = label(el); if (!t || t.length > 42) return;
      for (const [re, kind] of RULES) if (re.test(t)) { el.classList.add('act', 'act-' + kind); return; }
    });
  }
  let timer = null; const later = () => { clearTimeout(timer); timer = setTimeout(() => tag(), 100); };
  document.addEventListener('DOMContentLoaded', () => tag());
  if (document.readyState !== 'loading') tag();
  addEventListener('sl:live-updated', later); addEventListener('sl:soft-nav', later);
  new MutationObserver(later).observe(document.documentElement, { childList: true, subtree: true });   // pop-ups and lists drawn by script
  window.slTagActions = tag;
})();
