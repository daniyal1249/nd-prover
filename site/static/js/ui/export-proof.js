/**
 * Proof export controls
 *
 * Expands the "Export proof" button into the available export formats
 * and handles proof export requests.
 *
 * Dependencies: expandable-options.js, serialization.js, results-ui.js
 */

import { serializeProofState } from '../utils/serialization.js';
import { initExpandableOptions } from './expandable-options.js';
import { RESULT_SOURCES, setResultsMessage } from './results-ui.js';

const EXPORT_LOGIC = 'FOMLS5';

const EXPORT_ENDPOINTS = {
  plain: '/api/export-proof/plain',
  latex: '/api/export-proof/latex'
};

const EXPORT_ERROR_MESSAGE = 'An error occurred while exporting the proof.';
const INVALID_EXPORT_RESPONSE_MESSAGE = 'Invalid response from server.';

async function exportProof(state, endpoint, resultsSection, resultsBox) {
  const payload = {...serializeProofState(state), logic: EXPORT_LOGIC};

  setResultsMessage(
    resultsSection,
    resultsBox,
    'Exporting proof...',
    'progress',
    RESULT_SOURCES.proofExport
  );

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      setResultsMessage(
        resultsSection,
        resultsBox,
        data.message || EXPORT_ERROR_MESSAGE,
        'error',
        RESULT_SOURCES.proofExport
      );
      return;
    }

    if (typeof data.proofString !== 'string') {
      setResultsMessage(
        resultsSection,
        resultsBox,
        INVALID_EXPORT_RESPONSE_MESSAGE,
        'error',
        RESULT_SOURCES.proofExport
      );
      return;
    }

    setResultsMessage(
      resultsSection,
      resultsBox,
      data.proofString,
      'neutral',
      RESULT_SOURCES.proofExport,
      'results--proof-export'
    );
  } catch (error) {
    setResultsMessage(
      resultsSection,
      resultsBox,
      EXPORT_ERROR_MESSAGE,
      'error',
      RESULT_SOURCES.proofExport
    );
  }
}

function initExportButton(
  button,
  endpoint,
  expandable,
  state,
  resultsSection,
  resultsBox
) {
  button?.addEventListener('click', async () => {
    expandable?.close();
    await exportProof(state, endpoint, resultsSection, resultsBox);
  });
}

export function initExportProof(state) {
  const root = document.getElementById('export-proof');
  const toggle = document.getElementById('export-proof-toggle');
  const options = document.getElementById('export-proof-options');
  const expandable = initExpandableOptions(root, toggle, options);

  const btnPlain = document.getElementById('export-proof-plain');
  const btnLatex = document.getElementById('export-proof-latex');

  const resultsSection = document.getElementById('results-pane');
  const resultsBox = document.getElementById('results');

  if (!resultsBox) {
    return;
  }

  initExportButton(
    btnPlain,
    EXPORT_ENDPOINTS.plain,
    expandable,
    state,
    resultsSection,
    resultsBox
  );

  initExportButton(
    btnLatex,
    EXPORT_ENDPOINTS.latex,
    expandable,
    state,
    resultsSection,
    resultsBox
  );
}
