export type FormatThoughtDurationOptions = {
  /**
   * When the model produced no visible reasoning and no text, use “Thought brief …”
   * instead of “Thought …”.
   */
  brief?: boolean;
};

function formatSecondsDisplay(seconds: number): string {
  const s = Math.max(0, Number(seconds));
  if (s < 10) {
    return `${s.toFixed(1)}s`;
  }
  return `${Math.round(s)}s`;
}

/**
 * In-progress thinking row: always “Thinking …s”, never “Thought …” / “Thought brief …”.
 * Same numeric rules as {@link formatThoughtDuration}.
 */
export function formatThinkingElapsed(seconds: number): string {
  return `Thinking ${formatSecondsDisplay(seconds)}`;
}

/**
 * Fixed English label for wall-clock thinking duration (all locales; matches stored numeric replay).
 *
 * Displays one decimal place for values under 10 seconds so sub-second and short
 * durations are not rounded to 0.  Values ≥ 10 s are shown as whole seconds.
 */
export function formatThoughtDuration(
  seconds: number,
  options?: FormatThoughtDurationOptions,
): string {
  const prefix = options?.brief ? 'Thought brief' : 'Thought';
  return `${prefix} ${formatSecondsDisplay(seconds)}`;
}
