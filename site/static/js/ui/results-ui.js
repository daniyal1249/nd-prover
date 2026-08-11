/**
 * Results UI helpers
 *
 * Handles the results pane, progress display, and result-source tracking
 * for problem and proof actions.
 */

export const RESULT_SOURCES = {
  validation: 'validation',
  validity: 'validity',
  proofCheck: 'proof-check',
  generation: 'generation'
};

/**
 * Displays a message in the results pane.
 *
 * @param {HTMLElement|null} resultsSection - Results pane element
 * @param {HTMLElement|null} resultsBox - Results text element
 * @param {string} message - Message to display
 * @param {'progress'|'success'|'error'} status - Visual status
 * @param {string|null} source - Source of the displayed result
 */
export function setResultsMessage(
  resultsSection,
  resultsBox,
  message,
  status = 'progress',
  source = null
) {
  if (!resultsBox) {
    return;
  }

  if (resultsSection) {
    resultsSection.classList.remove('hidden');
    resultsSection.classList.remove(
      'results-pane--success',
      'results-pane--error'
    );

    if (status === 'success') {
      resultsSection.classList.add('results-pane--success');
    } else if (status === 'error') {
      resultsSection.classList.add('results-pane--error');
    }

    if (source) {
      resultsSection.dataset.resultSource = source;
    } else {
      delete resultsSection.dataset.resultSource;
    }
  }

  resultsBox.textContent = message;
  resultsBox.classList.add('results--show');
}

/**
 * Clears and hides the results pane.
 *
 * @param {HTMLElement|null} resultsSection - Results pane element
 * @param {HTMLElement|null} resultsBox - Results text element
 */
export function clearResults(resultsSection, resultsBox) {
  if (resultsSection) {
    resultsSection.classList.add('hidden');
    resultsSection.classList.remove(
      'results-pane--success',
      'results-pane--error'
    );
    resultsSection.setAttribute('aria-busy', 'false');
    delete resultsSection.dataset.resultSource;
  }

  if (resultsBox) {
    resultsBox.textContent = '';
    resultsBox.classList.remove(
      'results--show',
      'results--generating'
    );
    resultsBox.style.removeProperty('--generation-duration');
  }
}

/**
 * Clears the current result if it came from CHECK VALIDITY.
 *
 * @param {HTMLElement|null} resultsSection - Results pane element
 * @param {HTMLElement|null} resultsBox - Results text element
 */
export function clearValidityResult(resultsSection, resultsBox) {
  if (resultsSection?.dataset.resultSource !== RESULT_SOURCES.validity) {
    return;
  }
  clearResults(resultsSection, resultsBox);
}

/**
 * Starts the circular progress indicator.
 *
 * @param {HTMLElement|null} resultsSection - Results pane element
 * @param {HTMLElement|null} resultsBox - Results text element
 * @param {string} message - Progress message
 * @param {string} source - Source of the operation
 * @param {string} duration - CSS animation duration
 */
export function startResultsProgress(
  resultsSection,
  resultsBox,
  message,
  source,
  duration = '9s'
) {
  setResultsMessage(
    resultsSection,
    resultsBox,
    message,
    'progress',
    source
  );

  resultsSection?.setAttribute('aria-busy', 'true');
  resultsBox?.classList.add('results--generating');
  resultsBox?.style.setProperty('--generation-duration', duration);
}

/**
 * Stops the circular progress indicator.
 *
 * @param {HTMLElement|null} resultsSection - Results pane element
 * @param {HTMLElement|null} resultsBox - Results text element
 */
export function stopResultsProgress(resultsSection, resultsBox) {
  resultsSection?.setAttribute('aria-busy', 'false');
  resultsBox?.classList.remove('results--generating');
  resultsBox?.style.removeProperty('--generation-duration');
}
