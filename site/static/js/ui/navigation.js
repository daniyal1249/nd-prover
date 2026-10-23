/**
 * Site navigation
 *
 * Remembers the proof editor URL for this tab and keeps the current page
 * when its active navigation link is clicked. Modified clicks retain the
 * browser's usual behavior.
 *
 * Dependencies: none
 */

const STORAGE_KEY = 'proof-editor-url';

/**
 * Remembers the current editor URL and updates the navigation link.
 * On other pages, uses the editor URL saved for this tab.
 */
export function syncEditorLink() {
  const link = document.getElementById('nav-editor');
  let href = '/';

  try {
    if (window.location.pathname === '/') {
      href =
        `${window.location.pathname}${window.location.search}${window.location.hash}`;
      sessionStorage.setItem(STORAGE_KEY, href);
    } else {
      href = sessionStorage.getItem(STORAGE_KEY) || '/';
    }
  } catch (e) {
    // Storage may be unavailable; keep navigation working for this page.
  }

  if (link) {
    link.setAttribute('href', href);
  }
}

function initNavigation() {
  const nav = document.querySelector('.site-nav');
  if (!nav) {
    return;
  }

  syncEditorLink();

  nav.addEventListener('click', (e) => {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) {
      return;
    }

    const link = e.target.closest('a.active');
    if (link) {
      e.preventDefault();
    }
  });

  window.addEventListener('hashchange', syncEditorLink);
  // Cached navigation pages may still link to an older editor URL.
  window.addEventListener('pageshow', syncEditorLink);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initNavigation);
} else {
  initNavigation();
}
