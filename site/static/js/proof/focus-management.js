/**
 * Focus Management
 * 
 * Functions for managing focus and cursor position in proof line inputs.
 * 
 * Dependencies: None
 */

/**
 * Commits the currently active editor's content to state.
 * Handles formula inputs, justification inputs, and subproof goal inputs.
 * 
 * @param {Object} state - Application state object
 * @param {Function} processFormula - Function to process formula text
 * @param {Function} processJustification - Function to process justification text
 */
export function commitActiveEditor(state, processFormula, processJustification) {
  const ae = document.activeElement;
  if (!ae || (ae.tagName !== 'INPUT' && ae.tagName !== 'TEXTAREA')) {
    return;
  }

  const row = ae.closest('.proof-line');
  if (!row) {
    return;
  }

  const lineId = Number(row.dataset.id);
  const idx = state.lines.findIndex((l) => l.id === lineId);
  if (idx === -1) {
    return;
  }

  const val = ae.value || '';
  if (ae.classList.contains('formula-input')) {
    state.lines[idx].text = processFormula(val);
  } else if (ae.classList.contains('justification-input')) {
    state.lines[idx].justText = val ? processJustification(val) : '';
  } else if (ae.classList.contains('subproof-goal-input')) {
    state.lines[idx].goal = processFormula(val);
  }
}

/**
 * Focuses a specific line at the given index and positions cursor at end.
 * Uses lineId from state as fallback if data-index lookup fails
 * (e.g., during DOM updates).
 * 
 * @param {number} index - Index of the line to focus
 * @param {string} field - Field to focus ('formula-input' or 'justification-input')
 * @param {Object} state - Optional state object for fallback lookup by lineId
 */
export function focusLineAt(index, field = 'formula-input', state = null) {
  requestAnimationFrame(() => {
    // Try to find element by data-index first
    let el = document.querySelector(`.proof-line[data-index="${index}"] .${field}`);
    
    // If not found and state is provided, try finding by lineId as fallback
    if (!el && state && state.lines && index >= 0 && index < state.lines.length) {
      const line = state.lines[index];
      if (line) {
        const lineId = line.id;
        const row = document.querySelector(`.proof-line[data-id="${lineId}"]`);
        if (row) {
          el = row.querySelector(`.${field}`);
        }
      }
    }
    
    if (!el) {
      return;
    }
    el.focus({ preventScroll: true });
    
    // Position cursor at end of content
    if (el.setSelectionRange) {
      const len = el.value.length;
      el.setSelectionRange(len, len);
    }
    
    // Add focused class to container
    const container = el.closest(
      field === 'formula-input' ? '.formula-cell' : '.justification-cell'
    );
    if (container) {
      container.classList.add('focused');
    }
  });
}
