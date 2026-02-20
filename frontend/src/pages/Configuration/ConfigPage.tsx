import { PageHeader } from '@/components/ui/PageHeader';
import { TradingModeCard } from './TradingModeCard';
import { StrategyForm } from './StrategyForm';
import { RiskForm } from './RiskForm';
import { ExchangeSection } from './ExchangeSection';

export function ConfigPage() {
  return (
    <div>
      <PageHeader
        title="Configuration"
        description="Manage trading strategy, risk parameters, and exchange connections"
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TradingModeCard />
        <StrategyForm />
        <RiskForm />
        <ExchangeSection />
      </div>
    </div>
  );
}
