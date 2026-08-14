/**
 * Input Processing Utilities
 * 
 * Functions for processing and normalizing user input, including
 * filtering, symbolization, and justification processing.
 * 
 * Dependencies: utils/symbolization.js
 */

import { symbolize } from './symbolization.js';

/**
 * Processes formula text by symbolizing and normalizing spacing.
 * 
 * @param {string} raw - Raw input text to process
 * @returns {string} Processed formula text
 */
export function processFormula(raw) {
  const sym = symbolize(raw);
  if (!sym || typeof sym !== 'string') {
    return '';
  }
  
  let t = sym.replace(/\s/g, '');
  const binaryOperators = ['∧', '∨', '→', '↔', '='];
  for (const op of binaryOperators) {
    t = t.replace(new RegExp(escapeRegex(op), 'g'), ` ${op} `);
  }
  
  // Add space after forall x or exists x
  t = t.replace(/([∀∃][a-zA-Z])/g, '$1 ');
  
  // Normalize premise separators and application commas
  t = normalizeFormulaSeparators(t);
  
  t = t.replace(/ +/g, ' ');
  t = t.trim();
  return t;
}

/**
 * Normalizes comma and semicolon spacing in formula text.
 * 
 * @param {string} str - Formula text to normalize
 * @returns {string} Formula text with normalized separators
 */
function normalizeFormulaSeparators(str) {
  let depth = 0;
  let result = '';

  for (const ch of str) {
    if (ch === '(') {
      depth++;
      result += ch;
      continue;
    }
    if (ch === ')') {
      depth = Math.max(0, depth - 1);
      result += ch;
      continue;
    }
    if (ch === ',') {
      result += depth > 0 ? ',' : ', ';
      continue;
    }
    if (ch === ';') {
      result += '; ';
      continue;
    }
    result += ch;
  }
  return result;
}

/**
 * Escapes special regex characters in a string.
 * 
 * @param {string} str - String to escape
 * @returns {string} Escaped string safe for use in regex
 */
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Processes justification text by symbolizing rule names and preserving
 * line references. Handles comma-separated justifications.
 * 
 * @param {string} raw - Raw justification text
 * @returns {string} Processed justification text
 */
export function processJustification(raw) {
  const s = String(raw ?? '');
  const i = s.indexOf(',');
  const clean = (t) => t.replace(/\s+/g, '');
  
  // If no comma, just symbolize and clean
  if (i === -1) {
    return clean(symbolize(s));
  }
  
  // Check if text after comma is empty or just whitespace
  const right = clean(s.slice(i + 1));
  if (!right) {
    // Treat as if no comma, just symbolize and clean the left part
    return clean(symbolize(s.slice(0, i)));
  }
  
  // Split on comma: symbolize left part (rule), preserve right part (line refs)
  const left = clean(symbolize(s.slice(0, i)));
  return `${left}, ${right}`;
}
