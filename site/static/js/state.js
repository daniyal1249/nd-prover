/**
 * State Management
 * 
 * Manages the application's global state including proof lines and problem data.
 * This is the single source of truth for application state.
 */

/**
 * Application state object
 * @type {Object}
 * @property {Array} lines - Array of proof line objects
 *   Each line: { id, indent, text, justText, isAssumption, isPremise }
 * @property {number} nextId - Counter for generating unique line IDs
 * @property {Object} problemDraft - Draft problem configuration (problem-setup inputs)
 * @property {string} problemDraft.logic - Selected logic system label (TFL, FOL, etc.)
 * @property {string} problemDraft.premisesText - Symbolized premises text
 * @property {string} problemDraft.conclusionText - Symbolized conclusion text
 * @property {string|null} problemDraft.domainSemantics - Domain semantics
 * @property {string|null} problemDraft.equalitySemantics - Equality semantics
 * @property {Object|null} proofProblem - Committed problem configuration for the proof editor
 * @property {string} proofProblem.logic - Selected logic system label (TFL, FOL, etc.)
 * @property {string} proofProblem.premisesText - Symbolized premises text
 * @property {string} proofProblem.conclusionText - Symbolized conclusion text
 * @property {string|null} proofProblem.domainSemantics - Domain semantics
 * @property {string|null} proofProblem.equalitySemantics - Equality semantics
 */
export const state = {
  lines: [],
  nextId: 1,
  problemDraft: {
    logic: 'TFL',
    premisesText: '',
    conclusionText: '',
    domainSemantics: null,
    equalitySemantics: null
  },
  proofProblem: null
};
