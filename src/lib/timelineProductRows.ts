/**
 * Product timeline presentation model (agent-timeline-product-ui).
 *
 * Canonical SSE rows (`AnalysisTimelineEntry`) are reduced for UI in
 * `buildTimelineActivityChunks` (tool explore + delegation + subagent + task_board + HITL)
 * and `buildReActTimeline` (v0-style ReAct blocks for the main trace). Mapping reference:
 *
 * | SSE `type`        | Primary surface                                      |
 * |-------------------|------------------------------------------------------|
 * | reasoning         | Text (ReAct thinking blocks / ThinkingBlockView)     |
 * | tool_call/result  | Tool lines (explore merge, humanizeToolCallLine)     |
 * | task_plan / task_*| Task board chunk + live `taskPlan` state             |
 * | parameter_request | Inline `ParameterInput` when present on timeline       |
 * | decision_request  | Inline `UserDecision` when present on timeline       |
 * | step              | Text line (filtered by shouldHideStepRow)            |
 * | conclusion        | Assistant message / workspace (not explore strip)    |
 *
 * Discriminated kinds for future dedicated renderers / tests:
 */
export type ProductTimelineRowKind =
  | 'text'
  | 'tool_line'
  | 'task_block'
  | 'user_input'
  | 'delegation_line';

export type ProductTimelineRow =
  | { kind: 'text'; key: string; text: string }
  | { kind: 'tool_line'; key: string; toolName: string; line: string; hasResult: boolean }
  | { kind: 'task_block'; key: string; firstSeq: number }
  | { kind: 'user_input'; key: string; inputKind: 'parameter' | 'decision'; seq: number }
  | { kind: 'delegation_line'; key: string; subagent: string; task: string };
