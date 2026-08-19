/**
 * Proof serialization helpers
 *
 * These helpers prepare the frontend state for sending to the Python backend.
 * The shapes are chosen to map cleanly onto nd_prover.Problem operations.
 */

/**
 * Builds the raw line string expected by nd_prover.parser.parse_line.
 *
 * Examples:
 *   text: 'P → Q', justText: '→E, 1,2'
 *   => 'P → Q; →E, 1,2'
 *
 *   text: 'P', justText: ''
 *   => 'P'
 *
 * @param {Object} line - Line object from state.lines
 * @returns {string} Raw line string
 */
export function buildRawLineString(line) {
  const formula = (line.text || '').trim();
  const just = (line.justText || '').trim();
  if (!formula) {
    return '';
  }
  return just ? `${formula}; ${just}` : formula;
}

/**
 * Computes the correct kind for a line based on its position in the proof structure.
 * 
 * Rules:
 * - Premises always have kind 'premise'
 * - Assumptions:
 *   - If previous line has same indent → 'end_and_begin' (comes after another subproof)
 *   - Otherwise → 'assumption' (new subproof)
 * - Regular lines (not assumption, not premise):
 *   - If previous line has larger indent → 'close_subproof' (closing a subproof)
 *   - Otherwise → 'line' (regular line)
 * 
 * @param {Array} lines - All proof lines
 * @param {number} index - Index of the line to compute kind for
 * @param {Object} line - The line object
 * @returns {string} The computed kind
 */
function computeLineKind(lines, index, line) {
  if (line.isPremise) {
    return 'premise';
  }

  const prevLine = index > 0 ? lines[index - 1] : null;

  if (line.isAssumption) {
    if (prevLine && prevLine.indent === line.indent) {
      return 'end_and_begin';
    }
    return 'assumption';
  }

  if (prevLine && prevLine.indent > line.indent) {
    return 'close_subproof';
  }
  
  return 'line';
}

/**
 * Serializes the entire proof state into a JSON-ready object.
 *
 * Backend contract (per-line):
 *   {
 *     kind: 'premise' | 'assumption' | 'line' | 'close_subproof' | 'end_and_begin',
 *     indent: number,
 *     isAssumption: boolean,
 *     isPremise: boolean,
 *     raw: string  // output of buildRawLineString
 *   }
 *
 * @param {Object} state - Global application state
 * @returns {Object} JSON-serializable proof payload
 */
export function serializeProofState(state) {
  const problem = state.proofProblem || state.problemDraft || {};
  return {
    logic: problem.logic,
    premisesText: problem.premisesText,
    conclusionText: problem.conclusionText,
    domainSemantics: problem.domainSemantics ?? null,
    equalitySemantics: problem.equalitySemantics ?? null,
    derivedRules: state.derivedRules !== false,
    lines: state.lines.map((line, index) => {
      const kind = computeLineKind(state.lines, index, line);
      const isAssumptionLike = kind === 'assumption' || kind === 'end_and_begin';
      const formulaText = (line.text || '').trim();
      const justText = (line.justText || '').trim();

      return {
        lineNumber: index + 1,
        kind,
        indent: line.indent,
        isAssumption: line.isAssumption,
        isPremise: line.isPremise,
        formulaText,
        justText,
        raw: isAssumptionLike
          ? formulaText
          : buildRawLineString(line)
      };
    })
  };
}
