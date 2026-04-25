const BASE_URL = 'http://127.0.0.1:8000/api/v1';

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...options.headers,
    },
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, data };
  return data;
}
export const api = {
  getMerchants: () => request('/merchants/'),

  getMerchant: (id) => request(`/merchants/${id}/`),

  getBalance: (merchantId) =>
    request(`/merchants/${merchantId}/balance/`),

  getLedger: (merchantId) =>
    request(`/merchants/${merchantId}/ledger/`),

  getPayouts: (merchantId) =>
    request(`/merchants/${merchantId}/payouts/`),

  createPayout: (merchantId, body, idempotencyKey) =>
    request(`/merchants/${merchantId}/payouts/`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(body),
    }),
};