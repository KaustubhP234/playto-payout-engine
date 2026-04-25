import { useState, useEffect, useCallback } from 'react';
import { api } from './api';
import Sidebar from './components/Sidebar';
import BalanceCards from './components/BalanceCards';
import PayoutForm from './components/PayoutForm';
import PayoutTable from './components/PayoutTable';
import LedgerTable from './components/LedgerTable';

export default function App() {
  const [merchants, setMerchants] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [merchant, setMerchant] = useState(null);
  const [balance, setBalance] = useState(null);
  const [payouts, setPayouts] = useState([]);
  const [ledger, setLedger] = useState([]);
  const [payoutsLoading, setPayoutsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');

  // Load merchants on mount
  useEffect(() => {
    api.getMerchants().then((data) => {
      setMerchants(data);
      if (data.length > 0) setSelectedId(data[0].id);
    });
  }, []);

  // Load merchant data when selection changes
  const loadMerchantData = useCallback(async () => {
    if (!selectedId) return;
    const [m, b, p, l] = await Promise.all([
      api.getMerchant(selectedId),
      api.getBalance(selectedId),
      api.getPayouts(selectedId),
      api.getLedger(selectedId),
    ]);
    setMerchant(m);
    setBalance(b);
    setPayouts(p);
    setLedger(l);
  }, [selectedId]);

  useEffect(() => {
    loadMerchantData();
  }, [loadMerchantData]);

  // Poll payout statuses every 5 seconds for live updates
  useEffect(() => {
    if (!selectedId) return;
    const interval = setInterval(async () => {
      const [b, p] = await Promise.all([
        api.getBalance(selectedId),
        api.getPayouts(selectedId),
      ]);
      setBalance(b);
      setPayouts(p);
    }, 5000);
    return () => clearInterval(interval);
  }, [selectedId]);

  const handleMerchantSelect = (id) => {
    setSelectedId(id);
    setActiveTab('overview');
  };

  const handlePayoutSuccess = () => {
    loadMerchantData();
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar
        merchants={merchants}
        selectedId={selectedId}
        onSelect={handleMerchantSelect}
      />

      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="bg-white border-b border-slate-200 px-8 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">
              {merchant?.name || 'Loading...'}
            </h1>
            <p className="text-xs text-slate-500">{merchant?.email}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400 bg-slate-100 px-3 py-1 rounded-full font-mono">
              {merchant?.bank_account_id}
            </span>
          </div>
        </header>

        <div className="flex-1 px-8 py-6 space-y-6">
          {/* Balance Cards */}
          <BalanceCards balance={balance} />

          {/* Tabs */}
          <div className="flex gap-1 border-b border-slate-200">
            {['overview', 'payouts', 'ledger'].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
                  activeTab === tab
                    ? 'border-brand-500 text-brand-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          {activeTab === 'overview' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-1">
                <PayoutForm
                  merchant={merchant}
                  onSuccess={handlePayoutSuccess}
                />
              </div>
              <div className="lg:col-span-2">
                <PayoutTable payouts={payouts.slice(0, 5)} loading={payoutsLoading} />
              </div>
            </div>
          )}

          {activeTab === 'payouts' && (
            <PayoutTable payouts={payouts} loading={payoutsLoading} />
          )}

          {activeTab === 'ledger' && (
            <LedgerTable entries={ledger} />
          )}
        </div>
      </main>
    </div>
  );
}