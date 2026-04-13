import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 90000,
});

// ── Safety Check ──────────────────────────────────────────────────────────────
export const checkUrlSafety = async (url) => {
  const response = await api.post('/api/safety-check', { url });
  return response.data;
};

// ── Fact Check ────────────────────────────────────────────────────────────────
export const factCheckContent = async ({ text, url }) => {
  const payload = {};
  if (text) payload.text = text;
  if (url)  payload.url  = url;
  const response = await api.post('/api/fact-check', payload);
  return response.data;
};

// ── History ───────────────────────────────────────────────────────────────────
export const getHistory = async (limit = 8) => {
  const response = await api.get(`/api/history?limit=${limit}`);
  return response.data;
};

// ── Legacy compat (used by old code) ─────────────────────────────────────────
export const analyzeContent = async (text, url) => {
  return factCheckContent({ text, url });
};
