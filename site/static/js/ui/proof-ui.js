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

/**
 * Updates the visibility of the GENERATE button based on the selected logic.
 * The button is only visible when the logic is TFL.
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

      try {
        // Reveal the results section if hidden
        if (resultsSection && resultsSection.classList.contains('hidden')) {
          resultsSection.classList.remove('hidden');
        }

        resultsBox.classList.add('results--show');

        const payload = {
          logic: state.proofProblem
            ? state.proofProblem.logic
            : (state.problemDraft ? state.problemDraft.logic : 'TFL'),
          premisesText: state.proofProblem
            ? state.proofProblem.premisesText
            : (state.problemDraft ? state.problemDraft.premisesText : ''),
          conclusionText: state.proofProblem
            ? state.proofProblem.conclusionText
            : (state.problemDraft ? state.problemDraft.conclusionText : '')
        };

        resultsBox.textContent = 'Generating proof...';

        try {
          // Create an AbortController for timeout handling (12 seconds)
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 12000);

          let response;
          try {
            response = await fetch('/api/generate-proof', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
              signal: controller.signal
            });
            clearTimeout(timeoutId);
          } catch (fetchError) {
            clearTimeout(timeoutId);
            if (fetchError.name === 'AbortError') {
              // Timeout occurred
              if (resultsSection) {
                resultsSection.classList.remove('results-pane--success');
                resultsSection.classList.add('results-pane--error');
              }
              resultsBox.textContent = 'Proof generation timed out.';
              return;
            }
            throw fetchError; // Re-throw other errors
          }

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

          // Success - deserialize and display the proof
          if (data.lines && Array.isArray(data.lines)) {
            deserializeProofLines(state, data.lines);
            renderProof();
            scheduleUrlUpdate();
            
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
            resultsBox.textContent = 'Invalid response from server.';
          }
        } catch (error) {
          if (resultsSection) {
            resultsSection.classList.remove('results-pane--success');
            resultsSection.classList.add('results-pane--error');
          }
          resultsBox.textContent = 'An error occurred while generating the proof.';
        }
      } finally {
        isGenerating = false;
      }
    });
  }

  // Initialize GENERATE button visibility
  updateGenerateButtonVisibility(state);
}
