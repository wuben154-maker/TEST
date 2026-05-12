import { Globe, MapPin, Server, ExternalLink, FileDigit, Hash } from 'lucide-react';
import { IntelCard as IntelCardType } from '@/types/analysis';
import { useLanguage } from '@/contexts/LanguageContext';

interface IntelCardProps {
  block: IntelCardType;
}

const indicatorIcons = {
  ip: Server,
  domain: Globe,
  hash: FileDigit,
};

function getHashType(hash: string): string {
  const len = hash.length;
  if (len === 32) return 'MD5';
  if (len === 40) return 'SHA1';
  if (len === 64) return 'SHA256';
  return 'Hash';
}

function getVirusTotalUrl(indicator: string, type: 'ip' | 'domain' | 'hash'): string {
  switch (type) {
    case 'ip':
      return `https://www.virustotal.com/gui/ip-address/${indicator}`;
    case 'domain':
      return `https://www.virustotal.com/gui/domain/${indicator}`;
    case 'hash':
      return `https://www.virustotal.com/gui/file/${indicator}`;
    default:
      return 'https://www.virustotal.com';
  }
}

export function IntelCard({ block }: IntelCardProps) {
  const { t } = useLanguage();
  const threatConfig = {
    high: {
      color: 'text-destructive',
      bg: 'bg-destructive/20',
      border: 'border-destructive/50',
      label: t.intel.highRisk,
    },
    medium: {
      color: 'text-warning',
      bg: 'bg-warning/20',
      border: 'border-warning/50',
      label: t.intel.mediumRisk,
    },
    low: {
      color: 'text-accent',
      bg: 'bg-accent/20',
      border: 'border-accent/50',
      label: t.intel.lowRisk,
    },
    clean: {
      color: 'text-success',
      bg: 'bg-success/20',
      border: 'border-success/50',
      label: t.intel.safe,
    },
  };
  const threat = threatConfig[block.threatScore];
  const IndicatorIcon = indicatorIcons[block.indicatorType];
  const vtUrl = getVirusTotalUrl(block.indicator, block.indicatorType);

  const getIndicatorLabel = () => {
    if (block.indicatorType === 'ip') return t.intel.ipAddress;
    if (block.indicatorType === 'domain') return t.intel.domain;
    if (block.indicatorType === 'hash') return getHashType(block.indicator);
    return t.intel.indicator;
  };

  return (
    <div className={`rounded-lg border ${threat.border} ${threat.bg} overflow-hidden animate-slide-up`}>
      <div className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg ${threat.bg} border ${threat.border} flex items-center justify-center`}>
              <IndicatorIcon className={`w-5 h-5 ${threat.color}`} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
                {getIndicatorLabel()}
              </p>
              <p className={`font-mono font-semibold ${threat.color} break-all text-sm`}>
                {block.indicatorType === 'hash' && block.indicator.length > 40
                  ? `${block.indicator.slice(0, 20)}...${block.indicator.slice(-20)}`
                  : block.indicator}
              </p>
            </div>
          </div>
          <div className={`px-3 py-1 rounded-full ${threat.bg} border ${threat.border} flex-shrink-0`}>
            <span className={`text-xs font-medium ${threat.color}`}>{threat.label}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-border/50">
          {block.location && (
            <div className="flex items-center gap-2">
              <MapPin className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-foreground/80">{block.location}</span>
            </div>
          )}
          {block.asn && (
            <div className="flex items-center gap-2">
              <Server className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-foreground/80 font-mono">{block.asn}</span>
            </div>
          )}
          {block.indicatorType === 'hash' && (
            <div className="flex items-center gap-2 col-span-2">
              <Hash className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-foreground/80 font-mono">
                {getHashType(block.indicator)} {t.intel.fileHash}
              </span>
            </div>
          )}
        </div>

        {block.tags && block.tags.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {block.tags.map((tag, idx) => (
              <span
                key={idx}
                className="px-2 py-0.5 rounded text-xs font-medium bg-muted text-muted-foreground"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
      
      <div className="px-4 py-2 bg-background/30 border-t border-border/50">
        <a 
          href={vtUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ExternalLink className="w-3 h-3" />
          {t.intel.viewInVirusTotal}
        </a>
      </div>
    </div>
  );
}
