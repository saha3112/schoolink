(() => {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const progress = document.querySelector('.scroll-progress');
  let scheduled = false;
  function updateScroll() {
    const range = document.documentElement.scrollHeight - innerHeight;
    progress.style.transform = `scaleX(${range > 0 ? Math.min(1, Math.max(0, scrollY / range)) : 0})`;
    scheduled = false;
  }
  addEventListener('scroll', () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(updateScroll); }
  }, { passive: true });
  addEventListener('resize', updateScroll);
  updateScroll();
  if (!reducedMotion.matches && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.add('is-visible'); observer.unobserve(entry.target); }
    }), { threshold: .08 });
    document.querySelectorAll('[data-reveal]').forEach(element => {
      element.classList.add('reveal-pending'); observer.observe(element);
    });
  }
  const forgot = document.querySelector('.forgot-password');
  const guidance = document.querySelector('.reset-guidance');
  forgot.addEventListener('click', () => {
    const expanded = forgot.getAttribute('aria-expanded') !== 'true';
    forgot.setAttribute('aria-expanded', String(expanded));
    guidance.hidden = !expanded;
  });
})();
