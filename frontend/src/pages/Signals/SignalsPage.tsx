import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import {
  Activity,
  TrendingUp,
  MessageSquare,
  Link,
} from 'lucide-react';

export function SignalsPage() {
  return (
    <div>
      <PageHeader
        title="Signals"
        description="Trading signals from technical, sentiment, and on-chain analysis"
      />

      {/* Signal stream */}
      <Card className="mb-6">
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
          Signal Stream
        </h3>
        <EmptyState
          icon={<Activity size={48} />}
          title="No signals generated yet"
          description="Trading signals with BUY/SELL/HOLD recommendations and confidence scores will stream here in real time."
          phase={2}
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Technical Analysis */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Technical Analysis
          </h3>
          <EmptyState
            icon={<TrendingUp size={40} />}
            title="Indicators pending"
            description="RSI, MACD, Bollinger Bands, EMA crossovers, and more via pandas-ta."
            phase={2}
            className="py-8"
          />
        </Card>

        {/* Sentiment Analysis */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Sentiment Analysis
          </h3>
          <EmptyState
            icon={<MessageSquare size={40} />}
            title="Feeds not connected"
            description="FinBERT-powered analysis of news, social media, and market sentiment."
            phase={5}
            className="py-8"
          />
        </Card>

        {/* On-Chain Metrics */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            On-Chain Metrics
          </h3>
          <EmptyState
            icon={<Link size={40} />}
            title="Not configured"
            description="Whale movements, exchange flows, active addresses, and network metrics."
            phase={6}
            className="py-8"
          />
        </Card>
      </div>
    </div>
  );
}
