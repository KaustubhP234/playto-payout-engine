import { useState } from 'react';
import { api } from '../api';

function genUUID() {
  return crypto.randomUUID();
}

export default function PayoutForm({ merchant, onSuccess }) {
  const [amount, setAmount] = useState('');
  const [bankAccount, setBankAccount] = useState(merchant?.bank_account_id || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');

  const showToast = (msg, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(''), 4000);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const amountRupees = parseFloat(amount);
    if (!amount || isNaN(amountRupees) || amountRupees <= 0) {
      setError('Enter a valid amount in rupees.');
      return;
    }
    if (!bankAccount.trim()) {
      setError('Bank account ID is required.');
      return;
    }

    const amountPaise = Math.round(amountRupees * 100);
    setLoading(true);

    try {
      await api.createPayout(
        merchant.id,
        { amount_paise: amountPaise, bank_account_id: bankAccount },
        genUUID()
      );
      setAmount('');
      showToast(`Payout of ₹${amountRupees.toFixed(2)} initiated successfully.`);
      onSuccess();
    } catch (err) {
      const msg = err?.data?.error || 'Failed to create payout.';
      setError(msg);
      showToast(msg, true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-700 mb-4">Request Payout</h2>

      {toast && (
        <div className={`mb-4 px-4 py-2.5 rounded-lg text-sm font-medium ${
          toast.isError ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
        }`}>
          {toast.msg}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Amount (₹)</label>
          <input
            type="number"
            min="1"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="e.g. 500.00"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Bank Account ID</label>
          <input
            type="text"
            value={bankAccount}
            onChange={(e) => setBankAccount(e.target.value)}
            placeholder="e.g. HDFC_XXXX_0042"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>

        {error && (
          <p className="text-xs text-red-600 font-medium">{error}</p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-brand-500 hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium text-sm py-2.5 rounded-lg transition-colors"
        >
          {loading ? 'Processing...' : 'Initiate Payout'}
        </button>
      </form>
    </div>
  );
}