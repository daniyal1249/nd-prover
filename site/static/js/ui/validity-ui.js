/**
 * Validity request helpers
 *
 * Shares the validity-stage request contract between standalone validity
 * checking and the first stage of proof generation.
 */

export const VALIDITY_PROGRESS_MESSAGE = 'Checking argument validity...';

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
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    const data = await response.json();

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
  } finally {
    clearTimeout(timeoutId);
  }
}
