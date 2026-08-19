/**
 * Exercise links
 *
 * Auto-generates proof-editor URLs for exercises based on the argument text.
 *
 * - Splits on '∴'. If absent, treats the whole text as a conclusion with no premises.
 * - Premises are split on top-level commas/semicolons (same behavior as the editor).
 * - Only auto-fills links whose href is '#'. Any other href is treated
 *   as a manual override and left untouched.
 * - Logic is required per section: each exercises section must set `data-logic`.
 *
 * Dependencies:
 * - utils/input-processing.js (processFormula)
 * - ui/problem-summary.js (splitPremisesTopLevel)
 */

import { processFormula } from '../utils/input-processing.js'
import { splitPremisesTopLevel } from './problem-summary.js'

const HASH_PARAM = 's'
const THEREFORE = '∴'

function base64UrlEncode(text) {
  const bytes = new TextEncoder().encode(String(text || ''))
  let binary = ''
  for (const b of bytes) {
    binary += String.fromCharCode(b)
  }
  const b64 = btoa(binary)
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function getSectionLogic(linkEl) {
  const section = linkEl ? linkEl.closest('.exercises-section') : null
  const logic = section ? section.getAttribute('data-logic') : null
  return logic && String(logic).trim() ? String(logic).trim() : null
}

function parseArgumentText(text) {
  const raw = String(text || '').trim()
  const idx = raw.indexOf(THEREFORE)
  if (idx === -1) {
    return { premisesText: '', conclusionText: raw }
  }
  return {
    premisesText: raw.slice(0, idx).trim(),
    conclusionText: raw.slice(idx + THEREFORE.length).trim()
  }
}

function buildSnapshot({ logic, premisesText, conclusionText }) {
  const premises = processFormula(premisesText || '')
  const conclusion = processFormula(conclusionText || '')

  const premParts = splitPremisesTopLevel(premises)

  // Proof lines are stored as tuples: [indent, flags, text, justText]
  // flags bitmask: 1=assumption, 2=premise.
  const lines = premParts.map((p) => [0, 2, p, 'PR'])

  return {
    draft: {
      logic,
      premisesText: premises,
      conclusionText: conclusion
    },
    proof: {
      active: true,
      derivedRules: true,
      problem: {
        logic,
        premisesText: premises,
        conclusionText: conclusion
      },
      lines
    }
  }
}

function hydrateExerciseLinks() {
  const links = document.querySelectorAll('a.exercise-link')

  links.forEach((a) => {
    const rawHref = a.getAttribute('href')
    const href = String(rawHref || '').trim()
    if (href !== '#') {
      return
    }

    const logic = getSectionLogic(a)
    if (!logic) {
      console.warn('Missing required data-logic on exercises section for link:', a)
      return
    }

    const { premisesText, conclusionText } = parseArgumentText(a.textContent)
    const snapshot = buildSnapshot({ logic, premisesText, conclusionText })
    const encoded = base64UrlEncode(JSON.stringify(snapshot))
    a.href = `/#${HASH_PARAM}=${encoded}`
  })
}

function enhanceExerciseRows() {
  const rows = document.querySelectorAll('tr.exercise-row')
  rows.forEach((row) => {
    const link = row.querySelector('a.exercise-link')
    if (!link) {
      return
    }

    row.addEventListener('click', (e) => {
      const target = e.target
      if (target && target.closest && target.closest('a.exercise-link')) {
        return
      }

      const href = String(link.getAttribute('href') || '').trim()
      if (!href || href === '#') {
        return
      }

      e.preventDefault()
      if (e.ctrlKey || e.metaKey) {
        window.open(href, '_blank', 'noopener')
        return
      }
      window.location.assign(href)
    })
  })
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    hydrateExerciseLinks()
    enhanceExerciseRows()
  })
} else {
  hydrateExerciseLinks()
  enhanceExerciseRows()
}
