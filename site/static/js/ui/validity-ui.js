/**
 * Validity request helpers
 *
 * Shares the validity-stage request contract between standalone validity
 * checking and the first stage of proof generation.
 * Dependencies: utils/requests.js
 */

import { postJson } from '../utils/requests.js';

export const VALIDITY_PROGRESS_MESSAGE = 'Checking argument validity...';

const VALIDITY_CACHE_LIMIT = 100;
const validityCache = new Map();
const pendingValidityRequests = new Map();

export class ValidityRequestError extends Error {}

/**
 * Creates the semantic problem payload used by validity-related requests.
 *
 * @param {Object} problem - Draft or committed problem configuration
 * @returns {Object} Problem payload
 */
export function buildProblemPayload(problem = {}) {
  return {
    logic: problem.logic || 'TFL',
    premisesText: problem.premisesText || '',
    conclusionText: problem.conclusionText || '',
    domainSemantics: problem.domainSemantics ?? null,
    equalitySemantics: problem.equalitySemantics ?? null
  };
}

/**
 * Sends and validates a validity-stage request.
 *
 * @param {string} endpoint - Validity endpoint
 * @param {Object} payload - Problem payload
 * @param {number} timeoutMs - Browser-side safety timeout
 * @param {string} errorMessage - Fallback error message
 * @returns {Promise<Object>} Parsed validity response
 */
export async function requestValidity(
  endpoint,
  payload,
  timeoutMs,
  errorMessage
) {
  try {
    const { response, data } = await postJson(endpoint, payload, timeoutMs);

    if (!response.ok || !data.ok) {
      throw new ValidityRequestError(
        data.message || errorMessage
      );
    }

    if (
      !['invalid', 'valid', 'unknown'].includes(data.outcome) ||
      typeof data.message !== 'string'
    ) {
      throw new ValidityRequestError(
        'Invalid response from server.'
      );
    }

    return data;
  } catch (error) {
    if (error instanceof ValidityRequestError) {
      throw error;
    }
    throw new ValidityRequestError(errorMessage);
  }
}

/**
 * Shares validity results, including countermodel messages, between callers.
 * Keeps up to 100 definitive results for this page session, most recently used last.
 *
 * @param {Object} payload - Draft or committed problem configuration
 * @param {number} timeoutMs - Browser-side safety timeout
 * @param {string} errorMessage - Fallback error message
 * @param {number} semanticTimeoutMs - Backend semantic-check budget
 * @returns {Promise<Object>} Parsed validity response
 */
export async function requestCachedValidity(
  payload,
  timeoutMs,
  errorMessage,
  semanticTimeoutMs = 10000
) {
  const problem = buildProblemPayload(payload);
  const key = JSON.stringify(problem);
  const cached = validityCache.get(key);
  if (cached) {
    validityCache.delete(key);
    validityCache.set(key, cached);
    return { ...cached };
  }

  const requestKey = JSON.stringify([problem, semanticTimeoutMs]);
  let pending = pendingValidityRequests.get(requestKey);
  if (!pending) {
    pending = requestValidity(
      '/api/check-validity', { ...problem, timeout: semanticTimeoutMs }, timeoutMs, errorMessage
    )
      .then((data) => {
        if (data.outcome !== 'unknown') {
          validityCache.set(key, data);
          if (validityCache.size > VALIDITY_CACHE_LIMIT) {
            validityCache.delete(validityCache.keys().next().value);
          }
        }
        return data;
      })
      .finally(() => pendingValidityRequests.delete(requestKey));
    pendingValidityRequests.set(requestKey, pending);
  }
  return { ...await pending };
}
