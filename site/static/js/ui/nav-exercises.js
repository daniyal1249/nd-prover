/**
 * Exercises nav toggle
 *
 * Clicking "Exercises" replaces it with the three logic buttons (TFL/FOL/ML).
 * Clicking anywhere outside restores the "Exercises" button.
 *
 * Dependencies: expandable-options.js
 */

import { initExpandableOptions } from './expandable-options.js';

function initExercisesNav() {
  const root = document.getElementById('nav-exercises');
  const toggle = document.getElementById('nav-exercises-toggle');
  const options = document.getElementById('nav-exercises-options');

  initExpandableOptions(root, toggle, options);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initExercisesNav);
} else {
  initExercisesNav();
}
