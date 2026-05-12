-- 修复 parameter_callbacks 表的 RLS 策略，使其更安全

-- 删除过于宽松的策略
DROP POLICY IF EXISTS "Anyone can view callbacks by request_id" ON public.parameter_callbacks;
DROP POLICY IF EXISTS "Anyone can insert callbacks" ON public.parameter_callbacks;
DROP POLICY IF EXISTS "Anyone can update pending callbacks" ON public.parameter_callbacks;

-- 创建更严格的策略（基于 session_id 匹配）
CREATE POLICY "View callbacks by session" 
ON public.parameter_callbacks 
FOR SELECT 
USING (
    session_id = current_setting('request.headers', true)::json->>'x-session-id'
    OR session_id = current_setting('request.headers', true)::json->>'x-request-id'
);

CREATE POLICY "Insert callbacks for session" 
ON public.parameter_callbacks 
FOR INSERT 
WITH CHECK (
    session_id IS NOT NULL 
    AND request_id IS NOT NULL
);

CREATE POLICY "Update pending callbacks for session" 
ON public.parameter_callbacks 
FOR UPDATE 
USING (
    status = 'pending'
    AND (
        session_id = current_setting('request.headers', true)::json->>'x-session-id'
        OR session_id = current_setting('request.headers', true)::json->>'x-request-id'
    )
);