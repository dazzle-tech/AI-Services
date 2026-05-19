const isLocalHost =
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1";

const LOCAL_API_PORTS = ["8011", "8000"];
const FRONTEND_PORTS = new Set(["8080"]);

let resolvedApiBaseUrl = null;
let resolutionPromise = null;

function normalizeBaseUrl(url) {
  return String(url || "").replace(/\/+$/, "");
}

function buildOrigin(port) {
  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  return `${protocol}//${window.location.hostname}:${port}`;
}

function buildCandidateBaseUrls() {
  const candidates = [];

  if (window.API_BASE_URL) {
    candidates.push(normalizeBaseUrl(window.API_BASE_URL));
  }

  if (!isLocalHost) {
    candidates.push(normalizeBaseUrl(window.location.origin));
    return [...new Set(candidates.filter(Boolean))];
  }

  LOCAL_API_PORTS.forEach((port) => {
    candidates.push(buildOrigin(port));
  });

  if (!FRONTEND_PORTS.has(window.location.port || "")) {
    candidates.push(normalizeBaseUrl(window.location.origin));
  }

  candidates.push(normalizeBaseUrl(window.location.origin));
  return [...new Set(candidates.filter(Boolean))];
}

async function canReachApi(baseUrl) {
  try {
    const response = await fetch(`${baseUrl}/`, {
      method: "GET",
      mode: "cors",
    });
    return response.ok;
  } catch (_) {
    return false;
  }
}

export async function resolveApiBaseUrl() {
  if (resolvedApiBaseUrl) {
    return resolvedApiBaseUrl;
  }

  if (!resolutionPromise) {
    const candidates = buildCandidateBaseUrls();
    resolutionPromise = (async () => {
      for (const candidate of candidates) {
        if (await canReachApi(candidate)) {
          resolvedApiBaseUrl = candidate;
          return candidate;
        }
      }

      resolvedApiBaseUrl = candidates[0];
      return resolvedApiBaseUrl;
    })();
  }

  return resolutionPromise;
}

export async function getEndpoint(path) {
  const baseUrl = await resolveApiBaseUrl();
  return `${baseUrl}${path}`;
}

export const DEFAULT_USER_ID = "u101";
export const DEFAULT_ROLE = "doctor";
export const MIN_REQUEST_INTERVAL = 300;
export const MAX_CONCURRENT_REQUESTS = 3;
export const REQUEST_TIMEOUT = 90000;

export function createSessionId() {
  return `session_${Date.now()}`;
}
