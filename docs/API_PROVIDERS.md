# API Provider Configuration Guide

ActionSync supports both direct API access and Azure-hosted APIs for Claude and OpenAI services. This guide explains how to configure each option.

## Overview

ActionSync uses two types of AI services:
1. **LLM (Language Model)**: Claude for processing meetings, answering questions, and working on tickets
2. **Embeddings**: OpenAI embeddings for semantic search of meeting history

Each service can be configured to use either direct API access or Azure-hosted versions.

## LLM Provider Configuration

### Option 1: Direct Anthropic API (Recommended for most users)

**Advantages:**
- No Azure subscription required
- Simple setup with just an API key
- Direct access to latest Claude models

**Setup:**
1. Get an API key from [console.anthropic.com](https://console.anthropic.com/)
2. Set environment variables:
   ```bash
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=your-api-key-here
   ANTHROPIC_MODEL=claude-opus-4-20250514  # Optional, defaults to claude-opus-4-20250514
   ```

### Option 2: Azure Anthropic

**Advantages:**
- Enterprise Azure integration
- Azure billing and cost management
- Compliance with Azure data residency requirements

**Setup:**
1. Deploy Claude via Azure Anthropic service
2. Set environment variables:
   ```bash
   LLM_PROVIDER=azure_anthropic
   AZURE_ANTHROPIC_ENDPOINT=https://your-endpoint.azure.com
   AZURE_ANTHROPIC_API_KEY=your-azure-api-key
   AZURE_ANTHROPIC_MODEL=claude-opus-4-5  # Optional
   ```

## Embedding Provider Configuration

Embeddings are optional and only needed for semantic search of meeting history.

### Option 1: Direct OpenAI API (Recommended for most users)

**Advantages:**
- No Azure subscription required
- Simple setup with just an API key

**Setup:**
1. Get an API key from [platform.openai.com](https://platform.openai.com/)
2. Set environment variables:
   ```bash
   EMBEDDING_PROVIDER=openai
   OPENAI_API_KEY=your-openai-api-key
   OPENAI_EMBEDDING_MODEL=text-embedding-3-small  # Optional
   ```

### Option 2: Azure OpenAI

**Advantages:**
- Enterprise Azure integration
- Azure billing and cost management

**Setup:**
1. Deploy OpenAI embeddings via Azure OpenAI service
2. Set environment variables:
   ```bash
   EMBEDDING_PROVIDER=azure_openai
   AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
   AZURE_OPENAI_API_KEY=your-azure-openai-key
   AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small  # Your deployment name
   ```

## Migration from Azure-Only Configuration

If you were using the Azure-only version of ActionSync, your existing configuration will continue to work without changes. The defaults are:
- `LLM_PROVIDER=azure_anthropic`
- `EMBEDDING_PROVIDER=azure_openai`

To migrate to direct APIs:
1. Get API keys from Anthropic and/or OpenAI
2. Update your `.env` file with the new provider settings
3. Restart the application

## Example Configurations

### Example 1: Direct APIs (No Azure)
```bash
# LLM via direct Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Embeddings via direct OpenAI
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### Example 2: Azure Only (Original Configuration)
```bash
# LLM via Azure Anthropic
LLM_PROVIDER=azure_anthropic
AZURE_ANTHROPIC_ENDPOINT=https://your-endpoint.azure.com
AZURE_ANTHROPIC_API_KEY=your-key

# Embeddings via Azure OpenAI
EMBEDDING_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
AZURE_OPENAI_API_KEY=your-key
```

### Example 3: Mixed Configuration
```bash
# LLM via direct Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Embeddings via Azure OpenAI
EMBEDDING_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
AZURE_OPENAI_API_KEY=your-key
```

## Cost Considerations

### Direct API Pricing
- **Anthropic**: Pay-as-you-go pricing based on tokens used. See [anthropic.com/pricing](https://www.anthropic.com/pricing)
- **OpenAI**: Pay-as-you-go pricing based on tokens used. See [openai.com/pricing](https://openai.com/pricing)

### Azure Pricing
- Azure pricing may differ from direct API pricing
- Check Azure Marketplace for current pricing
- Azure may offer enterprise discounts and reserved capacity

## Troubleshooting

### "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
Make sure you've set the `ANTHROPIC_API_KEY` environment variable when using direct Anthropic API.

### "AZURE_ANTHROPIC_ENDPOINT and AZURE_ANTHROPIC_API_KEY are required"
Make sure both endpoint and API key are set when using Azure Anthropic.

### Embeddings not working
Embeddings are optional. If not configured, the application will work but semantic search will fall back to simple text search. Check logs for "embeddings will be disabled" messages.

### Unsupported provider error
Valid values for `LLM_PROVIDER` are: `anthropic`, `azure_anthropic`
Valid values for `EMBEDDING_PROVIDER` are: `openai`, `azure_openai`
