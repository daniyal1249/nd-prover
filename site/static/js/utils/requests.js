/**
 * JSON Request Helpers
 *
 * Shares JSON POST requests and browser-side timeout cleanup.
 * Dependencies: none
 */

/**
 * Sends JSON and returns the response with its parsed body.
 *
 * @param {string} endpoint - Request endpoint
 * @param {Object} payload - JSON request payload
 * @param {number} timeoutMs - Browser-side safety timeout
 * @returns {Promise<Object>} Response and parsed data
 */
export async function postJson(endpoint, payload, timeoutMs) {
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
    return { response, data };
  } finally {
    clearTimeout(timeoutId);
  }
}
