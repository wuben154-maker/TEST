-- Optional: row-level security for Supabase (requires auth.uid()).
-- Apply AFTER 20260407120000_context_memory_layers.sql on a Supabase Postgres instance.
-- Do not run on vanilla local Postgres unless the auth schema/JWT helpers exist.

ALTER TABLE public.project_derived_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_memory_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.context_memory_merge_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their own project derived memory" ON public.project_derived_memory;
CREATE POLICY "Users can view their own project derived memory"
  ON public.project_derived_memory FOR SELECT
  USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can upsert their own project derived memory" ON public.project_derived_memory;
CREATE POLICY "Users can upsert their own project derived memory"
  ON public.project_derived_memory FOR INSERT
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own project derived memory" ON public.project_derived_memory;
CREATE POLICY "Users can update their own project derived memory"
  ON public.project_derived_memory FOR UPDATE
  USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own project derived memory" ON public.project_derived_memory;
CREATE POLICY "Users can delete their own project derived memory"
  ON public.project_derived_memory FOR DELETE
  USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can view their own user memory index" ON public.user_memory_index;
CREATE POLICY "Users can view their own user memory index"
  ON public.user_memory_index FOR SELECT
  USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can upsert their own user memory index" ON public.user_memory_index;
CREATE POLICY "Users can upsert their own user memory index"
  ON public.user_memory_index FOR INSERT
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own user memory index" ON public.user_memory_index;
CREATE POLICY "Users can update their own user memory index"
  ON public.user_memory_index FOR UPDATE
  USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own user memory index" ON public.user_memory_index;
CREATE POLICY "Users can delete their own user memory index"
  ON public.user_memory_index FOR DELETE
  USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can view their own merge log rows" ON public.context_memory_merge_log;
CREATE POLICY "Users can view their own merge log rows"
  ON public.context_memory_merge_log FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = context_memory_merge_log.project_id AND p.user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS "Users can insert merge log for own projects" ON public.context_memory_merge_log;
CREATE POLICY "Users can insert merge log for own projects"
  ON public.context_memory_merge_log FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = context_memory_merge_log.project_id AND p.user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS "Users can delete merge log for own projects" ON public.context_memory_merge_log;
CREATE POLICY "Users can delete merge log for own projects"
  ON public.context_memory_merge_log FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = context_memory_merge_log.project_id AND p.user_id = auth.uid()
    )
  );
