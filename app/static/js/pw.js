/* Eye icon on every password field: click to show / hide */
(function () {
  const EYE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  const OFF = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><path d="M1 1l22 22"/></svg>';
  document.querySelectorAll('input[type=password]').forEach(inp => {
    if (inp.dataset.eye) return; inp.dataset.eye = '1';
    const wrap = document.createElement('span'); wrap.className = 'pw-wrap';
    inp.parentNode.insertBefore(wrap, inp); wrap.appendChild(inp);
    const b = document.createElement('button'); b.type = 'button'; b.className = 'pw-eye'; b.innerHTML = EYE;
    b.setAttribute('aria-label', 'Show password'); b.title = 'Show password';
    b.addEventListener('click', () => {
      const show = inp.type === 'password'; inp.type = show ? 'text' : 'password'; b.innerHTML = show ? OFF : EYE;
      b.setAttribute('aria-label', show ? 'Hide password' : 'Show password'); b.title = show ? 'Hide password' : 'Show password'; inp.focus();
    });
    wrap.appendChild(b);
  });
})();
