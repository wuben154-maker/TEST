import { useState, useEffect } from 'react';
import { FileText, Terminal, Shield, Cpu, Search, LayoutGrid } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import type { WorkspaceTabInstance } from '@/types/analysis';
import type { WorkspaceBlock } from '@/types/analysis';
import type { AnalysisResultStats, AnalysisResultStatus } from '@/types/project';
import { useLanguage } from '@/contexts/LanguageContext';
import { ReportTab } from './tabs/ReportTab';
import { ShellTab } from './tabs/ShellTab';
import { IocTableTab } from './tabs/IocTableTab';
import { BinaryPipelineTab } from './tabs/BinaryPipelineTab';
import { InvestigationTab } from './tabs/InvestigationTab';

const ICON_MAP: Record<string, React.ReactNode> = {
  terminal:         <Terminal className="w-3 h-3" />,
  shield:           <Shield className="w-3 h-3" />,
  cpu:              <Cpu className="w-3 h-3" />,
  search:           <Search className="w-3 h-3" />,
  'file-text':      <FileText className="w-3 h-3" />,
};

function resolveIcon(name: string): React.ReactNode {
  return ICON_MAP[name] ?? <LayoutGrid className="w-3 h-3" />;
}

function renderTabContent(tab: WorkspaceTabInstance, status: AnalysisResultStatus) {
  const { data } = tab;
  if (data.kind === 'shell') {
    return (
      <ShellTab
        instanceKey={tab.instanceKey}
        status={status}
        lines={data.lines}
      />
    );
  }
  if (data.kind === 'ioc_table') {
    return <IocTableTab raw={data.raw} />;
  }
  if (tab.type === 'binary_pipeline') {
    return <BinaryPipelineTab />;
  }
  if (tab.type === 'investigation') {
    return <InvestigationTab />;
  }
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
      {data.kind === 'placeholder' ? data.message : '—'}
    </div>
  );
}

interface TaskTabPanelProps {
  status: AnalysisResultStatus;
  blocks: WorkspaceBlock[];
  workspaceTabs: WorkspaceTabInstance[];
  reportTitle?: string;
  generatedAt?: string;
  stats?: AnalysisResultStats;
  /** Called when user saves an edited version of the report (plain text). */
  onEditReport?: (text: string) => void;
  /** Pre-existing edited text (from parent state). */
  editedReportText?: string;
}

export function TaskTabPanel({
  status,
  blocks,
  workspaceTabs,
  reportTitle,
  generatedAt,
  stats,
  onEditReport,
  editedReportText,
}: TaskTabPanelProps) {
  const { t } = useLanguage();
  const tp = t.workspace.taskPanel;
  const [activeTab, setActiveTab] = useState('report');

  const hasDynamicTabs = workspaceTabs.length > 0;

  useEffect(() => {
    if (activeTab === 'report') return;
    const exists = workspaceTabs.some((tab) => tab.id === activeTab);
    if (!exists) setActiveTab('report');
  }, [workspaceTabs, activeTab]);

  const tabTriggerClass = `
    h-9 px-3 rounded-none border-b-2 -mb-px text-xs gap-1.5 font-medium
    border-transparent text-muted-foreground
    hover:text-foreground hover:border-muted-foreground/30
    data-[state=active]:border-primary data-[state=active]:bg-transparent
    data-[state=active]:shadow-none data-[state=active]:text-foreground
    transition-colors duration-150
  `;

  return (
    <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col flex-1 min-h-0">
      {/* Inner Tab Bar — GitHub underline style */}
      <div className="flex-shrink-0 border-b border-border bg-background">
        <ScrollArea className="w-full whitespace-nowrap">
          <TabsList className="h-9 bg-transparent gap-0 p-0 px-4 inline-flex">
            {/* Report tab — always first */}
            <TabsTrigger value="report" className={tabTriggerClass}>
              <FileText className="w-3 h-3" />
              {tp.report}
            </TabsTrigger>

            {/* Dynamic tabs */}
            {workspaceTabs.map((tab) => (
              <TabsTrigger key={tab.id} value={tab.id} className={tabTriggerClass}>
                {resolveIcon(tab.icon)}
                <span className="max-w-[80px] sm:max-w-[120px] truncate">{tab.label}</span>
              </TabsTrigger>
            ))}
          </TabsList>
          {hasDynamicTabs && <ScrollBar orientation="horizontal" />}
        </ScrollArea>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto">
        <div className="px-5 pb-8 min-h-full">
          <TabsContent value="report" className="mt-0 outline-none">
            <ReportTab
              status={status}
              blocks={blocks}
              title={reportTitle}
              generatedAt={generatedAt}
              stats={stats}
              editedText={editedReportText}
              onSave={onEditReport}
            />
          </TabsContent>

          {workspaceTabs.map((tab) => (
            <TabsContent key={tab.id} value={tab.id} className="mt-0 outline-none pt-4">
              {renderTabContent(tab, status)}
            </TabsContent>
          ))}
        </div>
      </div>
    </Tabs>
  );
}
