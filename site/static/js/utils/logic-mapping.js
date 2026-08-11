/**
 * Logic mapping helpers
 *
 * Keeps the base-logic and checkbox mappings consistent across the UI and
 * persistence layers.
 */

const LOGIC_MAP = {
  TFL: {
    classical: { propositional: 'TFL', firstOrder: 'FOL' },
    intuitionistic: { propositional: 'IPL', firstOrder: 'IFOL' }
  },
  MLK: {
    classical: { propositional: 'MLK', firstOrder: 'FOMLK' },
    intuitionistic: { propositional: 'IMLK', firstOrder: 'IFOMLK' }
  },
  MLT: {
    classical: { propositional: 'MLT', firstOrder: 'FOMLT' },
    intuitionistic: { propositional: 'IMLT', firstOrder: 'IFOMLT' }
  },
  MLS4: {
    classical: { propositional: 'MLS4', firstOrder: 'FOMLS4' },
    intuitionistic: { propositional: 'IMLS4', firstOrder: 'IFOMLS4' }
  },
  MLS5: {
    classical: { propositional: 'MLS5', firstOrder: 'FOMLS5' },
    intuitionistic: { propositional: 'IMLS5', firstOrder: 'IFOMLS5' }
  }
};

const INVERSE_LOGIC_MAP = Object.entries(LOGIC_MAP).reduce(
  (inverse, [baseLogic, systems]) => {
    for (const [kind, orders] of Object.entries(systems)) {
      for (const [order, logicLabel] of Object.entries(orders)) {
        inverse[logicLabel] = {
          baseLogic,
          isFirstOrder: order === 'firstOrder',
          isIntuitionistic: kind === 'intuitionistic'
        };
      }
    }
    return inverse;
  },
  {}
);

/**
 * Maps the base logic and checkbox settings to a concrete logic class label.
 *
 * @param {string} baseLogic - Base logic value (TFL, MLK, MLT, MLS4, MLS5)
 * @param {boolean} isFirstOrder - Whether first-order logic is selected
 * @param {boolean} isIntuitionistic - Whether intuitionistic logic is selected
 * @returns {string} Concrete logic label
 */
export function getLogicValue(
  baseLogic,
  isFirstOrder,
  isIntuitionistic = false
) {
  const systems = LOGIC_MAP[baseLogic] || LOGIC_MAP.TFL;
  const kind = isIntuitionistic ? 'intuitionistic' : 'classical';
  const order = isFirstOrder ? 'firstOrder' : 'propositional';
  return systems[kind][order];
}

/**
 * Determines the controls needed to display a stored concrete logic label.
 *
 * @param {string} logicLabel - Stored logic label
 * @returns {{
 *   baseLogic: string,
 *   isFirstOrder: boolean,
 *   isIntuitionistic: boolean
 * }}
 */
export function splitLogicValue(logicLabel) {
  return INVERSE_LOGIC_MAP[String(logicLabel || '')] || {
    baseLogic: 'TFL',
    isFirstOrder: false,
    isIntuitionistic: false
  };
}

/**
 * Resolves selector visibility and the semantic values represented by the
 * current logic configuration.
 *
 * @param {string} baseLogic - Selected base logic
 * @param {boolean} isFirstOrder - Whether first-order logic is selected
 * @param {boolean} isIntuitionistic - Whether intuitionistic logic is selected
 * @param {string} domainChoice - Current domain-selector value
 * @param {string} equalityChoice - Current equality-selector value
 * @returns {{
 *   showDomain: boolean,
 *   showEquality: boolean,
 *   domainSemantics: string|null,
 *   equalitySemantics: string|null
 * }}
 */
export function resolveSemanticOptions(
  baseLogic,
  isFirstOrder,
  isIntuitionistic,
  domainChoice = 'expanding',
  equalityChoice = 'equivalence'
) {
  const classicalModalFirstOrder =
    isFirstOrder && !isIntuitionistic && baseLogic !== 'TFL';
  const intuitionisticFirstOrder = isFirstOrder && isIntuitionistic;

  const showDomain =
    intuitionisticFirstOrder ||
    (classicalModalFirstOrder && baseLogic !== 'MLS5');
  const showEquality = intuitionisticFirstOrder;

  let domainSemantics = null;
  if (isFirstOrder && isIntuitionistic) {
    domainSemantics = domainChoice;
  } else if (classicalModalFirstOrder) {
    domainSemantics = baseLogic === 'MLS5' ? 'constant' : domainChoice;
  }

  let equalitySemantics = null;
  if (isFirstOrder) {
    equalitySemantics = isIntuitionistic ? equalityChoice : 'identity';
  }

  return {
    showDomain,
    showEquality,
    domainSemantics,
    equalitySemantics
  };
}

/**
 * Determines whether the selected logic supports the proof editor.
 *
 * @param {string} baseLogic - Selected base logic
 * @param {boolean} isIntuitionistic - Whether intuitionistic logic is selected
 * @returns {boolean} Whether CREATE PROBLEM should be available
 */
export function supportsProofEditor(baseLogic, isIntuitionistic) {
  return !isIntuitionistic || baseLogic === 'TFL';
}
