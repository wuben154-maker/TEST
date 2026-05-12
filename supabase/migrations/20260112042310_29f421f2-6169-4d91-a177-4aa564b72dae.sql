-- 创建会话参数存储表（支持加密存储长期记忆）
CREATE TABLE public.session_parameters (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id UUID REFERENCES auth.users(id),
    param_name TEXT NOT NULL,
    param_value TEXT NOT NULL,  -- 加密存储的值
    param_type TEXT NOT NULL DEFAULT 'text',
    encrypted BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE,  -- 可选的过期时间
    metadata JSONB DEFAULT '{}',
    UNIQUE(session_id, param_name)
);

-- 创建索引
CREATE INDEX idx_session_parameters_session ON public.session_parameters(session_id);
CREATE INDEX idx_session_parameters_user ON public.session_parameters(user_id);
CREATE INDEX idx_session_parameters_expires ON public.session_parameters(expires_at) WHERE expires_at IS NOT NULL;

-- 启用 RLS
ALTER TABLE public.session_parameters ENABLE ROW LEVEL SECURITY;

-- RLS 策略：用户只能访问自己的参数（或匿名会话的参数）
CREATE POLICY "Users can view their own parameters" 
ON public.session_parameters 
FOR SELECT 
USING (
    user_id = auth.uid() 
    OR (user_id IS NULL AND session_id = current_setting('request.headers', true)::json->>'x-session-id')
);

CREATE POLICY "Users can insert their own parameters" 
ON public.session_parameters 
FOR INSERT 
WITH CHECK (
    user_id = auth.uid() 
    OR user_id IS NULL
);

CREATE POLICY "Users can update their own parameters" 
ON public.session_parameters 
FOR UPDATE 
USING (
    user_id = auth.uid() 
    OR (user_id IS NULL AND session_id = current_setting('request.headers', true)::json->>'x-session-id')
);

CREATE POLICY "Users can delete their own parameters" 
ON public.session_parameters 
FOR DELETE 
USING (
    user_id = auth.uid() 
    OR (user_id IS NULL AND session_id = current_setting('request.headers', true)::json->>'x-session-id')
);

-- 自动更新 updated_at
CREATE TRIGGER update_session_parameters_updated_at
BEFORE UPDATE ON public.session_parameters
FOR EACH ROW
EXECUTE FUNCTION public.update_updated_at_column();

-- 创建参数回调队列表（支持高并发）
CREATE TABLE public.parameter_callbacks (
    id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL UNIQUE,  -- 用于回调匹配
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, completed, expired
    parameters JSONB,  -- 用户提交的参数
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    completed_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (now() + interval '30 minutes')
);

-- 索引
CREATE INDEX idx_parameter_callbacks_session ON public.parameter_callbacks(session_id);
CREATE INDEX idx_parameter_callbacks_request ON public.parameter_callbacks(request_id);
CREATE INDEX idx_parameter_callbacks_status ON public.parameter_callbacks(status) WHERE status = 'pending';

-- RLS
ALTER TABLE public.parameter_callbacks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view callbacks by request_id"
ON public.parameter_callbacks
FOR SELECT
USING (true);

CREATE POLICY "Anyone can insert callbacks"
ON public.parameter_callbacks
FOR INSERT
WITH CHECK (true);

CREATE POLICY "Anyone can update pending callbacks"
ON public.parameter_callbacks
FOR UPDATE
USING (status = 'pending');