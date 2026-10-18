/**
 * Theme toggle
 *
 * Switches between light and dark mode and persists the choice in
 * localStorage. The initial theme is applied by an inline script in
 * _layout.html before stylesheets load, so there is no flash of the
 * wrong theme; this module only wires up the button and keeps tabs in sync.
 *
 * Dependencies: none
 */

const STORAGE_KEY = 'theme';
const THEMES = new Set(['light', 'dark']);

function currentTheme() {
  const value = document.documentElement.getAttribute('data-theme');
  return value === 'dark' ? 'dark' : 'light';
}

function applyTheme(theme, toggle) {
  document.documentElement.setAttribute('data-theme', theme);

  if (toggle) {
    const label = theme === 'dark'
      ? 'Switch to light mode'
      : 'Switch to dark mode';
    toggle.setAttribute('aria-label', label);
    toggle.setAttribute('title', label);
  }
}

function saveTheme(theme) {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch (e) {
    // Storage may be unavailable (private mode, disabled cookies); the
    // theme still applies for this page.
  }
}

function readStoredTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return THEMES.has(stored) ? stored : 'light';
  } catch (e) {
    return 'light';
  }
}

function initThemeToggle() {
  const toggle = document.getElementById('theme-toggle');
  if (!toggle) {
    return;
  }

  applyTheme(currentTheme(), toggle);

  toggle.addEventListener('click', () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    applyTheme(next, toggle);
    saveTheme(next);
  });

  // Keep other open tabs in sync when the theme changes.
  window.addEventListener('storage', (e) => {
    if (e.key !== STORAGE_KEY) {
      return;
    }
    const theme = THEMES.has(e.newValue) ? e.newValue : 'light';
    applyTheme(theme, toggle);
  });

  // A page restored from the back/forward cache missed any storage events
  // fired while it was frozen, so re-read the saved theme on restore.
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) {
      applyTheme(readStoredTheme(), toggle);
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initThemeToggle);
} else {
  initThemeToggle();
}
