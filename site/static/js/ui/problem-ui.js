/**
 * Problem UI Handlers
 * 
 * Handles UI interactions for problem creation, including input box
 * commit handlers and the create problem button.
 * 
 * Dependencies: state.js, utils/input-processing.js, proof/line-operations.js
 */

import { processFormula } from '../utils/input-processing.js';
import { addLine } from '../proof/line-operations.js';
import { updateGenerateButtonVisibility } from './proof-ui.js';
import {
  getLogicValue,
  resolveSemanticOptions,
  supportsProofEditor
} from '../utils/logic-mapping.js';
import { renderProblemSummary, splitPremisesTopLevel } from './problem-summary.js';
import { scheduleUrlUpdate } from '../utils/url-state.js';
import {
  RESULT_SOURCES,
  clearResults,
  clearValidityResult,
  setResultsMessage,
  startResultsProgress,
  stopResultsProgress
} from './results-ui.js';
import {
  VALIDITY_PROGRESS_MESSAGE,
  ValidityRequestError,
  buildProblemPayload,
  requestValidity
} from './validity-ui.js';

const VALIDITY_REQUEST_TIMEOUT = 12000;
const VALIDITY_ERROR_MESSAGE =
  'An error occurred while checking argument validity.';
const VALIDATION_ERROR_MESSAGE =
  'An error occurred while validating the problem.';

class ProblemValidationError extends Error {}

function hideAndClearProof(state) {
  const proofPane = document.getElementById('proof-pane');
  if (proofPane) {
    proofPane.classList.add('hidden');
  }

  const summary = document.getElementById('problem-summary');
  if (summary) {
    summary.textContent = '';
  }

  state.lines = [];
  state.nextId = 1;
  state.proofProblem = null;
  updateGenerateButtonVisibility(state);
}

/**
 * Commits an input box value to state, processing the text.
 * 
 * @param {HTMLElement} el - Input element
 * @param {string} target - Target property name in state.problemDraft
 * @param {Object} state - Application state object
 */
export function commitInputBox(el, target, state) {
  const raw = el.value || '';
  const processed = processFormula(raw);
  el.value = processed;
  state.problemDraft[target] = processed;
}

/**
 * Validates a problem setup with the backend.
 *
 * @param {Object} payload - Problem setup payload
 * @returns {Promise<Object>} Validation response
 */
async function validateProblemSetup(payload) {
  try {
    const response = await fetch('/api/validate-problem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new ProblemValidationError(
        data.message || VALIDATION_ERROR_MESSAGE
      );
    }

    return data;
  } catch (error) {
    if (error instanceof ProblemValidationError) {
      throw error;
    }
    throw new ProblemValidationError(VALIDATION_ERROR_MESSAGE);
  }
}

/**
 * Initializes problem UI handlers.
 * 
 * @param {Object} state - Application state object
 * @param {Function} renderProof - Function to render the proof
 * @returns {Object} Object containing DOM element references
 */

export function initProblemUI(state, renderProof) {
  const logicSelect = document.getElementById('logic');
  const firstOrderCheckbox = document.getElementById('first-order');
  const intuitionisticCheckbox = document.getElementById('intuitionistic');
  const semanticsContainer = document.getElementById('semantics-container');
  const domainSemanticsField = document.getElementById('domain-semantics-field');
  const equalitySemanticsField = document.getElementById('equality-semantics-field');
  const domainSemanticsSelect = document.getElementById('domain-semantics');
  const equalitySemanticsSelect = document.getElementById('equality-semantics');
  const premisesBox = document.getElementById('premises');
  const conclusionBox = document.getElementById('conclusion');
  const createBtn = document.getElementById('create-problem');
  const checkValidityBtn = document.getElementById('check-validity');
  const resultsSection = document.getElementById('results-pane');
  const resultsBox = document.getElementById('results');

  let setupRevision = 0;
  let isCheckingValidity = false;

  function markProblemSetupChanged() {
    setupRevision += 1;
    clearValidityResult(resultsSection, resultsBox);
  }

  function commitProblemSetup() {
    commitInputBox(premisesBox, 'premisesText', state);
    commitInputBox(conclusionBox, 'conclusionText', state);

    const baseLogic = logicSelect.value;
    const isFirstOrder = firstOrderCheckbox.checked;
    const isIntuitionistic = intuitionisticCheckbox.checked;
    const semantics = resolveSemanticOptions(
      baseLogic,
      isFirstOrder,
      isIntuitionistic,
      domainSemanticsSelect.value,
      equalitySemanticsSelect.value
    );

    state.problemDraft.logic = getLogicValue(
      baseLogic,
      isFirstOrder,
      isIntuitionistic
    );
    state.problemDraft.domainSemantics = semantics.domainSemantics;
    state.problemDraft.equalitySemantics = semantics.equalitySemantics;

    return buildProblemPayload(state.problemDraft);
  }

  function showValidationError(message) {
    setResultsMessage(
      resultsSection,
      resultsBox,
      message,
      'error',
      RESULT_SOURCES.validation
    );
  }

  // Input box handlers
  premisesBox.addEventListener('input', markProblemSetupChanged);
  premisesBox.addEventListener('blur', () => {
    commitInputBox(premisesBox, 'premisesText', state);
    scheduleUrlUpdate();
  });

  conclusionBox.addEventListener('input', markProblemSetupChanged);
  conclusionBox.addEventListener('blur', () => {
    commitInputBox(conclusionBox, 'conclusionText', state);
    scheduleUrlUpdate();
  });

  // Logic controls and semantic selector change handlers
  function updateLogic(configurationChanged = true) {
    const baseLogic = logicSelect.value;
    const isFirstOrder = firstOrderCheckbox.checked;
    const isIntuitionistic = intuitionisticCheckbox.checked;
    const semantics = resolveSemanticOptions(
      baseLogic,
      isFirstOrder,
      isIntuitionistic,
      domainSemanticsSelect.value,
      equalitySemanticsSelect.value
    );

    state.problemDraft.logic = getLogicValue(
      baseLogic,
      isFirstOrder,
      isIntuitionistic
    );
    state.problemDraft.domainSemantics = semantics.domainSemantics;
    state.problemDraft.equalitySemantics = semantics.equalitySemantics;

    domainSemanticsField.classList.toggle('hidden', !semantics.showDomain);
    equalitySemanticsField.classList.toggle('hidden', !semantics.showEquality);
    semanticsContainer.classList.toggle(
      'hidden',
      !semantics.showDomain && !semantics.showEquality
    );
    createBtn.classList.toggle(
      'hidden',
      !supportsProofEditor(baseLogic, isIntuitionistic)
    );

    if (configurationChanged) {
      markProblemSetupChanged();
    }

    updateGenerateButtonVisibility(state);
    scheduleUrlUpdate();
  }

  logicSelect.addEventListener('change', () => updateLogic());
  firstOrderCheckbox.addEventListener('change', () => updateLogic());
  intuitionisticCheckbox.addEventListener('change', () => updateLogic());
  domainSemanticsSelect.addEventListener('change', () => updateLogic());
  equalitySemanticsSelect.addEventListener('change', () => updateLogic());

  updateLogic(false);

  // Create problem button handler
  createBtn.addEventListener('click', async () => {
    const payload = commitProblemSetup();

    try {
      await validateProblemSetup(payload);
    } catch (error) {
      hideAndClearProof(state);
      scheduleUrlUpdate();
      showValidationError(error.message);
      return;
    }

    // At this point, validation succeeded; clear any previous results
    clearResults(resultsSection, resultsBox);

    // Reset proof editor state and commit the problem to the proof pane
    state.lines = [];
    state.nextId = 1;
    state.proofProblem = {
      logic: payload.logic,
      premisesText: payload.premisesText,
      conclusionText: payload.conclusionText,
      domainSemantics: payload.domainSemantics,
      equalitySemantics: payload.equalitySemantics
    };

    // Split premises on commas/semicolons at top level and add as PR lines
    const parts = splitPremisesTopLevel(payload.premisesText);

    // Proof-pane summary
    renderProblemSummary(
      document.getElementById('problem-summary'),
      state.proofProblem.logic,
      state.proofProblem.premisesText,
      state.proofProblem.conclusionText
    );

    // Create premise lines
    for (const p of parts) {
      const line = addLine(state, 0, null, false, true);
      line.text = p; // Already symbolized
      line.justText = 'PR'; // Show PR in justification column
    }

    // Reveal the proof section if hidden
    const proofPane = document.getElementById('proof-pane');
    if (proofPane && proofPane.classList.contains('hidden')) {
      proofPane.classList.remove('hidden');
    }

    // Update GENERATE button visibility based on logic
    updateGenerateButtonVisibility(state);

    renderProof();
    scheduleUrlUpdate();
  });

  // Check validity button handler
  checkValidityBtn.addEventListener('click', async () => {
    if (isCheckingValidity) {
      return;
    }

    isCheckingValidity = true;
    checkValidityBtn.disabled = true;

    hideAndClearProof(state);
    scheduleUrlUpdate();

    const requestRevision = setupRevision;
    const payload = commitProblemSetup();

    try {
      await validateProblemSetup(payload);
      if (requestRevision !== setupRevision) {
        return;
      }

      startResultsProgress(
        resultsSection,
        resultsBox,
        VALIDITY_PROGRESS_MESSAGE,
        RESULT_SOURCES.validity,
        '10s'
      );

      const data = await requestValidity(
        '/api/check-validity',
        payload,
        VALIDITY_REQUEST_TIMEOUT,
        VALIDITY_ERROR_MESSAGE
      );
      if (requestRevision !== setupRevision) {
        clearValidityResult(resultsSection, resultsBox);
        return;
      }

      let status = 'progress';
      if (data.outcome === 'valid') {
        status = 'success';
      } else if (data.outcome === 'invalid') {
        status = 'error';
      }

      setResultsMessage(
        resultsSection,
        resultsBox,
        data.message,
        status,
        RESULT_SOURCES.validity
      );
    } catch (error) {
      if (requestRevision !== setupRevision) {
        return;
      }

      if (error instanceof ProblemValidationError) {
        showValidationError(error.message);
      } else {
        const message = error instanceof ValidityRequestError
          ? error.message
          : VALIDITY_ERROR_MESSAGE;
        setResultsMessage(
          resultsSection,
          resultsBox,
          message,
          'error',
          RESULT_SOURCES.validity
        );
      }
    } finally {
      stopResultsProgress(resultsSection, resultsBox);
      isCheckingValidity = false;
      checkValidityBtn.disabled = false;
    }
  });

  return {
    logicSelect,
    firstOrderCheckbox,
    intuitionisticCheckbox,
    domainSemanticsSelect,
    equalitySemanticsSelect,
    premisesBox,
    conclusionBox
  };
}
