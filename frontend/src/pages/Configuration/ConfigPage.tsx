import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { TradingModeCard } from './TradingModeCard';
import { StrategyForm } from './StrategyForm';
import { RiskForm } from './RiskForm';
import { ExchangeSection } from './ExchangeSection';
import { EmailNotificationCard } from './EmailNotificationCard';
import { LogManagementCard } from './LogManagementCard';
import { TrendingUp, Plug, Wrench } from 'lucide-react';

type ConfigTab = 'trading' | 'integrations' | 'maintenance';

const tabs: { id: ConfigTab; label: string; icon: typeof TrendingUp }[] = [
  { id: 'trading', label: 'Trading', icon: TrendingUp },
  { id: 'integrations', label: 'Integrations', icon: Plug },
  { id: 'maintenance', label: 'Maintenance', icon: Wrench },
];

export function ConfigPage() {
  const [activeTab, setActiveTab] = useState<ConfigTab>('trading');

  return (
    <div>
      <PageHeader
        title="Configuration"
        description="Manage trading strategy, risk parameters, and exchange connections"
      />

      {/* Tab bar */}
      <div className="flex items-center border-b border-ct-border mb-6 overflow-x-auto">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap ${
              activeTab === id
                ? 'border-ct-accent text-ct-accent'
                : 'border-transparent text-ct-text-muted hover:text-ct-text'
            }`}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'trading' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <TradingModeCard />
          <StrategyForm />
          <RiskForm />
        </div>
      )}

      {activeTab === 'integrations' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ExchangeSection />
          <EmailNotificationCard />
        </div>
      )}

      {activeTab === 'maintenance' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <LogManagementCard />
        </div>
      )}
    </div>
  );
}
