/**
 * Gradient text + shimmer used for streaming reasoning and running ReAct / task steps.
 * Motion uses Tailwind ``animate-shimmer`` (linear timing, 2s period) for a steady loop without ease-in-out pauses.
 */
export const REASONING_STREAM_SHIMMER_CLASS =
  'bg-gradient-to-r from-muted-foreground/70 via-sky-200/95 to-muted-foreground/70 bg-[length:200%_100%] bg-clip-text text-transparent animate-shimmer dark:from-sky-300/50 dark:via-sky-100 dark:to-sky-300/50';
