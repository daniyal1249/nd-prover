/**
 * Proof Line Operations
 * 
 * Functions for adding, deleting, and manipulating proof lines and subproofs.
 * 
 * Dependencies: state.js
 */

/**
 * Updates citation numbers after inserting or deleting proof lines.
 * Numbers outside the old proof and references to deleted lines are preserved.
 *
 * @param {Object} state - Application state object
 * @param {number} oldLineCount - Number of lines before the edit
 * @param {number} start - First inserted or deleted line number (1-based)
 * @param {number} removedCount - Number of deleted lines
 * @param {number} addedCount - Number of inserted lines
 */
function updateCitations(state, oldLineCount, start, removedCount, addedCount) {
  for (const line of state.lines) {
    const justText = line.justText || '';
    const comma = justText.indexOf(',');
    if (comma === -1) {
      continue;
    }

    const citations = justText.slice(comma + 1);
    const updated = citations.replace(/\d+/g, (match, offset) => {
      const number = Number(match);
      // A minus after a number separates range endpoints; otherwise it is a sign.
      const isNegative = /(?:^|[^\d\s])\s*-\s*$/.test(citations.slice(0, offset));
      if (isNegative || number < 1 || number > oldLineCount || number < start) {
        return match;
      }
      if (number < start + removedCount) {
        return match;
      }
      return String(number + addedCount - removedCount);
    });

    line.justText = justText.slice(0, comma + 1) + updated;
  }
}

/**
 * Finds the assumptions whose subproofs contain the final proof line.
 *
 * @param {Array} lines - All proof lines
 * @returns {Array} Open assumptions, from outermost to innermost
 */
export function getOpenAssumptions(lines) {
  const open = [];
  for (const line of lines) {
    while (open.length > 0) {
      const assumption = open[open.length - 1];
      if (line.indent > assumption.indent ||
          (line.indent === assumption.indent && !line.isAssumption)) {
        break;
      }
      open.pop();
    }
    if (line.isAssumption) {
      open.push(line);
    }
  }
  return open;
}

/**
 * Adds a new proof line to the state.
 * 
 * @param {Object} state - Application state object
 * @param {number} indent - Indentation level (0 = top level)
 * @param {number|null} afterIndex - Index to insert after (null = append)
 * @param {boolean} isAssumption - Whether this is an assumption line
 * @param {boolean} isPremise - Whether this is a premise line
 * @returns {Object} The created line object
 */
export function addLine(
  state,
  indent = 0,
  afterIndex = null,
  isAssumption = false,
  isPremise = false
) {
  const oldLineCount = state.lines.length;
  const insertIndex = afterIndex == null || afterIndex < 0
    ? oldLineCount
    : Math.min(afterIndex + 1, oldLineCount);
  const line = {
    id: state.nextId++,
    indent,
    text: '',
    justText: isAssumption ? 'AS' : '',
    isAssumption,
    isPremise
  };
  if (isAssumption) {
    line.goal = '';
    line.goalExpanded = false;
  }
  
  if (afterIndex == null || afterIndex < 0) {
    state.lines.push(line);
  } else {
    state.lines.splice(afterIndex + 1, 0, line);
  }
  updateCitations(state, oldLineCount, insertIndex + 1, 0, 1);
  
  return line;
}

/**
 * Deletes a line at the given index. If it's an assumption line,
 * deletes the entire subproof (all nested lines).
 * 
 * @param {Object} state - Application state object
 * @param {number} i - Index of line to delete
 */
export function deleteLineAt(state, i) {
  if (i < 0 || i >= state.lines.length) {
    return;
  }
  
  const oldLineCount = state.lines.length;
  const line = state.lines[i];
  let removedCount = 1;
  if (line.isAssumption) {
    // Delete entire subproof
    const startIndent = line.indent;
    let j = i + 1;
    while (j < state.lines.length) {
      const nxt = state.lines[j];
      if (nxt.indent < startIndent) {
        break;
      }
      if (nxt.indent === startIndent && nxt.isAssumption) {
        break;
      }
      j++;
    }
    removedCount = j - i;
  }
  state.lines.splice(i, removedCount);
  updateCitations(state, oldLineCount, i + 1, removedCount, 0);
}

/**
 * Adds a line after the given index at the same indent level.
 * 
 * @param {Object} state - Application state object
 * @param {number} i - Index to add after
 * @returns {number} Index of the newly added line
 */
export function addLineAfterSame(state, i) {
  const indent = state.lines[i] ? state.lines[i].indent : 0;
  addLine(state, indent, i, false, false);
  return i + 1;
}

/**
 * Begins a subproof below the given index by adding an assumption line.
 * 
 * @param {Object} state - Application state object
 * @param {number} i - Index to add subproof after
 * @returns {number} Index of the newly added assumption line
 */
export function beginSubproofBelow(state, i) {
  const base = state.lines[i] ? state.lines[i].indent : 0;
  addLine(state, base + 1, i, true, false);
  return i + 1;
}

/**
 * Ends the subproof at the given index and adds a line at the parent level.
 * 
 * @param {Object} state - Application state object
 * @param {number} i - Index of line ending the subproof
 * @returns {number|null} Index of newly added line, or null if invalid
 */
export function endSubproofAt(state, i) {
  const line = state.lines[i];
  if (!line || line.indent < 1) {
    return null;
  }
  const parentIndent = line.indent - 1;
  addLine(state, parentIndent, i, false, false);
  return i + 1;
}

/**
 * Ends the subproof at the given index and begins another at the same level.
 * 
 * @param {Object} state - Application state object
 * @param {number} i - Index of line ending the subproof
 * @returns {number|null} Index of newly added assumption line, or null if invalid
 */
export function endAndBeginAnotherAt(state, i) {
  const line = state.lines[i];
  if (!line || line.indent < 1) {
    return null;
  }
  addLine(state, line.indent, i, true, false);
  return i + 1;
}
