/**
 * Subproof Goals
 *
 * Displays goal editors for open assumptions and retains goals when they close.
 * Dependencies: proof/line-operations.js, utils/input-processing.js, utils/url-state.js
 */

import { getOpenAssumptions } from './line-operations.js';
import { processFormula } from '../utils/input-processing.js';
import { scheduleUrlUpdate } from '../utils/url-state.js';

/**
 * Highlights the first empty open-subproof toggle until the next click anywhere.
 */
export function pulseMissingSubproofGoal() {
  const toggle = document.querySelector('#proof .subproof-goal-toggle:not(.has-goal)');
  if (!toggle) {
    return;
  }

  toggle.classList.add('needs-goal');
  document.addEventListener('click', () => {
    toggle.classList.remove('needs-goal');
  }, { capture: true, once: true });
}

/**
 * Creates a goal toggle and editor inside an assumption row.
 *
 * @param {HTMLElement} row - Assumption row
 * @param {Object} line - Assumption line object
 */
function createGoalControls(row, line) {
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'subproof-goal-toggle';
  toggle.setAttribute('aria-label', 'Toggle subproof goal');
  toggle.setAttribute('aria-controls', `subproof-goal-${line.id}`);

  const panel = document.createElement('div');
  panel.className = 'subproof-goal';
  panel.id = `subproof-goal-${line.id}`;
  panel.style.paddingLeft = `calc(${line.indent} * var(--proof-indent))`;

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'text-input subproof-goal-input';
  input.id = `subproof-goal-input-${line.id}`;
  input.setAttribute('aria-label', 'Subproof goal');
  input.placeholder = 'Enter the subproof goal';
  input.spellcheck = false;
  input.value = line.goal || '';

  function update() {
    const hasGoal = /\S/.test(line.goal || '');
    toggle.classList.toggle('has-goal', hasGoal);
    toggle.title = hasGoal ? 'Subproof goal specified' : 'Specify the subproof goal';
    toggle.setAttribute('aria-expanded', String(!!line.goalExpanded));
    panel.hidden = !line.goalExpanded;
  }

  toggle.addEventListener('click', () => {
    line.goalExpanded = !line.goalExpanded;
    update();
    if (line.goalExpanded) {
      input.focus({ preventScroll: true });
    }
  });

  input.addEventListener('input', () => {
    line.goal = input.value;
    update();
    scheduleUrlUpdate();
  });

  input.addEventListener('blur', () => {
    line.goal = processFormula(input.value || '');
    input.value = line.goal;
    update();
    scheduleUrlUpdate();
  });

  input.addEventListener('keydown', (e) => {
    if (e.isComposing) {
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      input.blur();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      line.goalExpanded = false;
      toggle.focus({ preventScroll: true });
      update();
    }
  });

  panel.appendChild(input);
  row.append(toggle, panel);
  update();
}

/**
 * Updates goal controls after rendering or editing the proof structure.
 *
 * @param {HTMLElement} proofRoot - Root element containing proof lines
 * @param {Object} state - Application state object
 */
export function updateSubproofGoals(proofRoot, state) {
  const open = new Map(getOpenAssumptions(state.lines).map(line => [line.id, line]));
  proofRoot.querySelectorAll('.proof-line').forEach((row) => {
    const line = open.get(Number(row.dataset.id));
    const toggle = row.querySelector('.subproof-goal-toggle');
    if (!line) {
      toggle?.remove();
      row.querySelector('.subproof-goal')?.remove();
    } else if (!toggle) {
      createGoalControls(row, line);
    }
  });
}
