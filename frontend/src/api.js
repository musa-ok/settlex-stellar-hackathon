const API = import.meta.env.VITE_API_URL || ''

async function req(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json()
}

export const api = {
  health: () => req('/api/health'),
  listRules: () => req('/api/rules'),
  createRule: (body) => req('/api/rules', { method: 'POST', body: JSON.stringify(body) }),
  parseRule: (text) => req('/api/rules/parse', { method: 'POST', body: JSON.stringify({ text }) }),
  deleteRule: (id) => req(`/api/rules/${id}`, { method: 'DELETE' }),
  sendInvoice: (body) => req('/api/invoice', { method: 'POST', body: JSON.stringify(body) }),
  startReturn: (text, lang = 'tr') =>
    req('/api/return', { method: 'POST', body: JSON.stringify({ text: text || '', lang }) }),
  listNegotiations: () => req('/api/negotiations'),
  approveAnomaly: (negotiation_id) =>
    req('/api/anomaly/approve', { method: 'POST', body: JSON.stringify({ negotiation_id, approved: true }) }),
  rejectAnomaly: (negotiation_id) =>
    req('/api/anomaly/reject', { method: 'POST', body: JSON.stringify({ negotiation_id, approved: false }) }),
  approveMultisig: (negotiation_id) =>
    req('/api/multisig/approve', { method: 'POST', body: JSON.stringify({ negotiation_id, approved: true }) }),
  balance: (public_key) =>
    req(`/api/balance${public_key ? `?public_key=${encodeURIComponent(public_key)}` : ''}`),
  fundWallet: (public_key) =>
    req('/api/wallet/fund', { method: 'POST', body: JSON.stringify({ public_key }) }),
  connectWallet: (public_key) =>
    req('/api/wallet/connect', { method: 'POST', body: JSON.stringify({ public_key }) }),
  sep10Challenge: (account) =>
    req('/api/sep10/challenge', { method: 'POST', body: JSON.stringify({ account }) }),
  sep10Token: (account, signed_transaction) =>
    req('/api/sep10/token', { method: 'POST', body: JSON.stringify({ account, signed_transaction }) }),
  transactions: () => req('/api/transactions'),
  withdraw: (body) => req('/api/anchor/withdraw', { method: 'POST', body: JSON.stringify(body) }),
  logs: () => req('/api/logs'),
}

export function wsUrl() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = import.meta.env.DEV ? `${window.location.hostname}:8000` : window.location.host
  return `${proto}://${host}/ws/agent-console`
}
