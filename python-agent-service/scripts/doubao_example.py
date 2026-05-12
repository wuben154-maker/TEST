#!/usr/bin/env python3
"""Doubao (Volcano Ark) API example using volcenginesdkarkruntime.

Requires: pip install volcenginesdkarkruntime

Environment: ARK_API_KEY (or DOUBAO_API_KEY) - API Key from Volcano Console
Ref: https://www.volcengine.com/docs/82379/1399008
"""

import os
from volcenginesdkarkruntime import Ark

# API Key from env (ARK_API_KEY or DOUBAO_API_KEY for project convention)
api_key = os.getenv("ARK_API_KEY") or os.getenv("DOUBAO_API_KEY")

client = Ark(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=api_key,
)

# Create chat request
response = client.responses.create(
    model="doubao-seed-2-0-pro-260215",
    stream=True,
    messages=[{"role": "user", "content": []}],
    max_output_tokens=131072,
    reasoning={"effort": "high"},
)

print(response)
