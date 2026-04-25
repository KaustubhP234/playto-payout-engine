function Card({ label, value, sub, color }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${color || 'text-slate-900'}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
    </div>
  );
}

function fmt(paise) {
  return '₹' + (paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 });
}

export default function BalanceCards({ balance }) {
  if (!balance) return null;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        label="Available Balance"
        value={fmt(balance.available_paise)}
        sub="Ready to withdraw"
        color="text-emerald-600"
      />
      <Card
        label="Held Balance"
        value={fmt(balance.held_paise)}
        sub="Pending / Processing"
        color="text-amber-600"
      />
      <Card
        label="Total Credits"
        value={fmt(balance.total_credits_paise)}
        sub="All time inflows"
        color="text-brand-600"
      />
      <Card
        label="Total Debits"
        value={fmt(balance.total_debits_paise)}
        sub="All time payouts"
        color="text-slate-700"
      />
    </div>
  );
}