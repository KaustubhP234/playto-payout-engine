export default function Sidebar({ merchants, selectedId, onSelect }) {
  return (
    <aside className="w-64 min-h-screen bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-6 py-5 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center text-white font-bold text-sm">P</div>
          <span className="font-semibold text-white tracking-tight">Playto Pay</span>
        </div>
        <p className="text-xs text-slate-400 mt-1">Payout Engine</p>
      </div>

      <nav className="flex-1 px-3 py-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider px-3 mb-2">Merchants</p>
        {merchants.map((m) => (
          <button
            key={m.id}
            onClick={() => onSelect(m.id)}
            className={`w-full text-left px-3 py-2.5 rounded-lg mb-1 text-sm transition-colors ${
              selectedId === m.id
                ? 'bg-brand-600 text-white font-medium'
                : 'text-slate-300 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <div className="font-medium truncate">{m.name}</div>
            <div className="text-xs truncate mt-0.5 opacity-60">{m.email}</div>
          </button>
        ))}
      </nav>

      <div className="px-6 py-4 border-t border-slate-700">
        <p className="text-xs text-slate-500">v1.0.0 · Playto Payout Engine</p>
      </div>
    </aside>
  );
}