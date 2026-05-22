# KiloCode Provider Coverage

This report maps the local KiloCode snapshot into Stagewarden runtime categories.

- Snapshot providers discovered: 115
- Stagewarden supported models: 119
- Core runtime providers: 5
- Snapshot-backed runtime providers: 114

## Core Runtime Providers

| Provider | Backend | Auth | Default model | Model count | Model ids |
| --- | --- | --- | --- | --- | --- |
| `local` | `local/ollama` | `none` | `provider-default` | 11 | provider-default, qwen2.5-coder:7b, minimax-m2.7:cloud, qwen3.5:9b, gpt-oss:20b, sqlcoder:15b, ... (+5 more) |
| `cheap` | `cheap/openrouter` | `api_key` | `provider-default` | 172 | provider-default, anthropic/claude-3.5-haiku, anthropic/claude-3.7-sonnet, anthropic/claude-haiku-4.5, anthropic/claude-opus-4, anthropic/claude-opus-4.1, ... (+166 more) |
| `chatgpt` | `chatgpt/chatgpt-plan` | `chatgpt_plan_oauth` | `provider-default` | 9 | provider-default, codex-mini-latest, gpt-5.1-codex, gpt-5.1-codex-mini, gpt-5.2-codex, gpt-5.3-codex, ... (+3 more) |
| `claude` | `claude/sonnet` | `anthropic_api_key_or_claude_code_credentials` | `sonnet` | 6 | default, sonnet, opus, haiku, sonnet[1m], opusplan |
| `openai` | `@ai-sdk/openai` | `openai_api_key` | `chatgpt-image-latest` | 50 | chatgpt-image-latest, gpt-3.5-turbo, gpt-4, gpt-4-turbo, gpt-4.1, gpt-4.1-mini, ... (+44 more) |

## Snapshot-Backed Runtime Providers

These providers are first-class runtime options because Stagewarden now consumes the KiloCode snapshot directly. The full model lists live in the JSON companion file.

| Provider | Backend | Auth | Default model | Model count | Runtime class |
| --- | --- | --- | --- | --- | --- |
| `302ai` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMax-M1` | 95 | `snapshot-runtime` |
| `alibaba` | `@ai-sdk/openai-compatible` | `api_key` | `qvq-max` | 42 | `snapshot-runtime` |
| `scaleway` | `@ai-sdk/openai-compatible` | `api_key` | `bge-multilingual-gemma2` | 16 | `snapshot-runtime` |
| `nano-gpt` | `@ai-sdk/openai-compatible` | `api_key` | `Alibaba-NLP/Tongyi-DeepResearch-30B-A3B` | 518 | `snapshot-runtime` |
| `abacus` | `@ai-sdk/openai-compatible` | `api_key` | `Qwen/QwQ-32B` | 65 | `snapshot-runtime` |
| `perplexity-agent` | `@ai-sdk/openai` | `api_key` | `anthropic/claude-haiku-4-5` | 16 | `snapshot-runtime` |
| `siliconflow-cn` | `@ai-sdk/openai-compatible` | `api_key` | `ByteDance-Seed/Seed-OSS-36B-Instruct` | 79 | `snapshot-runtime` |
| `submodel` | `@ai-sdk/openai-compatible` | `api_key` | `Qwen/Qwen3-235B-A22B-Instruct-2507` | 9 | `snapshot-runtime` |
| `minimax-coding-plan` | `@ai-sdk/anthropic` | `api_key` | `MiniMax-M2` | 6 | `snapshot-runtime` |
| `perplexity` | `@ai-sdk/perplexity` | `api_key` | `sonar` | 4 | `snapshot-runtime` |
| `deepseek` | `@ai-sdk/openai-compatible` | `api_key` | `deepseek-chat` | 2 | `snapshot-runtime` |
| `llama` | `@ai-sdk/openai-compatible` | `api_key` | `cerebras-llama-4-maverick-17b-128e-instruct` | 7 | `snapshot-runtime` |
| `openrouter` | `@openrouter/ai-sdk-provider` | `openrouter_api_key` | `anthropic/claude-3.5-haiku` | 171 | `snapshot-runtime` |
| `tencent-token-plan` | `@ai-sdk/openai-compatible` | `api_key` | `hy3-preview` | 1 | `snapshot-runtime` |
| `fireworks-ai` | `@ai-sdk/openai-compatible` | `api_key` | `accounts/fireworks/models/deepseek-v3p1` | 17 | `snapshot-runtime` |
| `kimi-for-coding` | `@ai-sdk/anthropic` | `api_key` | `k2p5` | 2 | `snapshot-runtime` |
| `moark` | `@ai-sdk/openai-compatible` | `api_key` | `GLM-4.7` | 2 | `snapshot-runtime` |
| `opencode-go` | `@ai-sdk/openai-compatible` | `api_key` | `glm-5` | 9 | `snapshot-runtime` |
| `io-net` | `@ai-sdk/openai-compatible` | `api_key` | `Intel/Qwen3-Coder-480B-A35B-Instruct-int4-mixed-ar` | 17 | `snapshot-runtime` |
| `alibaba-cn` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMax-M2.5` | 76 | `snapshot-runtime` |
| `minimax-cn-coding-plan` | `@ai-sdk/anthropic` | `api_key` | `MiniMax-M2` | 6 | `snapshot-runtime` |
| `jiekou` | `@ai-sdk/openai-compatible` | `api_key` | `baidu/ernie-4.5-300b-a47b-paddle` | 61 | `snapshot-runtime` |
| `bailing` | `@ai-sdk/openai-compatible` | `api_key` | `Ling-1T` | 2 | `snapshot-runtime` |
| `iflowcn` | `@ai-sdk/openai-compatible` | `api_key` | `deepseek-r1` | 14 | `snapshot-runtime` |
| `v0` | `@ai-sdk/vercel` | `api_key` | `v0-1.0-md` | 3 | `snapshot-runtime` |
| `huggingface` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMaxAI/MiniMax-M2.1` | 22 | `snapshot-runtime` |
| `zenmux` | `@ai-sdk/openai-compatible` | `api_key` | `anthropic/claude-3.5-haiku` | 88 | `snapshot-runtime` |
| `upstage` | `@ai-sdk/openai-compatible` | `api_key` | `solar-mini` | 3 | `snapshot-runtime` |
| `novita-ai` | `@ai-sdk/openai-compatible` | `api_key` | `baichuan/baichuan-m2-32b` | 90 | `snapshot-runtime` |
| `xiaomi-token-plan-cn` | `@ai-sdk/openai-compatible` | `api_key` | `mimo-v2-omni` | 3 | `snapshot-runtime` |
| `wandb` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMaxAI/MiniMax-M2.5` | 17 | `snapshot-runtime` |
| `chutes` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMaxAI/MiniMax-M2.1-TEE` | 69 | `snapshot-runtime` |
| `dinference` | `@ai-sdk/openai-compatible` | `api_key` | `glm-4.7` | 3 | `snapshot-runtime` |
| `vivgrid` | `@ai-sdk/openai` | `api_key` | `deepseek-v3.2` | 12 | `snapshot-runtime` |
| `deepinfra` | `@ai-sdk/deepinfra` | `api_key` | `MiniMaxAI/MiniMax-M2` | 29 | `snapshot-runtime` |
| `qiniu-ai` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMax-M1` | 91 | `snapshot-runtime` |
| `kilo` | `@ai-sdk/openai-compatible` | `kilo_api_key` | `ai21/jamba-large-1.7` | 334 | `snapshot-runtime` |
| `sap-ai-core` | `@jerome-benoit/sap-ai-provider-v2` | `api_key` | `anthropic--claude-3-haiku` | 23 | `snapshot-runtime` |
| `morph` | `@ai-sdk/openai-compatible` | `api_key` | `auto` | 3 | `snapshot-runtime` |
| `cloudflare-ai-gateway` | `ai-gateway-provider` | `api_key` | `anthropic/claude-3-5-haiku` | 73 | `snapshot-runtime` |
| `github-copilot` | `@ai-sdk/openai-compatible` | `oauth_or_token` | `claude-haiku-4.5` | 26 | `snapshot-runtime` |
| `mixlayer` | `@ai-sdk/openai-compatible` | `api_key` | `qwen/qwen3.5-122b-a10b` | 5 | `snapshot-runtime` |
| `xiaomi-token-plan-sgp` | `@ai-sdk/openai-compatible` | `api_key` | `mimo-v2-omni` | 3 | `snapshot-runtime` |
| `zai` | `@ai-sdk/openai-compatible` | `api_key` | `glm-4.5` | 13 | `snapshot-runtime` |
| `opencode` | `@ai-sdk/openai-compatible` | `opencode_api_key` | `big-pickle` | 52 | `snapshot-runtime` |
| `stepfun` | `@ai-sdk/openai-compatible` | `api_key` | `step-1-32k` | 4 | `snapshot-runtime` |
| `nebius` | `@ai-sdk/openai-compatible` | `api_key` | `BAAI/bge-en-icl` | 49 | `snapshot-runtime` |
| `poe` | `@ai-sdk/openai-compatible` | `api_key` | `anthropic/claude-haiku-3` | 129 | `snapshot-runtime` |
| `helicone` | `@ai-sdk/openai-compatible` | `api_key` | `chatgpt-4o-latest` | 90 | `snapshot-runtime` |
| `ollama-cloud` | `@ai-sdk/openai-compatible` | `ollama_api_key` | `cogito-2.1:671b` | 36 | `snapshot-runtime` |
| `zai-coding-plan` | `@ai-sdk/openai-compatible` | `api_key` | `glm-4.5` | 13 | `snapshot-runtime` |
| `amazon-bedrock` | `@ai-sdk/amazon-bedrock` | `api_key` | `amazon.nova-2-lite-v1:0` | 92 | `snapshot-runtime` |
| `the-grid-ai` | `@ai-sdk/openai-compatible` | `api_key` | `text-max` | 3 | `snapshot-runtime` |
| `baseten` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMaxAI/MiniMax-M2.5` | 12 | `snapshot-runtime` |
| `zhipuai-coding-plan` | `@ai-sdk/openai-compatible` | `api_key` | `glm-4.5` | 14 | `snapshot-runtime` |
| `alibaba-coding-plan` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMax-M2.5` | 9 | `snapshot-runtime` |
| `venice` | `venice-ai-sdk-provider` | `api_key` | `aion-labs-aion-2-0` | 60 | `snapshot-runtime` |
| `aihubmix` | `@aihubmix/ai-sdk-provider` | `api_key` | `Kimi-K2-0905` | 52 | `snapshot-runtime` |
| `cerebras` | `@ai-sdk/cerebras` | `api_key` | `gpt-oss-120b` | 4 | `snapshot-runtime` |
| `firmware` | `@ai-sdk/openai-compatible` | `api_key` | `claude-haiku-4-5` | 24 | `snapshot-runtime` |
| `lmstudio` | `@ai-sdk/openai-compatible` | `api_key` | `openai/gpt-oss-20b` | 3 | `snapshot-runtime` |
| `lucidquery` | `@ai-sdk/openai-compatible` | `api_key` | `lucidnova-rf1-100b` | 2 | `snapshot-runtime` |
| `moonshotai-cn` | `@ai-sdk/openai-compatible` | `api_key` | `kimi-k2-0711-preview` | 6 | `snapshot-runtime` |
| `azure-cognitive-services` | `@ai-sdk/azure` | `api_key` | `claude-haiku-4-5` | 99 | `snapshot-runtime` |
| `wafer.ai` | `@ai-sdk/openai-compatible` | `api_key` | `GLM-5.1` | 2 | `snapshot-runtime` |
| `cohere` | `@ai-sdk/cohere` | `api_key` | `c4ai-aya-expanse-32b` | 12 | `snapshot-runtime` |
| `cloudferro-sherlock` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMaxAI/MiniMax-M2.5` | 5 | `snapshot-runtime` |
| `kuae-cloud-coding-plan` | `@ai-sdk/openai-compatible` | `api_key` | `GLM-4.7` | 1 | `snapshot-runtime` |
| `xai` | `@ai-sdk/xai` | `api_key` | `grok-2` | 25 | `snapshot-runtime` |
| `meganova` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMaxAI/MiniMax-M2.1` | 19 | `snapshot-runtime` |
| `google-vertex-anthropic` | `@ai-sdk/google-vertex/anthropic` | `api_key` | `claude-3-5-haiku@20241022` | 12 | `snapshot-runtime` |
| `evroc` | `@ai-sdk/openai-compatible` | `api_key` | `KBLab/kb-whisper-large` | 13 | `snapshot-runtime` |
| `synthetic` | `@ai-sdk/openai-compatible` | `api_key` | `hf:MiniMaxAI/MiniMax-M2` | 32 | `snapshot-runtime` |
| `nvidia` | `@ai-sdk/openai-compatible` | `api_key` | `black-forest-labs/flux.1-dev` | 77 | `snapshot-runtime` |
| `inference` | `@ai-sdk/openai-compatible` | `api_key` | `google/gemma-3` | 9 | `snapshot-runtime` |
| `inception` | `@ai-sdk/openai-compatible` | `api_key` | `mercury-2` | 2 | `snapshot-runtime` |
| `requesty` | `@ai-sdk/openai-compatible` | `api_key` | `anthropic/claude-3-7-sonnet` | 38 | `snapshot-runtime` |
| `digitalocean` | `@ai-sdk/openai-compatible` | `api_key` | `alibaba-qwen3-32b` | 46 | `snapshot-runtime` |
| `vultr` | `@ai-sdk/openai-compatible` | `api_key` | `DeepSeek-V3.2` | 5 | `snapshot-runtime` |
| `alibaba-coding-plan-cn` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMax-M2.5` | 9 | `snapshot-runtime` |
| `mistral` | `@ai-sdk/mistral` | `api_key` | `codestral-latest` | 27 | `snapshot-runtime` |
| `ovhcloud` | `@ai-sdk/openai-compatible` | `api_key` | `gpt-oss-120b` | 10 | `snapshot-runtime` |
| `friendli` | `@ai-sdk/openai-compatible` | `api_key` | `MiniMaxAI/MiniMax-M2.5` | 6 | `snapshot-runtime` |
| `cortecs` | `@ai-sdk/openai-compatible` | `api_key` | `claude-4-5-sonnet` | 33 | `snapshot-runtime` |
| `siliconflow` | `@ai-sdk/openai-compatible` | `api_key` | `ByteDance-Seed/Seed-OSS-36B-Instruct` | 73 | `snapshot-runtime` |
| `vercel` | `@ai-sdk/gateway` | `api_key` | `alibaba/qwen-3-14b` | 235 | `snapshot-runtime` |
| `minimax` | `@ai-sdk/anthropic` | `api_key` | `MiniMax-M2` | 6 | `snapshot-runtime` |
| `llmgateway` | `@ai-sdk/openai-compatible` | `api_key` | `auto` | 182 | `snapshot-runtime` |
| `google-vertex` | `@ai-sdk/google-vertex` | `api_key` | `deepseek-ai/deepseek-v3.1-maas` | 29 | `snapshot-runtime` |
| `cloudflare-workers-ai` | `@ai-sdk/openai-compatible` | `api_key` | `@cf/google/gemma-4-26b-a4b-it` | 7 | `snapshot-runtime` |
| `groq` | `@ai-sdk/groq` | `api_key` | `allam-2-7b` | 27 | `snapshot-runtime` |
| `azure` | `@ai-sdk/azure` | `azure_api_key` | `claude-haiku-4-5` | 105 | `snapshot-runtime` |
| `fastrouter` | `@ai-sdk/openai-compatible` | `api_key` | `anthropic/claude-opus-4.1` | 15 | `snapshot-runtime` |
| `stackit` | `@ai-sdk/openai-compatible` | `api_key` | `Qwen/Qwen3-VL-235B-A22B-Instruct-FP8` | 8 | `snapshot-runtime` |
| `tencent-coding-plan` | `@ai-sdk/openai-compatible` | `api_key` | `glm-5` | 8 | `snapshot-runtime` |
| `privatemode-ai` | `@ai-sdk/openai-compatible` | `api_key` | `gemma-3-27b` | 5 | `snapshot-runtime` |
| `google` | `@ai-sdk/google` | `google_api_key` | `gemini-1.5-flash` | 37 | `snapshot-runtime` |
| `drun` | `@ai-sdk/openai-compatible` | `api_key` | `public/deepseek-r1` | 3 | `snapshot-runtime` |
| `moonshotai` | `@ai-sdk/openai-compatible` | `api_key` | `kimi-k2-0711-preview` | 6 | `snapshot-runtime` |
| `berget` | `@ai-sdk/openai-compatible` | `api_key` | `google/gemma-4-31B-it` | 5 | `snapshot-runtime` |
| `github-models` | `@ai-sdk/openai-compatible` | `api_key` | `ai21-labs/ai21-jamba-1.5-large` | 55 | `snapshot-runtime` |
| `togetherai` | `@ai-sdk/togetherai` | `api_key` | `MiniMaxAI/MiniMax-M2.5` | 15 | `snapshot-runtime` |
| `qihang-ai` | `@ai-sdk/openai-compatible` | `api_key` | `claude-haiku-4-5-20251001` | 9 | `snapshot-runtime` |
| `tencent-tokenhub` | `@ai-sdk/openai-compatible` | `api_key` | `hy3-preview` | 1 | `snapshot-runtime` |
| `anthropic` | `@ai-sdk/anthropic` | `anthropic_api_key` | `claude-3-5-haiku-20241022` | 23 | `snapshot-runtime` |
| `modelscope` | `@ai-sdk/openai-compatible` | `api_key` | `Qwen/Qwen3-235B-A22B-Instruct-2507` | 7 | `snapshot-runtime` |
| `hpc-ai` | `@ai-sdk/openai-compatible` | `api_key` | `minimax/minimax-m2.5` | 3 | `snapshot-runtime` |
| `gitlab` | `gitlab-ai-provider` | `api_key` | `duo-chat-gpt-5-1` | 15 | `snapshot-runtime` |
| `xiaomi` | `@ai-sdk/openai-compatible` | `api_key` | `mimo-v2-flash` | 3 | `snapshot-runtime` |
| `clarifai` | `@ai-sdk/openai-compatible` | `api_key` | `arcee_ai/AFM/models/trinity-mini` | 11 | `snapshot-runtime` |
| `minimax-cn` | `@ai-sdk/anthropic` | `api_key` | `MiniMax-M2` | 6 | `snapshot-runtime` |
| `xiaomi-token-plan-ams` | `@ai-sdk/openai-compatible` | `api_key` | `mimo-v2-omni` | 3 | `snapshot-runtime` |
| `zhipuai` | `@ai-sdk/openai-compatible` | `api_key` | `glm-4.5` | 12 | `snapshot-runtime` |
| `nova` | `@ai-sdk/openai-compatible` | `api_key` | `nova-2-lite-v1` | 2 | `snapshot-runtime` |

## Runtime Notes

- Core providers keep bespoke UX, auth, and role defaults.
- Snapshot-backed providers use the generic provider registry path for routing, variants, and metadata.
- Use `stagewarden model list <provider>` or `stagewarden models --json` for the live runtime view.
