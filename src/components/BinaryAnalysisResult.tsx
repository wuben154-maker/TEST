import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Shield,
  AlertTriangle,
  CheckCircle,
  XCircle,
  FileText,
  Network,
  Eye,
  Database,
  Code,
  Hash,
  FileCheck,
} from 'lucide-react';

interface ThreatDetection {
  detection_id: string;
  detector_name: string;
  threat_name: string;
  threat_type: string;
  confidence: number;
  severity: number;
  description: string;
  mitigation: string;
  iocs: string[];
}

interface FileInfo {
  file_name: string;
  file_size: number;
  file_type: string | null;
  architecture: string;
  hashes: {
    md5: string;
    sha1: string;
    sha256: string;
  };
}

interface SectionInfo {
  name: string;
  virtual_address: string;
  virtual_size: number;
  raw_size: number;
  entropy: number;
  permissions: string[];
  is_executable: boolean;
  contains_code: boolean;
}

interface ImportInfo {
  function_name: string;
  library_name: string;
  is_suspicious: boolean;
  risk_level: string;
  description: string;
}

interface StringInfo {
  content: string;
  address: string;
  encoding: string;
  length: number;
  is_url: boolean;
  is_ip: boolean;
  is_suspicious: boolean;
}

interface FunctionInfo {
  address: string;
  name: string;
  size: number;
  complexity_score: number;
  is_suspicious: boolean;
  basic_blocks_count: number;
  api_calls: string[];
}

interface AnalysisStats {
  duration: number;
  sections_count: number;
  imports_count: number;
  exports_count: number;
  strings_count: number;
  functions_count: number;
  threats_count: number;
}

interface AnalysisResult {
  analysis_id: string;
  status: string;
  threat_level: number;
  file_info: FileInfo;
  analysis_stats: AnalysisStats;
  threats: ThreatDetection[];
  sections: SectionInfo[];
  imports: ImportInfo[];
  exports: unknown[];
  strings: StringInfo[];
  functions: FunctionInfo[];
  call_graph?: {
    nodes_count: number;
    edges_count: number;
    entry_points_count: number;
    complexity_score: number;
  } | null;
  warnings?: string[];
  error?: string;
}

interface BinaryAnalysisResultProps {
  result: AnalysisResult;
  onDownloadReport?: () => void;
  onViewCallGraph?: () => void;
}

export function BinaryAnalysisResult({ result, onDownloadReport, onViewCallGraph }: BinaryAnalysisResultProps) {
  const [selectedTab, setSelectedTab] = useState('overview');

  const getThreatLevelInfo = (level: number) => {
    if (level >= 75) return { color: 'destructive', icon: XCircle, text: 'Critical', bgColor: 'bg-red-50' };
    if (level >= 50) return { color: 'destructive', icon: AlertTriangle, text: 'Malicious', bgColor: 'bg-orange-50' };
    if (level >= 25) return { color: 'warning', icon: AlertTriangle, text: 'Suspicious', bgColor: 'bg-yellow-50' };
    return { color: 'default', icon: CheckCircle, text: 'Clean', bgColor: 'bg-green-50' };
  };

  const threatInfo = getThreatLevelInfo(result.threat_level);
  const ThreatIcon = threatInfo.icon;

  const getRiskColor = (riskLevel: string) => {
    switch (riskLevel) {
      case 'high':
        return 'destructive';
      case 'medium':
        return 'warning';
      default:
        return 'secondary';
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`;
  };

  return (
    <div className="space-y-6">
      {result.error && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertTitle>Analysis Failed</AlertTitle>
          <AlertDescription>{result.error}</AlertDescription>
        </Alert>
      )}

      {result.warnings && result.warnings.length > 0 && (
        <Alert variant="default">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Warnings</AlertTitle>
          <AlertDescription>
            <ul className="list-disc list-inside space-y-1">
              {result.warnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <Card className={threatInfo.bgColor}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Threat Assessment
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <ThreatIcon className={`h-8 w-8 ${threatInfo.color === 'warning' ? 'text-yellow-600' : threatInfo.color === 'destructive' ? 'text-red-600' : 'text-green-600'}`} />
              <div>
                <h3 className="text-2xl font-bold">{threatInfo.text}</h3>
                <p className="text-sm text-muted-foreground">Threat Level: {result.threat_level}/100</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-lg font-semibold">{result.analysis_stats.threats_count} Threats</p>
              <p className="text-sm text-muted-foreground">detected</p>
            </div>
          </div>
          {result.analysis_stats.threats_count > 0 && (
            <div className="mt-4">
              <Progress value={result.threat_level} className="h-2" />
            </div>
          )}
        </CardContent>
      </Card>

      <Tabs value={selectedTab} onValueChange={setSelectedTab}>
        <TabsList className="grid w-full grid-cols-7">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="threats">Threats</TabsTrigger>
          <TabsTrigger value="sections">Sections</TabsTrigger>
          <TabsTrigger value="imports">Imports</TabsTrigger>
          <TabsTrigger value="strings">Strings</TabsTrigger>
          <TabsTrigger value="functions">Functions</TabsTrigger>
          <TabsTrigger value="callgraph">Call Graph</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  File Information
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <span className="font-medium">Name:</span><span className="font-mono">{result.file_info.file_name}</span>
                  <span className="font-medium">Size:</span><span>{formatBytes(result.file_info.file_size)}</span>
                  <span className="font-medium">Type:</span><span>{result.file_info.file_type || 'Unknown'}</span>
                  <span className="font-medium">Architecture:</span><span>{result.file_info.architecture}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Hash className="h-4 w-4" />
                  File Hashes
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div>
                  <span className="font-medium">MD5:</span>
                  <code className="block mt-1 p-2 bg-muted rounded text-xs">{result.file_info.hashes.md5}</code>
                </div>
                <div>
                  <span className="font-medium">SHA1:</span>
                  <code className="block mt-1 p-2 bg-muted rounded text-xs">{result.file_info.hashes.sha1}</code>
                </div>
                <div>
                  <span className="font-medium">SHA256:</span>
                  <code className="block mt-1 p-2 bg-muted rounded text-xs break-all">{result.file_info.hashes.sha256}</code>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-4 w-4" />
                Analysis Statistics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center"><div className="text-2xl font-bold">{result.analysis_stats.sections_count}</div><div className="text-sm text-muted-foreground">Sections</div></div>
                <div className="text-center"><div className="text-2xl font-bold">{result.analysis_stats.imports_count}</div><div className="text-sm text-muted-foreground">Imports</div></div>
                <div className="text-center"><div className="text-2xl font-bold">{result.analysis_stats.functions_count}</div><div className="text-sm text-muted-foreground">Functions</div></div>
                <div className="text-center"><div className="text-2xl font-bold">{formatDuration(result.analysis_stats.duration)}</div><div className="text-sm text-muted-foreground">Duration</div></div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="threats">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle className="h-4 w-4" />Threat Detections ({result.threats.length})</CardTitle></CardHeader>
            <CardContent>
              {result.threats.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <CheckCircle className="h-12 w-12 mx-auto mb-2 text-green-500" />
                  <p>No threats detected</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {result.threats.map((threat, index) => (
                    <Card key={index} className="border-l-4 border-l-red-500">
                      <CardContent className="pt-4">
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <h4 className="font-semibold">{threat.threat_name}</h4>
                            <Badge variant={getRiskColor(threat.threat_type)}>{threat.threat_type}</Badge>
                            <Badge variant="outline">{threat.detector_name}</Badge>
                          </div>
                          <p className="text-sm text-muted-foreground">{threat.description}</p>
                          <div className="flex items-center gap-2 text-sm">
                            <span>Confidence:</span>
                            <Progress value={threat.confidence * 100} className="w-20 h-2" />
                            <span>{(threat.confidence * 100).toFixed(1)}%</span>
                          </div>
                          {threat.mitigation && <div className="mt-2 p-2 bg-blue-50 rounded text-sm"><strong>Mitigation:</strong> {threat.mitigation}</div>}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sections">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Database className="h-4 w-4" />Sections ({result.sections.length})</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Virtual Address</TableHead><TableHead>Size</TableHead><TableHead>Entropy</TableHead><TableHead>Permissions</TableHead><TableHead>Properties</TableHead></TableRow></TableHeader>
                <TableBody>
                  {result.sections.map((section, index) => (
                    <TableRow key={index}>
                      <TableCell className="font-mono">{section.name}</TableCell>
                      <TableCell className="font-mono">{section.virtual_address}</TableCell>
                      <TableCell>{formatBytes(section.raw_size)}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span>{section.entropy}</span>
                          <div className={`h-2 w-12 rounded ${section.entropy > 7.5 ? 'bg-red-500' : section.entropy > 6 ? 'bg-yellow-500' : 'bg-green-500'}`} />
                        </div>
                      </TableCell>
                      <TableCell><div className="flex gap-1">{section.permissions.map(perm => <Badge key={perm} variant="outline" className="text-xs">{perm}</Badge>)}</div></TableCell>
                      <TableCell><div className="flex gap-1">{section.is_executable && <Badge variant="default" className="text-xs">EXEC</Badge>}{section.contains_code && <Badge variant="secondary" className="text-xs">CODE</Badge>}</div></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="imports">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Network className="h-4 w-4" />Imported Functions ({result.imports.length})</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>Function</TableHead><TableHead>Library</TableHead><TableHead>Risk Level</TableHead><TableHead>Description</TableHead></TableRow></TableHeader>
                <TableBody>
                  {result.imports.map((imp, index) => (
                    <TableRow key={index} className={imp.is_suspicious ? 'bg-red-50' : ''}>
                      <TableCell className="font-mono">{imp.function_name}</TableCell>
                      <TableCell>{imp.library_name}</TableCell>
                      <TableCell><Badge variant={getRiskColor(imp.risk_level)}>{imp.risk_level}</Badge></TableCell>
                      <TableCell className="text-sm">{imp.description}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="strings">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><FileText className="h-4 w-4" />Interesting Strings ({result.strings.length})</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2">
                {result.strings.map((str, index) => (
                  <div key={index} className={`p-2 rounded border ${str.is_suspicious ? 'bg-red-50 border-red-200' : 'bg-gray-50'}`}>
                    <div className="flex items-center justify-between">
                      <code className="text-sm flex-1 mr-4">{str.content}</code>
                      <div className="flex gap-1">
                        <Badge variant="outline" className="text-xs">{str.address}</Badge>
                        {str.is_url && <Badge variant="default" className="text-xs">URL</Badge>}
                        {str.is_ip && <Badge variant="default" className="text-xs">IP</Badge>}
                        {str.is_suspicious && <Badge variant="destructive" className="text-xs">SUSPICIOUS</Badge>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="functions">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Code className="h-4 w-4" />Functions ({result.functions.length})</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>Address</TableHead><TableHead>Name</TableHead><TableHead>Size</TableHead><TableHead>Complexity</TableHead><TableHead>Basic Blocks</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                <TableBody>
                  {result.functions.map((func, index) => (
                    <TableRow key={index} className={func.is_suspicious ? 'bg-red-50' : ''}>
                      <TableCell className="font-mono">{func.address}</TableCell>
                      <TableCell className="font-mono">{func.name}</TableCell>
                      <TableCell>{formatBytes(func.size)}</TableCell>
                      <TableCell><div className="flex items-center gap-2"><span>{func.complexity_score}</span><Progress value={func.complexity_score * 100} className="w-12 h-2" /></div></TableCell>
                      <TableCell>{func.basic_blocks_count}</TableCell>
                      <TableCell>{func.is_suspicious ? <Badge variant="destructive">Suspicious</Badge> : <Badge variant="secondary">Normal</Badge>}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="callgraph">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Network className="h-4 w-4" />Call Graph Analysis</CardTitle></CardHeader>
            <CardContent>
              {result.call_graph ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-4 gap-4 mb-4">
                    <div className="text-center"><div className="text-2xl font-bold">{result.call_graph.nodes_count}</div><div className="text-sm text-muted-foreground">Functions</div></div>
                    <div className="text-center"><div className="text-2xl font-bold">{result.call_graph.edges_count}</div><div className="text-sm text-muted-foreground">Calls</div></div>
                    <div className="text-center"><div className="text-2xl font-bold">{result.call_graph.entry_points_count}</div><div className="text-sm text-muted-foreground">Entry Points</div></div>
                    <div className="text-center"><div className="text-2xl font-bold">{result.call_graph.complexity_score.toFixed(2)}</div><div className="text-sm text-muted-foreground">Complexity</div></div>
                  </div>
                  {onViewCallGraph && (
                    <Button onClick={onViewCallGraph} className="w-full">
                      <Eye className="h-4 w-4 mr-2" />
                      View Interactive Call Graph
                    </Button>
                  )}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <Network className="h-12 w-12 mx-auto mb-2" />
                  <p>Call graph not available</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="flex gap-2">
        {onDownloadReport && (
          <Button onClick={onDownloadReport}>
            <FileCheck className="h-4 w-4 mr-2" />
            Download Report
          </Button>
        )}
      </div>
    </div>
  );
}
