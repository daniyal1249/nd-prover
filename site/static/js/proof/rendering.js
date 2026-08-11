/**
 * Proof Rendering
 * 
 * Functions for rendering the proof display, including dynamic width calculation,
 * DOM element creation, and event handler attachment.
 * 
 * Dependencies: state.js, utils/text-measurement.js, proof/line-operations.js,
 *               utils/input-processing.js, proof/focus-management.js
 */

import { textWidth, pxVar } from '../utils/text-measurement.js';
import { processFormula, processJustification } from '../utils/input-processing.js';
import { commitActiveEditor, focusLineAt } from './focus-management.js';
import { scheduleUrlUpdate } from '../utils/url-state.js';

/**
 * Computes the required width for the proof formula column based on content.
 * 
 * @param {Object} state - Application state object
 * @returns {number} Required width in pixels
 */
export function computeProofWidth(state) {
  const base = pxVar('--proof-formula-min-width');
  const theIndent = pxVar('--proof-indent');
  const gap = pxVar('--proof-text-gap');
  let maxW = 0;
  
  for (const line of state.lines) {
    const contentSpan = Math.max(base, line.text ? textWidth(line.text) : 0);
    const total = (line.indent * theIndent) + gap + contentSpan;
    if (total > maxW) {
      maxW = total;
    }
  }
  
  if (state.lines.length === 0) {
    maxW = base;
  }
  
  // Pad preserved from original
  return Math.ceil(maxW) + 50;
}

/**
 * Computes the required width for the justification column based on content.
 * 
 * @param {Object} state - Application state object
 * @returns {number} Required width in pixels (minimum 100px)
 */
export function computeJustWidth(state) {
  let maxJust = 0;
  for (const line of state.lines) {
    const w = line.justText ? textWidth(line.justText) : 0;
    if (w > maxJust) {
      maxJust = w;
    }
  }
  // Min 100 + buffer
  return Math.ceil(Math.max(100, maxJust)) + 10;
}

/**
 * Updates the visibility of the toolbar based on whether there are any lines.
 * 
 * @param {HTMLElement} toolbar - Toolbar element
 * @param {Object} state - Application state object
 */
export function updateToolbarVisibility(toolbar, state) {
  if (!toolbar) {
    return;
  }
  // Toolbar should be visible (flex) when there are no lines, hidden otherwise
  if (state.lines.length === 0) {
    toolbar.classList.remove('hidden');
  } else {
    toolbar.classList.add('hidden');
  }
}

/**
 * Creates vertical bars for subproof visualization.
 * 
 * @param {HTMLElement} container - Container element to add bars to
 * @param {number} depth - Depth/indent level
 * @param {boolean} capLast - Whether to cap the last bar (for assumptions)
 */
export function addBars(container, depth, capLast = false) {
  container.innerHTML = '';
  for (let i = 0; i <= depth; i++) {
    const bar = document.createElement('div');
    bar.className = 'bar';
    if (capLast && i === depth) {
      bar.classList.add('cap');
    }
    bar.style.left = `calc(${i} * var(--proof-indent))`;
    container.appendChild(bar);
  }
}

/**
 * Handles blur event logic: updates state and updates the input value in place.
 * Always updates in place to avoid unnecessary DOM recreation.
 * 
 * @param {HTMLElement} inputElement - The input element that was blurred
 * @param {string} processedText - The processed text to display
 * @param {Function} updateState - Function to update state with processed text
 */
function handleInputBlur(inputElement, processedText, updateState) {
  updateState(processedText);
  // Always update value in place to show processed text without recreating DOM
  inputElement.value = processedText;
}

/**
 * Creates a horizontal bar element for assumptions and premise separators.
 * 
 * @param {Object} line - Line object
 * @returns {HTMLElement} Horizontal bar element
 */
function createHorizontalBar(line) {
  const h = document.createElement('div');
  h.className = 'horizontal-bar';
  h.style.left = `calc(${line.indent} * var(--proof-indent))`;
  const base = pxVar('--horizontal-bar-length');
  const extra = pxVar('--horizontal-bar-extra-width');
  const width = line.text
    ? (textWidth(line.text) + pxVar('--proof-text-gap') + extra)
    : base;
  h.style.width = Math.max(base, width) + 'px';
  return h;
}

/**
 * Updates the width of the horizontal bar in a formula cell based on the current text.
 * Only updates if a horizontal bar exists (e.g., for assumption cells).
 * 
 * @param {HTMLElement} cell - The formula cell element
 * @param {string} text - The text to measure for bar width
 */
function updateHorizontalBarWidth(cell, text) {
  const horizontalBar = cell.querySelector('.horizontal-bar');
  if (!horizontalBar) {
    return;
  }
  
  const base = pxVar('--horizontal-bar-length');
  const extra = pxVar('--horizontal-bar-extra-width');
  const width = text ? (textWidth(text) + pxVar('--proof-text-gap') + extra) : base;
  horizontalBar.style.width = Math.max(base, width) + 'px';
}

/**
 * Creates the formula input cell with all its elements and event handlers.
 * 
 * @param {Object} line - Line object
 * @param {number} idx - Line index
 * @param {number} lineId - Stable line ID
 * @param {Object} state - Application state object
 * @returns {HTMLElement} Formula cell element
 */
function createFormulaCell(line, idx, lineId, state) {
  const cell = document.createElement('div');
  cell.className = 'formula-cell';

  // Bars
  const bars = document.createElement('div');
  bars.className = 'bars';
  addBars(bars, line.indent, line.isAssumption);
  cell.appendChild(bars);

  // Formula input
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'formula-input';
  const canEditFormula = !line.isPremise;
  input.disabled = !canEditFormula;
  input.spellcheck = false;
  input.value = line.text || '';
  
  // Position input absolutely to fill the cell
  input.style.position = 'absolute';
  input.style.top = '0';
  input.style.bottom = '0';
  input.style.left = '0';
  input.style.right = '0';
  input.style.zIndex = '1';
  
  // Set padding to fill cell and maintain text position based on indent
  const paddingLeft =
    `calc(var(--spacing-md) + ${line.indent} * var(--proof-indent) + ` + 
    `var(--proof-text-gap))`;
  const paddingRight = 'var(--spacing-md)';
  const paddingTop = 'var(--proof-row-padding-vertical)';
  const paddingBottom = 'var(--proof-row-padding-vertical)';
  input.style.paddingLeft = paddingLeft;
  input.style.paddingRight = paddingRight;
  input.style.paddingTop = paddingTop;
  input.style.paddingBottom = paddingBottom;

  if (!canEditFormula) {
    cell.classList.add('disabled');
  }

  // Input focus handler
  input.addEventListener('focus', () => {
    if (!canEditFormula) {
      return;
    }
    cell.classList.add('focused');
  });

  // Input blur handler
  input.addEventListener('blur', () => {
    if (!canEditFormula) {
      return;
    }
    cell.classList.remove('focused');
    const processed = processFormula(input.value || '');
    const i = state.lines.findIndex((l) => l.id === lineId);
    if (i === -1) {
      return;
    }
    
    if (state.lines[i].text === processed) {
      input.value = processed;
      updateHorizontalBarWidth(cell, processed);
      updateProofDimensions(state);
      scheduleUrlUpdate();
      return;
    }
    
    handleInputBlur(
      input,
      processed,
      (text) => { state.lines[i].text = text; }
    );
    
    updateHorizontalBarWidth(cell, processed);
    updateProofDimensions(state);
    scheduleUrlUpdate();
  });

  // Note: When clicking on a disabled input, the click event bubbles up to 
  // the cell container. The browser automatically blurs the currently focused 
  // element when clicking on a non-focusable element (the cell div), so no 
  // manual blur handler is needed here. The pointer-events: none on disabled 
  // inputs is useful for preventing the input from being the event target and 
  // for cursor behavior, but blur happens regardless due to event bubbling.

  cell.appendChild(input);

  return cell;
}

/**
 * Creates the justification cell with all its elements and event handlers.
 * 
 * @param {Object} line - Line object
 * @param {number} idx - Line index
 * @param {number} lineId - Stable line ID
 * @param {Object} state - Application state object
 * @returns {HTMLElement} Justification cell element
 */
function createJustificationCell(line, idx, lineId, state) {
  const just = document.createElement('div');
  just.className = 'justification-cell';

  const justInput = document.createElement('input');
  justInput.type = 'text';
  justInput.className = 'justification-input';
  const editable = !(line.isAssumption || line.isPremise);
  justInput.disabled = !editable;
  justInput.spellcheck = false;
  justInput.value = line.justText || '';
  
  // Position input absolutely to fill the cell
  justInput.style.position = 'absolute';
  justInput.style.top = '0';
  justInput.style.bottom = '0';
  justInput.style.left = '0';
  justInput.style.right = '0';
  justInput.style.zIndex = '1';

  const hasText = !!(line.justText && /\S/.test(line.justText));
  if (!editable) {
    just.classList.add('disabled');
  }
  if (hasText) {
    just.classList.add('filled');
  }

  // Justification focus handler
  justInput.addEventListener('focus', () => {
    if (!editable) {
      return;
    }
    just.classList.add('focused');
  });

  // Justification blur handler
  justInput.addEventListener('blur', () => {
    if (!editable) {
      return;
    }
    just.classList.remove('focused');
    const raw = justInput.value || '';
    const processed = raw ? processJustification(raw) : '';
    const i = state.lines.findIndex((l) => l.id === lineId);
    if (i === -1) {
      return;
    }
    
    if (state.lines[i].justText === processed) {
      justInput.value = processed;
      updateProofDimensions(state);
      scheduleUrlUpdate();
      return;
    }
    
    handleInputBlur(
      justInput,
      processed,
      (text) => {
        state.lines[i].justText = text;
        if (text) {
          just.classList.add('filled');
        } else {
          just.classList.remove('filled');
        }
      }
    );
    
    updateProofDimensions(state);
    scheduleUrlUpdate();
  });

  // Note: When clicking on a disabled input, the click event bubbles up to 
  // the cell container. The browser automatically blurs the currently focused 
  // element when clicking on a non-focusable element (the cell div), so no 
  // manual blur handler is needed here. The pointer-events: none on disabled 
  // inputs is useful for preventing the input from being the event target and 
  // for cursor behavior, but blur happens regardless due to event bubbling.

  just.appendChild(justInput);
  return just;
}

/**
 * Runs an action while preserving the page's current scroll position.
 *
 * @param {Function} action - Action to run
 */
function runPreservingScroll(action) {
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;

  action();

  requestAnimationFrame(() => {
    window.scrollTo(scrollX, scrollY);
  });
}

/**
 * Creates action buttons for a proof line.
 * 
 * @param {Object} line - Line object
 * @param {number} idx - Line index
 * @param {number} lastPremiseIndex - Index of the last premise
 * @param {Object} state - Application state object
 * @param {Function} deleteLineAt - Function to delete a line
 * @param {Function} addLineAfterSame - Function to add line after index
 * @param {Function} beginSubproofBelow - Function to begin subproof
 * @param {Function} endSubproofAt - Function to end subproof
 * @param {Function} endAndBeginAnotherAt - Function to end and begin subproof
 * @returns {HTMLElement} Actions container element
 */
function createActionButtons(
  line,
  idx,
  lastPremiseIndex,
  state,
  deleteLineAt,
  addLineAfterSame,
  beginSubproofBelow,
  endSubproofAt,
  endAndBeginAnotherAt
) {
  const actions = document.createElement('div');
  actions.className = 'line-actions';

  // Delete button
  const btnDel = document.createElement('button');
  btnDel.className = 'action-btn';
  btnDel.type = 'button';
  btnDel.title = 'Delete this line';
  btnDel.setAttribute('aria-label', 'Delete this line');
  btnDel.textContent = 'x';
  btnDel.addEventListener('click', (e) => {
    // e.preventDefault();
    // e.stopPropagation();
    // btnDel.blur();
    deleteLineAt(idx);
  });

  // Add line button
  const btnAdd = document.createElement('button');
  btnAdd.className = 'action-btn';
  btnAdd.type = 'button';
  btnAdd.title = 'Add a line below';
  btnAdd.setAttribute('aria-label', 'Add a line below');
  btnAdd.textContent = '↓';
  btnAdd.addEventListener('click', (e) => {
    // e.preventDefault();
    // e.stopPropagation();
    // btnAdd.blur();
    runPreservingScroll(() => addLineAfterSame(idx));
  });

  // Begin subproof button
  const btnSub = document.createElement('button');
  btnSub.className = 'action-btn';
  btnSub.type = 'button';
  btnSub.title = 'Begin a subproof below';
  btnSub.setAttribute('aria-label', 'Begin a subproof below');
  btnSub.textContent = '→';
  btnSub.addEventListener('click', (e) => {
    // e.preventDefault();
    // e.stopPropagation();
    // btnSub.blur();
    runPreservingScroll(() => beginSubproofBelow(idx));
  });

  // End subproof button
  const btnEnd = document.createElement('button');
  btnEnd.className = 'action-btn';
  btnEnd.type = 'button';
  btnEnd.title = 'End this subproof and add a line below';
  btnEnd.setAttribute('aria-label', 'End this subproof and add a line below');
  btnEnd.textContent = '←';
  btnEnd.addEventListener('click', (e) => {
    // e.preventDefault();
    // e.stopPropagation();
    // btnEnd.blur();
    runPreservingScroll(() => endSubproofAt(idx));
  });

  // End and begin another button
  const btnEndBegin = document.createElement('button');
  btnEndBegin.className = 'action-btn';
  btnEndBegin.type = 'button';
  btnEndBegin.title = 'End this subproof and begin another below';
  btnEndBegin.setAttribute('aria-label', 'End this subproof and begin another below');
  btnEndBegin.textContent = '↔';
  btnEndBegin.addEventListener('click', (e) => {
    // e.preventDefault();
    // e.stopPropagation();
    // btnEndBegin.blur();
    runPreservingScroll(() => endAndBeginAnotherAt(idx));
  });

  // Determine whether this line can "end" its subproof
  const next = state.lines[idx + 1];
  const canEndHere =
    !next ||
    next.indent < line.indent ||
    (next.indent === line.indent && next.isAssumption);

  // Add buttons based on line type
  if (line.isPremise) {
    if (idx === lastPremiseIndex) {
      actions.append(btnAdd, btnSub);
    }
  } else {
    actions.append(btnDel, btnAdd, btnSub);
    if (line.indent >= 1 && canEndHere) {
      actions.append(btnEnd, btnEndBegin);
    }
  }

  return actions;
}

/**
 * Creates a single proof line row with all its components.
 * 
 * @param {Object} line - Line object
 * @param {number} idx - Line index
 * @param {number} lastPremiseIndex - Index of the last premise
 * @param {Object} state - Application state object
 * @param {Function} deleteLineAt - Function to delete a line
 * @param {Function} addLineAfterSame - Function to add line after index
 * @param {Function} beginSubproofBelow - Function to begin subproof
 * @param {Function} endSubproofAt - Function to end subproof
 * @param {Function} endAndBeginAnotherAt - Function to end and begin subproof
 * @returns {HTMLElement} Proof line row element
 */
export function createProofLine(
  line,
  idx,
  lastPremiseIndex,
  state,
  deleteLineAt,
  addLineAfterSame,
  beginSubproofBelow,
  endSubproofAt,
  endAndBeginAnotherAt
) {
  const row = document.createElement('div');
  row.className = 'proof-line';
  row.dataset.index = idx;
  const lineId = line.id; // Stable id
  row.dataset.id = String(lineId);

  // Line number
  const ln = document.createElement('div');
  ln.className = 'line-number';
  ln.textContent = String(idx + 1);

  // Formula cell
  const cell = createFormulaCell(line, idx, lineId, state);

  // Horizontal bars for assumptions and premise separator
  if (line.isAssumption) {
    cell.appendChild(createHorizontalBar(line));
  }
  if (idx === lastPremiseIndex) {
    cell.appendChild(createHorizontalBar(line));
  }

  // Justification column
  const just = createJustificationCell(line, idx, lineId, state);

  // Actions column
  const actions = createActionButtons(
    line,
    idx,
    lastPremiseIndex,
    state,
    deleteLineAt,
    addLineAfterSame,
    beginSubproofBelow,
    endSubproofAt,
    endAndBeginAnotherAt
  );

  row.append(ln, cell, just, actions);
  return row;
}

/**
 * Updates CSS custom properties for proof dimensions.
 * 
 * @param {Object} state - Application state object
 */
export function updateProofDimensions(state) {
  const justW = computeJustWidth(state);
  document.documentElement.style.setProperty('--justification-width', justW + 'px');

  const proofW = computeProofWidth(state);
  document.documentElement.style.setProperty('--proof-formula-width', proofW + 'px');
}

/**
 * Removes a proof line element from the DOM.
 * 
 * @param {HTMLElement} row - The proof line row element to remove
 * @param {HTMLElement} proofRoot - Root element containing proof lines
 */
export function removeLineFromDOM(row, proofRoot) {
  if (row && row.parentNode === proofRoot) {
    row.remove();
  }
}

/**
 * Updates line number displays and dataset.index for all proof lines to match state.
 * 
 * @param {HTMLElement} proofRoot - Root element containing proof lines
 * @param {Object} state - Application state object
 */
export function updateLineNumbers(proofRoot, state) {
  const rows = Array.from(proofRoot.querySelectorAll('.proof-line'));
  
  // Create a map of line IDs to state indices
  const lineIdToIndex = new Map();
  state.lines.forEach((line, idx) => {
    lineIdToIndex.set(line.id, idx);
  });
  
  const activeElement = document.activeElement;
  if (
    activeElement &&
    (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')
  ) {
    const activeRow = activeElement.closest('.proof-line');
    if (activeRow) {
      activeElement.blur();
    }
  }

  // Update each row based on its line ID
  rows.forEach((row) => {
    const lineId = Number(row.dataset.id);
    const idx = lineIdToIndex.get(lineId);
    
    if (idx !== undefined) {
      row.dataset.index = String(idx);
      const lineNumber = row.querySelector('.line-number');
      if (lineNumber) {
        lineNumber.textContent = String(idx + 1);
      }
    }
  });
  
  // Reorder rows in DOM to match state order
  const sortedRows = rows.sort((a, b) => {
    const idxA = parseInt(a.dataset.index, 10);
    const idxB = parseInt(b.dataset.index, 10);
    return idxA - idxB;
  });
  
  sortedRows.forEach((row) => {
    proofRoot.appendChild(row);
  });
  
}

/**
 * Updates action button visibility for all proof lines based on current state.
 * 
 * @param {HTMLElement} proofRoot - Root element containing proof lines
 * @param {Object} state - Application state object
 * @param {Function} deleteLineAt - Function to delete a line
 * @param {Function} addLineAfterSame - Function to add line after index
 * @param {Function} beginSubproofBelow - Function to begin subproof
 * @param {Function} endSubproofAt - Function to end subproof
 * @param {Function} endAndBeginAnotherAt - Function to end and begin subproof
 */
export function updateActionButtons(
  proofRoot,
  state,
  deleteLineAt,
  addLineAfterSame,
  beginSubproofBelow,
  endSubproofAt,
  endAndBeginAnotherAt
) {
  const lastPremiseIndex = state.lines.reduce((acc, l, i) => l.isPremise ? i : acc, -1);
  const rows = proofRoot.querySelectorAll('.proof-line');
  
  rows.forEach((row) => {
    const idx = parseInt(row.dataset.index, 10);
    const line = state.lines[idx];
    if (!line) {
      return;
    }
    
    // Remove existing actions
    const oldActions = row.querySelector('.line-actions');
    if (oldActions) {
      oldActions.remove();
    }
    
    // Create new actions with updated state
    const actions = createActionButtons(
      line,
      idx,
      lastPremiseIndex,
      state,
      deleteLineAt,
      addLineAfterSame,
      beginSubproofBelow,
      endSubproofAt,
      endAndBeginAnotherAt
    );
    
    row.appendChild(actions);
  });
}

/**
 * Inserts a new proof line element into the DOM at the specified index.
 * 
 * @param {Object} state - Application state object
 * @param {number} idx - Index where to insert the line
 * @param {HTMLElement} proofRoot - Root element containing proof lines
 * @param {Function} deleteLineAt - Function to delete a line
 * @param {Function} addLineAfterSame - Function to add line after index
 * @param {Function} beginSubproofBelow - Function to begin subproof
 * @param {Function} endSubproofAt - Function to end subproof
 * @param {Function} endAndBeginAnotherAt - Function to end and begin subproof
 * @returns {HTMLElement} The newly created proof line row element
 */
export function insertLineInDOM(
  state,
  idx,
  proofRoot,
  deleteLineAt,
  addLineAfterSame,
  beginSubproofBelow,
  endSubproofAt,
  endAndBeginAnotherAt
) {
  const line = state.lines[idx];
  if (!line) {
    return null;
  }
  
  const lastPremiseIndex = state.lines.reduce((acc, l, i) => l.isPremise ? i : acc, -1);
  const row = createProofLine(
    line,
    idx,
    lastPremiseIndex,
    state,
    deleteLineAt,
    addLineAfterSame,
    beginSubproofBelow,
    endSubproofAt,
    endAndBeginAnotherAt
  );
  
  // Insert at correct position - find the row that should come after this one
  const existingRows = Array.from(proofRoot.querySelectorAll('.proof-line'));
  const nextRow = existingRows.find(r => {
    const rIdx = parseInt(r.dataset.index, 10);
    return rIdx >= idx;
  });
  
  if (nextRow) {
    proofRoot.insertBefore(row, nextRow);
  } else {
    proofRoot.appendChild(row);
  }
  
  return row;
}

/**
 * Renders the entire proof by creating DOM elements for each line.
 * This is only used for initial render and when creating a new problem.
 * 
 * @param {Object} state - Application state object
 * @param {HTMLElement} proofRoot - Root element for proof lines
 * @param {HTMLElement} toolbar - Toolbar element
 * @param {Function} deleteLineAt - Function to delete a line
 * @param {Function} addLineAfterSame - Function to add line after index
 * @param {Function} beginSubproofBelow - Function to begin subproof
 * @param {Function} endSubproofAt - Function to end subproof
 * @param {Function} endAndBeginAnotherAt - Function to end and begin subproof
 */
export function renderProof(
  state,
  proofRoot,
  toolbar,
  deleteLineAt,
  addLineAfterSame,
  beginSubproofBelow,
  endSubproofAt,
  endAndBeginAnotherAt
) {
  // Update dynamic widths
  updateProofDimensions(state);
  updateToolbarVisibility(toolbar, state);

  // Compute once, use inside the loop
  const lastPremiseIndex = state.lines.reduce((acc, l, i) => l.isPremise ? i : acc, -1);

  proofRoot.innerHTML = '';
  
  state.lines.forEach((line, idx) => {
    const row = createProofLine(
      line,
      idx,
      lastPremiseIndex,
      state,
      deleteLineAt,
      addLineAfterSame,
      beginSubproofBelow,
      endSubproofAt,
      endAndBeginAnotherAt
    );
    proofRoot.append(row);
  });
}
