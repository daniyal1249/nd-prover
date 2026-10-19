/**
 * Assistance Notice Dialog
 *
 * Shares the responsible-use notice and dismissal behavior between actions.
 * Dependencies: none
 */

/**
 * Opens the notice and returns one selected action, or null on dismissal.
 *
 * @param {'hint'|'validity'} mode - Action requesting assistance
 * @param {HTMLElement} opener - Control to focus after dismissal
 * @returns {Promise<string|null>} Selected action
 */
export function showAssistanceDialog(mode, opener) {
  const dialog = document.getElementById('assistance-dialog');
  if (!dialog || dialog.open) {
    return Promise.resolve(null);
  }

  const hint = mode === 'hint';
  dialog.querySelector('h2').textContent = hint ? 'Choose a hint' : 'Check argument validity';
  dialog.querySelector('.assistance-dialog__prompt').textContent = hint
    ? 'Choose whether to reveal the next formula or justification.'
    : 'Continue to check whether this argument is valid?';
  dialog.querySelector('.assistance-dialog__choices').classList.toggle('hidden', !hint);
  dialog.querySelector('[value="continue"]').classList.toggle('hidden', hint);
  dialog.returnValue = 'cancel';

  return new Promise((resolve) => {
    dialog.onkeydown = (e) => {
      if (e.key !== 'Tab') {
        return;
      }
      const buttons = Array.from(dialog.querySelectorAll('button'))
        .filter(button => button.getClientRects().length > 0);
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    dialog.onclick = (e) => {
      if (e.target !== dialog) {
        return;
      }
      const bounds = dialog.getBoundingClientRect();
      if (e.clientX < bounds.left || e.clientX > bounds.right ||
          e.clientY < bounds.top || e.clientY > bounds.bottom) {
        dialog.close('cancel');
      }
    };
    dialog.addEventListener('close', () => {
      dialog.onclick = null;
      dialog.onkeydown = null;
      resolve(dialog.returnValue === 'cancel' ? null : dialog.returnValue);
      requestAnimationFrame(() => {
        if (opener?.isConnected && !opener.disabled) {
          opener.focus({ preventScroll: true });
        }
      });
    }, { once: true });
    dialog.showModal();
  });
}
