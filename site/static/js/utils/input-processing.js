/**
 * Input Processing Utilities
 * 
 * Functions for processing and normalizing user input, including
 * filtering, symbolization, and justification processing.
 * 
 * Dependencies: utils/symbolization.js
 */

import { symbolize } from './symbolization.js';

const RULE_NAMES = new Set(JSON.parse(
  document.getElementById('rule-names')?.textContent || '[]'
));

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
 * Splits a justification into a normalized rule name and citation text.
 * Accepts a comma or whitespace between the rule and its citations.
 * 
 * @param {string} raw - Raw justification text
 * @returns {Array<string>} Rule name and citations
 */
export function splitJustification(raw) {
  const s = String(raw ?? '').trim();
  const i = s.indexOf(',');
  const clean = (t) => t.replace(/\s+/g, '');
  const ruleName = (t) => clean(symbolize(t));

  if (i !== -1 && RULE_NAMES.has(ruleName(s.slice(0, i)))) {
    return [ruleName(s.slice(0, i)), clean(s.slice(i + 1))];
  }

  const boundaries = Array.from(s.matchAll(/\s+(?=[+-]?\s*\p{Decimal_Number})/gu));
  for (const match of boundaries.reverse()) {
    const rule = ruleName(s.slice(0, match.index));
    if (RULE_NAMES.has(rule)) {
      return [rule, clean(s.slice(match.index + match[0].length))];
    }
  }

  return i === -1
    ? [ruleName(s), '']
    : [ruleName(s.slice(0, i)), clean(s.slice(i + 1))];
}

/**
 * Formats a justification with one space before its citations.
 *
 * @param {string} raw - Raw justification text
 * @returns {string} Processed justification text
 */
export function processJustification(raw) {
  const [rule, citations] = splitJustification(raw);
  return citations ? `${rule} ${citations}` : rule;
}
