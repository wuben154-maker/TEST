-- Create shared_reports table for public link sharing
CREATE TABLE public.shared_reports (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT 'Security Analysis Report',
  blocks JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  expires_at TIMESTAMP WITH TIME ZONE DEFAULT (now() + interval '7 days')
);

-- Enable RLS
ALTER TABLE public.shared_reports ENABLE ROW LEVEL SECURITY;

-- Anyone can view shared reports (public links)
CREATE POLICY "Shared reports are publicly viewable"
ON public.shared_reports
FOR SELECT
USING (expires_at IS NULL OR expires_at > now());

-- Users can create their own shared reports
CREATE POLICY "Users can create shared reports"
ON public.shared_reports
FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- Users can delete their own shared reports
CREATE POLICY "Users can delete own shared reports"
ON public.shared_reports
FOR DELETE
USING (auth.uid() = user_id);