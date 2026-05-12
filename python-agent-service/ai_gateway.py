"""
AI Gateway - 自定义多模型网关服务
支持 Gemini 和豆包(Doubao) 模型

使用方法:
1. 安装依赖: pip install -r requirements.txt
2. 配置环境变量或 config.yaml
3. 运行: python ai_gateway.py

支持的模型:
- Gemini: gemini-2.5-flash, gemini-2.5-pro, gemini-1.5-flash, gemini-1.5-pro
- 豆包: doubao-pro-32k, doubao-lite-32k, doubao-pro-128k
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import yaml
import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Provider(str, Enum):
    GEMINI = "gemini"
    DOUBAO = "doubao"
    AUTO = "auto"


@dataclass
class ProviderConfig:
    base_url: str
    models: List[str]
    default_model: str


PROVIDERS: Dict[str, ProviderConfig] = {
    "gemini": ProviderConfig(
        base_url=os.environ.get("GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
        models=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"],
        default_model="gemini-2.5-flash"
    ),
    "doubao": ProviderConfig(
        base_url=os.environ.get("DOUBAO_API_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        models=["doubao-pro-32k", "doubao-lite-32k", "doubao-pro-128k"],
        default_model="doubao-pro-32k"
    )
}


class EncryptedConfig:
    """加密配置管理器"""
    
    def __init__(self, config_path: str = "config.yaml", password: Optional[str] = None):
        self.config_path = Path(config_path)
        self.password = password or os.environ.get("CONFIG_PASSWORD", "default-password-change-me")
        self._fernet = self._create_fernet()
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _create_fernet(self) -> Fernet:
        """创建加密器"""
        salt = b"ai-gateway-salt-v1"  # 固定salt，实际生产中应该随机生成并存储
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.password.encode()))
        return Fernet(key)
    
    def encrypt(self, value: str) -> str:
        """加密字符串"""
        return self._fernet.encrypt(value.encode()).decode()
    
    def decrypt(self, encrypted_value: str) -> str:
        """解密字符串"""
        try:
            return self._fernet.decrypt(encrypted_value.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt value: {e}")
            raise ValueError("Failed to decrypt configuration value")
    
    def _load_config(self):
        """加载配置文件"""
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}
    
    def _save_config(self):
        """保存配置文件"""
        with open(self.config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False)
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """获取解密后的API密钥"""
        encrypted = self._config.get("api_keys", {}).get(provider)
        if encrypted:
            return self.decrypt(encrypted)
        # Fallback to environment variables
        env_var = f"{provider.upper()}_API_KEY"
        return os.environ.get(env_var)
    
    def set_api_key(self, provider: str, api_key: str):
        """设置加密的API密钥"""
        if "api_keys" not in self._config:
            self._config["api_keys"] = {}
        self._config["api_keys"][provider] = self.encrypt(api_key)
        self._save_config()
        logger.info(f"API key for {provider} saved (encrypted)")


# Pydantic models
class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class FunctionDef(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class ToolDef(BaseModel):
    type: str = "function"
    function: FunctionDef


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    provider: Provider = Provider.AUTO
    stream: bool = False
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[ToolDef]] = None
    tool_choice: Optional[Any] = None


class ChatChoice(BaseModel):
    index: int = 0
    message: Optional[Dict[str, Any]] = None
    delta: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None


class ChatResponse(BaseModel):
    id: str = "chatcmpl-gateway"
    object: str = "chat.completion"
    choices: List[ChatChoice]
    model: str = ""
    usage: Optional[Dict[str, int]] = None


# FastAPI app
app = FastAPI(
    title="AI Gateway",
    description="Multi-model AI gateway supporting Gemini and Doubao",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global config
config = EncryptedConfig()


def convert_to_gemini_format(messages: List[ChatMessage], tools: Optional[List[ToolDef]] = None) -> Dict[str, Any]:
    """Convert OpenAI format to Gemini format"""
    system_instruction = "\n".join(
        m.content for m in messages if m.role == "system"
    )
    
    contents = [
        {
            "role": "model" if m.role == "assistant" else "user",
            "parts": [{"text": m.content}]
        }
        for m in messages if m.role not in ("system", "tool")
    ]
    
    body: Dict[str, Any] = {"contents": contents}
    
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    
    if tools:
        body["tools"] = [{
            "functionDeclarations": [
                {
                    "name": t.function.name,
                    "description": t.function.description or "",
                    "parameters": t.function.parameters or {}
                }
                for t in tools
            ]
        }]
    
    return body


async def call_gemini(
    api_key: str,
    model: str,
    messages: List[ChatMessage],
    stream: bool,
    tools: Optional[List[ToolDef]] = None
) -> AsyncGenerator[str, None]:
    """Call Gemini API"""
    endpoint = "streamGenerateContent" if stream else "generateContent"
    url = f"{PROVIDERS['gemini'].base_url}/models/{model}:{endpoint}"
    params = {"key": api_key}
    if stream:
        params["alt"] = "sse"
    
    body = convert_to_gemini_format(messages, tools)
    body["generationConfig"] = {"temperature": 0.7}
    
    logger.info(f"Calling Gemini: {model}, stream={stream}")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        if stream:
            async with client.stream("POST", url, params=params, json=body) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise HTTPException(status_code=response.status_code, detail=error_text.decode())
                
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    
                    try:
                        data = json.loads(line[6:])
                        content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        
                        chunk = {
                            "choices": [{
                                "delta": {"content": content},
                                "index": 0
                            }]
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                    except json.JSONDecodeError:
                        continue
                
                yield "data: [DONE]\n\n"
        else:
            response = await client.post(url, params=params, json=body)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            
            data = response.json()
            content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            
            result = ChatResponse(
                choices=[ChatChoice(
                    message={"role": "assistant", "content": content}
                )],
                model=model
            )
            yield result.model_dump_json()


async def call_doubao(
    api_key: str,
    model: str,
    messages: List[ChatMessage],
    stream: bool,
    tools: Optional[List[ToolDef]] = None
) -> AsyncGenerator[str, None]:
    """Call Doubao API (OpenAI compatible)"""
    url = f"{PROVIDERS['doubao'].base_url}/chat/completions"
    
    body = {
        "model": model,
        "messages": [m.model_dump(exclude_none=True) for m in messages],
        "stream": stream
    }
    
    if tools:
        body["tools"] = [t.model_dump() for t in tools]
    
    logger.info(f"Calling Doubao: {model}, stream={stream}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        if stream:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise HTTPException(status_code=response.status_code, detail=error_text.decode())
                
                async for line in response.aiter_lines():
                    if line:
                        yield f"{line}\n\n"
        else:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            
            yield response.text


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "providers": list(PROVIDERS.keys())}


@app.get("/v1/models")
async def list_models():
    """List available models"""
    models = []
    for provider_name, provider_config in PROVIDERS.items():
        for model in provider_config.models:
            models.append({
                "id": f"{provider_name}/{model}",
                "object": "model",
                "owned_by": provider_name
            })
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """OpenAI-compatible chat completions endpoint"""
    
    # Determine provider
    provider = request.provider
    if provider == Provider.AUTO:
        if request.model and request.model.startswith("doubao"):
            provider = Provider.DOUBAO
        else:
            provider = Provider.GEMINI
    
    # Get API key
    api_key = config.get_api_key(provider.value)
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=f"API key for {provider.value} not configured"
        )
    
    # Determine model
    provider_config = PROVIDERS[provider.value]
    model = request.model
    if not model or not any(m in model for m in provider_config.models):
        model = provider_config.default_model
    
    logger.info(f"Request: provider={provider.value}, model={model}, stream={request.stream}")
    
    # Call provider
    if provider == Provider.GEMINI:
        generator = call_gemini(api_key, model, request.messages, request.stream, request.tools)
    else:
        generator = call_doubao(api_key, model, request.messages, request.stream, request.tools)
    
    if request.stream:
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )
    else:
        result = ""
        async for chunk in generator:
            result = chunk
        return JSONResponse(content=json.loads(result))


@app.post("/admin/set-api-key")
async def set_api_key(provider: str, api_key: str):
    """Set encrypted API key (admin endpoint)"""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    
    config.set_api_key(provider, api_key)
    return {"status": "success", "message": f"API key for {provider} saved (encrypted)"}


# CLI for setting up API keys
def setup_keys():
    """Interactive CLI for setting up API keys"""
    import getpass
    
    print("=" * 50)
    print("AI Gateway - API Key Setup")
    print("=" * 50)
    print("\nThis will securely store your API keys in encrypted config.\n")
    
    password = getpass.getpass("Enter encryption password: ")
    cfg = EncryptedConfig(password=password)
    
    for provider in PROVIDERS.keys():
        current = cfg.get_api_key(provider)
        status = "configured" if current else "not set"
        print(f"\n{provider.upper()} API Key ({status})")
        
        api_key = getpass.getpass(f"Enter {provider} API key (or press Enter to skip): ")
        if api_key:
            cfg.set_api_key(provider, api_key)
            print(f"✓ {provider} API key saved (encrypted)")
    
    print("\n" + "=" * 50)
    print("Setup complete! Run the server with:")
    print("  uvicorn ai_gateway:app --host 0.0.0.0 --port 8000")
    print("=" * 50)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        setup_keys()
    else:
        import uvicorn
        port = int(os.environ.get("PORT", 8000))
        uvicorn.run(app, host="0.0.0.0", port=port)
