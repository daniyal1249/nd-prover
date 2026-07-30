/**
 * Proof UI Handlers
 * 
 * Handles UI interactions for the proof editor, including toolbar buttons.
 * 
 * Dependencies: state.js, proof/line-operations.js, proof/focus-management.js
 */

import { addLine } from '../proof/line-operations.js';
import { focusLineAt } from '../proof/focus-management.js';
import { serializeProofState } from '../utils/serialization.js';
import { processFormula, processJustification } from '../utils/input-processing.js';
import { scheduleUrlUpdate } from '../utils/url-state.js';

const GENERATION_REQUEST_TIMEOUTS = {
  validity: 3000,
  exhaustive: 7000,
  fast: 6000,
};

const GENERATION_ERROR_MESSAGE =
  'An error occurred while generating the proof.';
const INVALID_GENERATION_RESPONSE_MESSAGE =
  'Invalid response from server.';

class GenerationError extends Error {}

/**
 * Updates the visibility of the GENERATE button.
 * 
 * @param {Object} state - Application state object
 */
export function updateGenerateButtonVisibility(state) {
  const btnGenerate = document.getElementById('generate-proof');
  if (!btnGenerate) {
    return;
  }
  if (state.proofProblem) {
    btnGenerate.classList.remove('hidden');
  } else {
    btnGenerate.classList.add('hidden');
  }
}

/**
 * Deserializes proof lines from the backend and populates the state.
 * 
 * @param {Object} state - Application state object
 * @param {Array} proofLines - Array of line objects from backend
 */
function deserializeProofLines(state, proofLines) {
  // Clear existing proof
  state.lines = [];
  state.nextId = 1;

  // Add each line from the backend
  for (const lineData of proofLines) {
    const line = addLine(
      state,
      lineData.indent,
      null,
      lineData.isAssumption,
      lineData.isPremise
    );
    
    // Process and set the formula text
    line.text = processFormula(lineData.text || '');
    
    // PR/AS are fixed and should not be symbolized.
    const justText = lineData.justText || '';
    if (justText === 'PR' || justText === 'AS') {
      line.justText = justText;
    } else {
      line.justText = processJustification(justText);
    }
  }
}

/**
 * Updates the result text and visual state.
 *
 * @param {HTMLElement|null} resultsSection - Results pane element
 * @param {HTMLElement} resultsBox - Results text element
 * @param {string} message - Message to display
 * @param {'progress'|'success'|'error'} status - Visual status
 */
function setResultsMessage(resultsSection, resultsBox, message, status = 'progress') {
  resultsBox.textContent = message;

  if (!resultsSection) {
    return;
  }

  resultsSection.classList.remove(
    'results-pane--success',
    'results-pane--error'
  );

  if (status === 'success') {
    resultsSection.classList.add('results-pane--success');
  } else if (status === 'error') {
    resultsSection.classList.add('results-pane--error');
  }
}

/**
 * Waits for the specified number of milliseconds.
 *
 * @param {number} milliseconds - Delay duration
 * @returns {Promise<void>}
 */
function delay(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

/**
 * Creates the payload used by proof-generation requests.
 *
 * @param {Object} state - Application state object
 * @returns {Object} Problem payload
 */
function getGenerationPayload(state) {
  const problem = state.proofProblem || state.problemDraft || {};

  return {
    logic: problem.logic || 'TFL',
    premisesText: problem.premisesText || '',
    conclusionText: problem.conclusionText || '',
  };
}

/**
 * Sends one proof-generation stage request with a browser-side safety timeout.
 *
 * @param {string} endpoint - Stage endpoint
 * @param {Object} payload - Problem payload
 * @param {number} timeoutMs - Browser-side request timeout
 * @returns {Promise<Object>} Parsed generation response
 */
async function requestGenerationStage(endpoint, payload, timeoutMs) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new GenerationError(
        data.message || GENERATION_ERROR_MESSAGE
      );
    }

    return data;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Validates the outcome and message returned for a generation stage.
 *
 * @param {Object} data - Generation response
 * @param {Array<string>} outcomes - Allowed outcomes
 */
function validateGenerationResponse(data, outcomes) {
  if (
    !outcomes.includes(data.outcome) ||
    typeof data.message !== 'string'
  ) {
    throw new GenerationError(
      INVALID_GENERATION_RESPONSE_MESSAGE
    );
  }
}

/**
 * Replaces the current proof with a generated proof response.
 *
 * @param {Object} state - Application state object
 * @param {Object} data - Generation response
 * @param {Function} renderProof - Function to render the proof
 * @returns {boolean} Whether a valid proof payload was displayed
 */
function displayGeneratedProof(state, data, renderProof) {
  if (!data.lines || !Array.isArray(data.lines)) {
    return false;
  }

  deserializeProofLines(state, data.lines);
  renderProof();
  scheduleUrlUpdate();
  return true;
}

/**
 * Displays a successfully generated proof.
 *
 * @param {Object} state - Application state object
 * @param {Object} data - Generation response
 * @param {Function} renderProof - Function to render the proof
 * @param {HTMLElement|null} resultsSection - Results pane element
 * @param {HTMLElement} resultsBox - Results text element
 */
function showGeneratedProof(
  state,
  data,
  renderProof,
  resultsSection,
  resultsBox
) {
  if (!displayGeneratedProof(state, data, renderProof)) {
    throw new GenerationError(
      INVALID_GENERATION_RESPONSE_MESSAGE
    );
  }

  setResultsMessage(
    resultsSection,
    resultsBox,
    data.message,
    'success'
  );
}

/**
 * Runs the staged proof-generation process.
 *
 * @param {Object} state - Application state object
 * @param {Function} renderProof - Function to render the proof
 * @param {HTMLElement|null} resultsSection - Results pane element
 * @param {HTMLElement} resultsBox - Results text element
 */
async function generateProof(
  state,
  renderProof,
  resultsSection,
  resultsBox
) {
  const payload = getGenerationPayload(state);

  setResultsMessage(
    resultsSection,
    resultsBox,
    'Checking argument validity...'
  );

  const validityData = await requestGenerationStage(
    '/api/generate-proof/validity',
    payload,
    GENERATION_REQUEST_TIMEOUTS.validity
  );

  validateGenerationResponse(
    validityData,
    ['invalid', 'valid', 'unknown']
  );

  if (validityData.outcome === 'invalid') {
    setResultsMessage(
      resultsSection,
      resultsBox,
      validityData.message,
      'error'
    );
    return;
  }

  setResultsMessage(
    resultsSection,
    resultsBox,
    validityData.message
  );

  const exhaustiveData = await requestGenerationStage(
    '/api/generate-proof/exhaustive',
    payload,
    GENERATION_REQUEST_TIMEOUTS.exhaustive
  );

  validateGenerationResponse(
    exhaustiveData,
    ['success', 'failure', 'timeout']
  );

  if (exhaustiveData.outcome === 'success') {
    showGeneratedProof(
      state,
      exhaustiveData,
      renderProof,
      resultsSection,
      resultsBox
    );
    return;
  }

  setResultsMessage(
    resultsSection,
    resultsBox,
    exhaustiveData.message
  );

  const [fastData] = await Promise.all([
    requestGenerationStage(
      '/api/generate-proof/fast',
      {
        ...payload,
        validityOutcome: validityData.outcome,
      },
      GENERATION_REQUEST_TIMEOUTS.fast
    ),
    delay(1000),
  ]);

  validateGenerationResponse(
    fastData,
    ['success', 'failure', 'timeout']
  );

  if (fastData.outcome === 'success') {
    showGeneratedProof(
      state,
      fastData,
      renderProof,
      resultsSection,
      resultsBox
    );
    return;
  }

  setResultsMessage(
    resultsSection,
    resultsBox,
    fastData.message,
    'error'
  );
}

/**
 * Initializes proof UI handlers (toolbar buttons).
 * 
 * @param {Object} state - Application state object
 * @param {Function} renderProof - Function to render the proof
 */
export function initProofUI(state, renderProof) {
  // Add line button (first-line only)
  const btnAddLine = document.getElementById('btn-add-line');
  btnAddLine.addEventListener('click', () => {
    if (state.lines.length !== 0) {
      return;
    }
    addLine(state, 0, null, false, false); // First top-level line
    renderProof();
    focusLineAt(0, 'formula-input', state);
    scheduleUrlUpdate();
  });

  // Begin subproof button (first-line only)
  const btnBeginSubproof = document.getElementById('btn-begin-subproof');
  btnBeginSubproof.addEventListener('click', () => {
    if (state.lines.length !== 0) {
      return;
    }
    addLine(state, 1, null, true, false); // First assumption at indent 1
    renderProof();
    focusLineAt(0, 'formula-input', state);
    scheduleUrlUpdate();
  });

  // Results section elements (shared by both CHECK PROOF and GENERATE buttons)
  const resultsSection = document.getElementById('results-pane');
  const resultsBox = document.getElementById('results');

  // Check proof button
  const btnCheckProof = document.getElementById('check-proof');

  if (btnCheckProof && resultsBox) {
    btnCheckProof.addEventListener('click', async () => {
      // Reveal the results section if hidden (mirror proof-pane behavior)
      if (resultsSection && resultsSection.classList.contains('hidden')) {
        resultsSection.classList.remove('hidden');
      }

      resultsBox.classList.add('results--show');
      const payload = serializeProofState(state);

      resultsBox.textContent = 'Checking proof...';

      try {
        const response = await fetch('/api/check-proof', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        const data = await response.json();
        const message = data.message || '';

        if (!response.ok || !data.ok) {
          if (resultsSection) {
            resultsSection.classList.remove('results-pane--success');
            resultsSection.classList.add('results-pane--error');
          }
          resultsBox.textContent = message;
          return;
        }

        if (data.isComplete) {
          if (resultsSection) {
            resultsSection.classList.remove('results-pane--error');
            resultsSection.classList.add('results-pane--success');
          }
          resultsBox.textContent = message;
        } else {
          if (resultsSection) {
            resultsSection.classList.remove('results-pane--success');
            resultsSection.classList.add('results-pane--error');
          }
          resultsBox.textContent = message;
        }
      } catch (error) {
        if (resultsSection) {
          resultsSection.classList.remove('results-pane--success');
          resultsSection.classList.add('results-pane--error');
        }
        resultsBox.textContent = 'An error occurred while checking the proof.';
      }
    });
  }

  // Generate proof button
  const btnGenerate = document.getElementById('generate-proof');

  if (btnGenerate && resultsBox) {
    let isGenerating = false;

    btnGenerate.addEventListener('click', async () => {
      if (isGenerating) {
        return;
      }

      isGenerating = true;
      btnGenerate.disabled = true;

      if (resultsSection) {
        resultsSection.setAttribute('aria-busy', 'true');
      }

      try {
        // Reveal the results section if hidden
        if (resultsSection && resultsSection.classList.contains('hidden')) {
          resultsSection.classList.remove('hidden');
        }

        resultsBox.classList.add(
          'results--show',
          'results--generating'
        );

        await generateProof(
          state,
          renderProof,
          resultsSection,
          resultsBox
        );
      } catch (error) {
        const message = error instanceof GenerationError
          ? error.message
          : GENERATION_ERROR_MESSAGE;

        setResultsMessage(
          resultsSection,
          resultsBox,
          message,
          'error'
        );
      } finally {
        resultsBox.classList.remove('results--generating');

        isGenerating = false;
        btnGenerate.disabled = false;

        if (resultsSection) {
          resultsSection.setAttribute('aria-busy', 'false');
        }
      }
    });
  }

  // Initialize GENERATE button visibility
  updateGenerateButtonVisibility(state);
}
