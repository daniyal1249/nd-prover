/**
 * Expandable options control
 *
 * Clicking the toggle replaces it with its inline options.
 * Clicking anywhere outside restores the toggle.
 *
 * Dependencies: none
 */

export function initExpandableOptions(root, toggle, options) {
  if (!root || !toggle || !options) {
    return;
  }

  let isOpen = false;

  function open() {
    if (isOpen) return;
    isOpen = true;
    root.classList.add('is-open');
    toggle.setAttribute('aria-expanded', 'true');
    options.hidden = false;
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    root.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
    options.hidden = true;
  }

  toggle.addEventListener('click', (e) => {
    e.preventDefault();
    open();
  });

  document.addEventListener('click', (e) => {
    if (!isOpen) return;
    const target = e.target;
    if (target && (toggle.contains(target) || options.contains(target))) {
        return;
    }
    close();
  });

  document.addEventListener('keydown', (e) => {
    if (!isOpen) return;
    if (e.key === 'Escape') {
      close();
      toggle.focus({ preventScroll: true });
    }
  });

  return { close };
}
