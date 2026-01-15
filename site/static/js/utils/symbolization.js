/**
 * Symbolization Utilities
 *
 * Converts natural language logical operators to their symbolic representations.
 * This is a JavaScript implementation of the backend.py symbolization logic.
 *
 * Dependencies: None
 */

/**
 * Symbol mapping from text operators to logical symbols.
 * Keys are sorted by length (longest first) to ensure longer patterns
 * are matched before shorter ones.
 */
const SYMBOLS = {
  'not': '¬',
  '~': '¬',
  '∼': '¬',
  '-': '¬',
  '−': '¬',
  'and': '∧',
  '^': '∧',
  '&': '∧',
  '&&': '∧',
  '.': '∧',
  '·': '∧',
  '*': '∧',
  'or': '∨',
  '|': '∨',
  '||': '∨',
  '+': '∨',
  'iff': '↔',
  '⇔': '↔',
  '≡': '↔',
  '<->': '↔',
  '<=>': '↔',
  'imp': '→',
  '⇒': '→',
  '⊃': '→',
  '->': '→',
  '=>': '→',
  '>': '→',
  'forall': '∀',
  '⋀': '∀',
  '!': '∀',
  'exists': '∃',
  '⋁': '∃',
  '?': '∃',
  'bot': '⊥',
  'XX': '⊥',
  '#': '⊥',
  '_': '⊥',
  'box': '☐',
  '[]': '☐',
  'dia': '◇',
  '<>': '◇'
};

/**
 * Creates a regex pattern for matching all symbol operators.
 * Patterns are sorted by length (longest first) to match longer operators first.
 * Special patterns are added for Forall/Exists.
 *
 * @returns {RegExp} Compiled regex pattern for matching operators
 */
function createSymbolRegex() {
  // Get all keys sorted by length (longest first)
  const keys = Object.keys(SYMBOLS).sort((a, b) => b.length - a.length);
  
  // Escape special regex characters in each key
  const patterns = keys.map(key => escapeRegex(key));
  
  patterns.push('A(?=[s-zIE])');
  patterns.push('E(?=[s-zIE])');
  
  // Join all patterns with alternation operator
  const pattern = patterns.join('|');
  
  return new RegExp(pattern, 'g');
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

// Create the regex pattern once at module load time
const SYMBOL_REGEX = createSymbolRegex();

/**
 * Replaces matched operators with their symbolic equivalents.
 * Handles special cases for 'A' (Forall) and 'E' (Exists) followed by letters.
 *
 * @param {string} match - The matched substring
 * @returns {string} The corresponding symbol
 */
function replaceSymbol(match) {
  // Special handling for 'A' and 'E' followed by letters
  if (match === 'A') {
    return '∀';
  }
  if (match === 'E') {
    return '∃';
  }
  
  // Look up the symbol in the mapping
  return SYMBOLS[match] || match;
}

/**
 * Symbolizes a logical formula by converting text operators to symbols.
 * This function replaces natural language operators (e.g., "and", "or", "not")
 * and their various representations with standard logical symbols.
 *
 * @param {string|any} s - The input to symbolize (will be converted to string)
 * @returns {string} The symbolized string with operators replaced
 */
export function symbolize(s) {
  if (!s) {
    return '';
  }
  
  // Convert to string (handles non-string inputs like numbers, null, etc.)
  const str = String(s);
  
  // Replace all matched operators with their symbols
  return str.replace(SYMBOL_REGEX, replaceSymbol);
}
