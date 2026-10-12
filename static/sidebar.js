/* Shared navigation visibility for every application route. */
(() => {
  const key = 'paradas.sidebar.hidden';
  let collapsed = false;
  try { collapsed = localStorage.getItem(key) === 'true'; } catch (_) { /* Storage may be unavailable. */ }
  document.documentElement.classList.add('sidebar-enabled');
  document.documentElement.classList.toggle('sidebar-collapsed', collapsed);

  document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.querySelector('body > .sidebar');
    if (!sidebar) return;
    sidebar.id = sidebar.id || 'app-sidebar';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'sidebar-toggle';
    button.setAttribute('aria-controls', sidebar.id);
    document.body.prepend(button);
    function update() {
      document.documentElement.classList.toggle('sidebar-collapsed', collapsed);
      sidebar.hidden = collapsed;
      button.setAttribute('aria-expanded', String(!collapsed));
      button.setAttribute('aria-label', collapsed ? 'Exibir menu lateral' : 'Ocultar menu lateral');
      button.title = collapsed ? 'Exibir menu lateral' : 'Ocultar menu lateral';
      button.innerHTML = '<span aria-hidden="true">☰</span> ' + (collapsed ? 'Exibir menu' : 'Ocultar menu');
    }
    button.addEventListener('click', () => {
      collapsed = !collapsed;
      try { localStorage.setItem(key, String(collapsed)); } catch (_) { /* The toggle still works. */ }
      update();
      requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    });
    update();
  });
})();
