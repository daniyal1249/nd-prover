/**
 * URL state persistence
 *
 * Stores the draft problem (problem-setup inputs) + proof editor state into the URL hash,
 * and restores it on load / back-forward navigation.
 *
 * Format:
 *   #s=<payload>
 *
 * Payload is a URL-safe, base64url-encoded JSON string.
 */

import { splitLogicValue } from './logic-mapping.js';
import { processFormula, processJustification } from './input-processing.js';
import { renderProblemSummary } from '../ui/problem-summary.js';

const HASH_PARAM = 's';

let _state = null;
let _render = null;
let _timer = null;
let _suspendWrites = false;
let _lastAppliedEncoded = null;

/**
 * Initializes URL state sync and attempts to restore from the current URL.
 *
 * @param {Object} state - Global application state
 * @param {Function} render - Render function (re-renders proof)
 * @param {{ renderOnInit?: boolean }} [opts]
 * @returns {boolean} Whether a snapshot was successfully loaded from the URL
 */
export function initUrlState(state, render, opts = {}) {
  _state = state;
  _render = render;

  const loaded = applySnapshotFromUrl({ shouldRender: !!opts.renderOnInit });

  window.addEventListener('hashchange', () => {
    applySnapshotFromUrl({ shouldRender: true });
  });

  return loaded;
}

/**
 * Debounced request to write current app state into the URL.
 * Call this after any mutation to `state.problemDraft`, 
 * `state.proofProblem`, or `state.lines`.
 */
export function scheduleUrlUpdate() {
  if (!_state || _suspendWrites) {
    return;
  }

  if (_timer) {
    clearTimeout(_timer);
  }

  _timer = setTimeout(() => {
    _timer = null;
    writeUrlFromState(_state);
  }, 200);
}

function buildSnapshotFromState(state) {
  const draft = state.problemDraft || {
    logic: 'TFL',
    premisesText: '',
    conclusionText: ''
  };
  const proofProblem = state.proofProblem || null;

  const proofActive = isProofPaneActive();

  const hasAnyProblem =
    !!(draft.logic && draft.logic !== 'TFL') ||
    !!(draft.premisesText && /\S/.test(draft.premisesText)) ||
    !!(draft.conclusionText && /\S/.test(draft.conclusionText));
  const hasAnyLines =
    proofActive && Array.isArray(state.lines) && state.lines.length > 0;

  if (!hasAnyProblem && !hasAnyLines) {
    return null;
  }

  const storedLines = proofActive
    ? (state.lines || []).map((line) => {
      const flags = (line.isAssumption ? 1 : 0) | (line.isPremise ? 2 : 0);
      return [
        Number(line.indent || 0),
        flags,
        String(line.text || ''),
        String(line.justText || '')
      ];
    })
    : [];

  const committed = proofActive
    ? (proofProblem || {
      logic: String(draft.logic || 'TFL'),
      premisesText: String(draft.premisesText || ''),
      conclusionText: String(draft.conclusionText || '')
    })
    : null;

  return {
    draft: {
      logic: String(draft.logic || 'TFL'),
      premisesText: String(draft.premisesText || ''),
      conclusionText: String(draft.conclusionText || '')
    },
    proof: {
      active: proofActive,
      problem: committed,
      // Each line: [indent, flags, text, justText] where flags bitmask:
      // 1=assumption, 2=premise.
      lines: storedLines
    }
  };
}

function applySnapshotToState(snapshot, state) {
  const d = extractDraftFromSnapshot(snapshot);
  state.problemDraft.logic = String(d.logic || 'TFL');
  state.problemDraft.premisesText = String(d.premisesText || '');
  state.problemDraft.conclusionText = String(d.conclusionText || '');

  const {
    active: proofActive,
    tuples,
    problem: proofProblem
  } = extractProofFromSnapshot(snapshot);
  state.proofProblem = proofActive ? proofProblem : null;

  state.lines = [];
  state.nextId = 1;

  if (proofActive) {
    for (const t of tuples) {
      if (!Array.isArray(t) || t.length < 4) {
        continue;
      }

      const indent = Number(t[0] || 0);
      const flags = Number(t[1] || 0);
      const isAssumption = (flags & 1) === 1;
      const isPremise = (flags & 2) === 2;

      const rawText = String(t[2] || '');
      const rawJust = String(t[3] || '');

      const text = processFormula(rawText);
      const justText =
        rawJust === 'PR' || rawJust === 'AS'
          ? rawJust
          : (rawJust ? processJustification(rawJust) : '');

      state.lines.push({
        id: state.nextId++,
        indent,
        text,
        justText,
        isAssumption,
        isPremise
      });
    }
  }
}

function updateGenerateButtonVisibilityFromState(state) {
  const btnGenerate = document.getElementById('generate-proof');
  if (!btnGenerate) {
    return;
  }
  if (isProofPaneActive()) {
    btnGenerate.classList.remove('hidden');
  } else {
    btnGenerate.classList.add('hidden');
  }
}

function syncUiFromState(state) {
  const logicSelect = document.getElementById('logic');
  const firstOrderCheckbox = document.getElementById('first-order');
  const premisesBox = document.getElementById('premises');
  const conclusionBox = document.getElementById('conclusion');

  if (premisesBox) {
    premisesBox.value = state.problemDraft.premisesText || '';
  }
  if (conclusionBox) {
    conclusionBox.value = state.problemDraft.conclusionText || '';
  }

  const { baseLogic, isFirstOrder } = splitLogicValue(state.problemDraft.logic);
  if (logicSelect) {
    logicSelect.value = baseLogic;
  }
  if (firstOrderCheckbox) {
    firstOrderCheckbox.checked = isFirstOrder;
  }

  const summaryEl = document.getElementById('problem-summary');
  const proofActive = isProofPaneActive();
  if (proofActive && state.proofProblem) {
    renderProblemSummary(
      summaryEl,
      state.proofProblem.logic,
      state.proofProblem.premisesText,
      state.proofProblem.conclusionText
    );
  } else if (summaryEl) {
    summaryEl.textContent = '';
  }

  updateGenerateButtonVisibilityFromState(state);
}

function isProofPaneActive() {
  const proofPane = document.getElementById('proof-pane');
  if (!proofPane) {
    return false;
  }
  return !proofPane.classList.contains('hidden');
}

function extractDraftFromSnapshot(snapshot) {
  if (!isSnapshotShape(snapshot)) {
    return {};
  }
  return snapshot.draft || {};
}

function extractProofFromSnapshot(snapshot) {
  if (!isSnapshotShape(snapshot)) {
    return { active: false, tuples: [], problem: null };
  }

  const proof = snapshot.proof || {};
  const active = !!proof.active;
  const tuples = Array.isArray(proof.lines) ? proof.lines : [];
  const problem = proof.problem || null;
  return { active, tuples, problem };
}

function isSnapshotShape(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') {
    return false;
  }
  if (!snapshot.draft || typeof snapshot.draft !== 'object') {
    return false;
  }
  if (!snapshot.proof || typeof snapshot.proof !== 'object') {
    return false;
  }
  return true;
}

function parseHashParams() {
  const raw = window.location.hash || '';
  const hash = raw.startsWith('#') ? raw.slice(1) : raw;
  return new URLSearchParams(hash);
}

function getEncodedSnapshotFromUrl() {
  const params = parseHashParams();
  const val = params.get(HASH_PARAM);
  return val && String(val) ? String(val) : null;
}

function setEncodedSnapshotInUrl(encoded) {
  const params = parseHashParams();

  if (!encoded) {
    params.delete(HASH_PARAM);
  } else {
    params.set(HASH_PARAM, encoded);
  }

  const newHash = params.toString();
  const base = `${window.location.pathname}${window.location.search}`;
  const nextUrl = newHash ? `${base}#${newHash}` : base;
  const currentUrl =
    `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (nextUrl === currentUrl) {
    return;
  }

  // replaceState avoids triggering a hashchange event (keeps editing smooth).
  history.replaceState(null, '', nextUrl);
}

function encodeSnapshot(snapshot) {
  const json = JSON.stringify(snapshot);
  return base64UrlEncode(json);
}

function decodeSnapshot(encoded) {
  const json = base64UrlDecode(encoded);
  return JSON.parse(json);
}

function base64UrlEncode(text) {
  const bytes = new TextEncoder().encode(String(text || ''));
  let binary = '';
  for (const b of bytes) {
    binary += String.fromCharCode(b);
  }
  const b64 = btoa(binary);
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function base64UrlDecode(encoded) {
  const s = String(encoded || '');
  if (!s) {
    return '';
  }
  const padded =
    s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new TextDecoder().decode(bytes);
}

function applySnapshotFromUrl({ shouldRender }) {
  const encoded = getEncodedSnapshotFromUrl();
  if (!encoded) {
    return false;
  }

  if (encoded === _lastAppliedEncoded) {
    return true;
  }

  let snapshot;
  try {
    snapshot = decodeSnapshot(encoded);
  } catch (e) {
    console.warn('Failed to decode URL snapshot:', e);
    return false;
  }

  if (!isSnapshotShape(snapshot)) {
    return false;
  }

  _suspendWrites = true;
  try {
    applySnapshotToState(snapshot, _state);
    setProofPaneVisibilityFromSnapshot(snapshot);
    syncUiFromState(_state);
    _lastAppliedEncoded = encoded;
  } finally {
    _suspendWrites = false;
  }

  if (shouldRender && typeof _render === 'function') {
    _render();
  }

  return true;
}

function setProofPaneVisibilityFromSnapshot(snapshot) {
  const proofPane = document.getElementById('proof-pane');
  if (!proofPane) {
    return;
  }

  const { active } = extractProofFromSnapshot(snapshot);
  if (active) {
    proofPane.classList.remove('hidden');
  } else {
    proofPane.classList.add('hidden');
  }
}

function writeUrlFromState(state) {
  const snapshot = buildSnapshotFromState(state);
  const encoded = snapshot ? encodeSnapshot(snapshot) : null;

  const current = getEncodedSnapshotFromUrl();
  // If the state is now "empty", clear the URL (but don't wipe an undecodable hash).
  if (current && !encoded) {
    try {
      const parsed = decodeSnapshot(current);
      if (isSnapshotShape(parsed)) {
        setEncodedSnapshotInUrl(null);
      }
    } catch (e) {
      // Keep the existing snapshot if we can't decode it.
    }
    return;
  }
  if ((current || null) === (encoded || null)) {
    return;
  }

  setEncodedSnapshotInUrl(encoded);
}
