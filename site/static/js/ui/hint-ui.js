/**
 * Hint UI Handlers
 *
 * Checks partial proofs, caches completions, and reveals one selected field.
 * Dependencies: proof/line-operations.js, proof/focus-management.js,
 *               proof/subproof-goals.js,
 *               utils/serialization.js, utils/input-processing.js,
 *               utils/requests.js, utils/url-state.js,
 *               ui/validity-ui.js, ui/assistance-dialog.js
 */

import { addLine } from '../proof/line-operations.js';
import { commitActiveEditor, focusLineAt } from '../proof/focus-management.js';
import { pulseMissingSubproofGoal } from '../proof/subproof-goals.js';
import { processFormula, processJustification } from '../utils/input-processing.js';
import { postJson } from '../utils/requests.js';
import { serializeHintState } from '../utils/serialization.js';
import { scheduleUrlUpdate } from '../utils/url-state.js';
import { showAssistanceDialog } from './assistance-dialog.js';
import {
  VALIDITY_PROGRESS_MESSAGE,
  ValidityRequestError,
  buildProblemPayload,
  requestCachedValidity
} from './validity-ui.js';
import {
  RESULT_SOURCES,
  clearResults,
  setResultsMessage,
  startResultsProgress,
  stopResultsProgress
} from './results-ui.js';

const HINT_REQUEST_TIMEOUT = 15000;
const HINT_ERROR_MESSAGE = 'An error occurred while requesting a hint.';

class HintError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/**
 * Sends the proof and goals for backend validation and completion.
 *
 * @param {Object} payload - Serialized proof and subproof goals
 * @returns {Promise<Object>} Completion response
 */
async function requestHint(payload) {
  const { response, data } = await postJson('/api/get-hint', payload, HINT_REQUEST_TIMEOUT);
  if (!response.ok || !data.ok) {
    throw new HintError(data.message || HINT_ERROR_MESSAGE, data.status);
  }
  if (!['success', 'failure', 'timeout', 'cached'].includes(data.outcome) ||
      typeof data.message !== 'string' ||
      (data.outcome === 'success' &&
        (!Array.isArray(data.lines) || !Array.isArray(data.goals)))) {
    throw new HintError('Invalid response from server.');
  }
  return data;
}

/**
 * Appends one hint, keeping ordinary lines incomplete for the user to finish.
 *
 * @param {Object} state - Application state object
 * @param {Object} completion - Cached completion response
 * @param {'formula'|'justification'} field - Selected hint field
 * @param {Function} renderProof - Function to render the proof
 */
function revealHint(state, completion, field, renderProof) {
  const index = state.lines.length;
  const next = completion.lines[index];
  const goal = completion.goals.find(g => g.lineNumber === index + 1);
  if (next.isAssumption && !goal?.formulaText) {
    throw new HintError('Invalid response from server.');
  }

  const line = addLine(state, next.indent, null, next.isAssumption, next.isPremise);
  if (next.isAssumption || field === 'formula') {
    line.text = processFormula(next.text);
  }
  if (next.isAssumption) {
    line.goal = processFormula(goal.formulaText);
  } else if (field === 'justification') {
    line.justText = processJustification(next.justText);
  }

  renderProof();
  scheduleUrlUpdate();
  focusLineAt(
    index, next.isAssumption || field === 'justification'
      ? 'formula-input' : 'justification-input', state
  );
}

/**
 * Initializes GET HINT without changing the proof-generation controls.
 *
 * @param {Object} state - Application state object
 * @param {Function} renderProof - Function to render the proof
 */
export function initHintUI(state, renderProof) {
  const button = document.getElementById('get-hint');
  const resultsSection = document.getElementById('results-pane');
  const resultsBox = document.getElementById('results');
  if (!button || !resultsBox) {
    return;
  }

  // Keep only the current completion, in memory until the page is reloaded.
  let completion = null;

  button.addEventListener('click', async () => {
    if (button.disabled || !state.proofProblem) {
      return;
    }
    button.disabled = true;
    commitActiveEditor(state, processFormula, processJustification);
    const problem = state.proofProblem;
    const payload = serializeHintState(state);
    const snapshot = JSON.stringify(payload);
    const lines = payload.lines;
    const settingsKey = JSON.stringify({
      ...buildProblemPayload(payload), derivedRules: payload.derivedRules
    });

    function isCurrent() {
      commitActiveEditor(state, processFormula, processJustification);
      return state.proofProblem === problem &&
        JSON.stringify(serializeHintState(state)) === snapshot;
    }

    function show(message, status) {
      setResultsMessage(
        resultsSection, resultsBox, message, status, RESULT_SOURCES.hint
      );
    }

    startResultsProgress(
      resultsSection, resultsBox, VALIDITY_PROGRESS_MESSAGE,
      RESULT_SOURCES.hint, '3s'
    );
    try {
      const validity = await requestCachedValidity(
        payload, 5000, HINT_ERROR_MESSAGE, 3000
      );
      if (!isCurrent() || resultsSection?.dataset.resultSource !== RESULT_SOURCES.hint) {
        return;
      }
      if (validity.outcome === 'invalid') {
        show('Argument is invalid!', 'error');
        return;
      }
      if (validity.outcome === 'unknown') {
        show('Argument validity unknown. Please try again.', 'neutral');
        return;
      }

      startResultsProgress(
        resultsSection, resultsBox, 'Checking the proof and completing the current goal...',
        RESULT_SOURCES.hint, '13s'
      );
      const cached = completion?.problem === problem &&
        completion.settingsKey === settingsKey &&
        lines.length >= completion.originalLength &&
        lines.length < completion.data.lines.length &&
        lines.every((line, index) => {
          const expected = completion.data.lines[index];
          return line.indent === expected.indent &&
            line.isAssumption === expected.isAssumption &&
            line.isPremise === expected.isPremise;
        }) ? completion.data : null;
      const response = await requestHint(cached ? {
        ...payload,
        cachedProof: { lines: cached.lines.slice(0, lines.length), goals: cached.goals }
      } : payload);
      if (isCurrent() && resultsSection?.dataset.resultSource === RESULT_SOURCES.hint) {
        if (response.outcome === 'cached' && !cached) {
          throw new HintError('Invalid response from server.');
        }
        const data = response.outcome === 'cached' ? cached : response;
        if (response.outcome !== 'cached') {
          completion = data.outcome === 'success' ? {
            problem, settingsKey, originalLength: lines.length, data
          } : null;
        }
        if (data.outcome !== 'success' || data.lines.length <= payload.lines.length) {
          show(data.message, data.outcome === 'success' ? 'success' : 'error');
          return;
        }
        clearResults(resultsSection, resultsBox);
        const field = await showAssistanceDialog('hint', button);
        if (!field || !isCurrent()) {
          return;
        }
        revealHint(state, data, field, renderProof);
      }
    } catch (error) {
      if (isCurrent() && resultsSection?.dataset.resultSource === RESULT_SOURCES.hint) {
        const message = error instanceof HintError || error instanceof ValidityRequestError
          ? error.message : HINT_ERROR_MESSAGE;
        show(message, 'error');
        if (error instanceof HintError && error.status === 'missing-goal') {
          pulseMissingSubproofGoal();
        }
      }
    } finally {
      if (resultsSection?.dataset.resultSource === RESULT_SOURCES.hint) {
        if (isCurrent()) {
          stopResultsProgress(resultsSection, resultsBox);
        } else {
          clearResults(resultsSection, resultsBox);
        }
      }
      button.disabled = false;
      if (document.activeElement === document.body) {
        button.focus({ preventScroll: true });
      }
    }
  });
}
