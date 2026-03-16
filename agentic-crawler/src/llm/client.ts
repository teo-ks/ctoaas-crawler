import Anthropic from '@anthropic-ai/sdk';
import OpenAI from 'openai';

export interface LLMMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface LLMUsage {
  inputTokens: number;
  outputTokens: number;
}

export interface LLMResponse {
  content: string;
  usage: LLMUsage;
}

export interface LLMClient {
  complete(messages: LLMMessage[], model: string): Promise<LLMResponse>;
}

// ---------------------------------------------------------------------------
// Pricing table — per 1M tokens (input / output)
// Add entries as needed; unknown models fall back to token-count-only logging.
// ---------------------------------------------------------------------------
const PRICING_PER_1M: Record<string, { input: number; output: number }> = {
  'claude-haiku-4-5-20251001':        { input: 0.80,  output: 4.00  },
  'claude-haiku-4-5':                 { input: 0.80,  output: 4.00  },
  'claude-sonnet-4-6':                { input: 3.00,  output: 15.00 },
  'claude-opus-4-6':                  { input: 15.00, output: 75.00 },
  // AWS Bedrock models (via LiteLLM)
  'bedrock-claude-haiku-3':           { input: 0.25,  output: 1.25  },
  'bedrock-claude-haiku-3-5':         { input: 0.80,  output: 4.00  },
  'bedrock-claude-sonnet-4':          { input: 3.00,  output: 15.00 },
  'bedrock-claude-sonnet-4-5':        { input: 3.00,  output: 15.00 },
  // Google (via LiteLLM)
  'google-gemini-3-flash':            { input: 0.15,  output: 0.60  },
  'gemini/gemini-2.0-flash':          { input: 0.15,  output: 0.60  },
};

export function estimateCost(usage: LLMUsage, model: string): number | null {
  const pricing = PRICING_PER_1M[model];
  if (!pricing) return null;
  return (usage.inputTokens / 1_000_000) * pricing.input
       + (usage.outputTokens / 1_000_000) * pricing.output;
}

// ---------------------------------------------------------------------------
// CostTracker — accumulates usage across all LLM calls in one crawl run
// ---------------------------------------------------------------------------
export class CostTracker {
  private totalInput = 0;
  private totalOutput = 0;
  private callCount = 0;

  record(usage: LLMUsage, model: string, label: string): void {
    this.totalInput  += usage.inputTokens;
    this.totalOutput += usage.outputTokens;
    this.callCount++;

    const cost = estimateCost(usage, model);
    const costStr = cost !== null ? `$${cost.toFixed(4)}` : 'unknown pricing';
    console.log(
      `[tokens] ${label} | in:${usage.inputTokens.toLocaleString()} out:${usage.outputTokens.toLocaleString()} | ${costStr} | model:${model}`
    );
  }

  summary(): void {
    const model = process.env.LLM_MODEL ?? '';
    const pricing = PRICING_PER_1M[model];
    const totalCost = pricing
      ? (this.totalInput / 1_000_000) * pricing.input
      + (this.totalOutput / 1_000_000) * pricing.output
      : null;
    const costStr = totalCost !== null ? `$${totalCost.toFixed(4)}` : 'unknown pricing';

    // Write to stderr so Crawlee's stdout carriage-return stats don't overwrite it
    process.stderr.write(
      `\n[tokens] TOTAL | ${this.callCount} calls | in:${this.totalInput.toLocaleString()} out:${this.totalOutput.toLocaleString()} | est. ${costStr} | model:${model}\n`
    );
  }
}

// ---------------------------------------------------------------------------
// Anthropic SDK client — used when LLM_BASE_URL is not set
// ---------------------------------------------------------------------------
class AnthropicClient implements LLMClient {
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY!,
    });
  }

  async complete(messages: LLMMessage[], model: string): Promise<LLMResponse> {
    const response = await this.client.messages.create({
      model,
      max_tokens: 4096,
      messages,
    });
    const block = response.content[0];
    if (block.type !== 'text') throw new Error('Unexpected non-text response from Anthropic');
    return {
      content: block.text,
      usage: {
        inputTokens: response.usage.input_tokens,
        outputTokens: response.usage.output_tokens,
      },
    };
  }
}

// ---------------------------------------------------------------------------
// OpenAI-compatible client — used when LLM_BASE_URL is set (LiteLLM, OpenRouter, etc.)
// ---------------------------------------------------------------------------
class OpenAICompatibleClient implements LLMClient {
  private client: OpenAI;

  constructor(baseURL: string) {
    this.client = new OpenAI({
      apiKey: process.env.LLM_API_KEY || process.env.ANTHROPIC_API_KEY || 'dummy',
      baseURL,
    });
  }

  async complete(messages: LLMMessage[], model: string): Promise<LLMResponse> {
    const response = await this.client.chat.completions.create({
      model,
      messages,
      max_tokens: 4096,
    });
    return {
      content: response.choices[0]?.message?.content ?? '',
      usage: {
        inputTokens:  response.usage?.prompt_tokens     ?? 0,
        outputTokens: response.usage?.completion_tokens ?? 0,
      },
    };
  }
}

// ---------------------------------------------------------------------------
// Factory — auto-selects client based on environment
// ---------------------------------------------------------------------------
export function createLLMClient(): LLMClient {
  const rawBaseURL = process.env.LLM_BASE_URL;
  if (rawBaseURL) {
    // Strip trailing endpoint paths so the OpenAI SDK can append its own paths cleanly
    const baseURL = rawBaseURL
      .replace(/\/chat\/completions\/?$/, '')
      .replace(/\/completions\/?$/, '')
      .replace(/\/v1\/?$/, '');
    console.log(`[llm] Using OpenAI-compatible client → ${baseURL}`);
    return new OpenAICompatibleClient(baseURL);
  }
  console.log('[llm] Using Anthropic client (direct)');
  return new AnthropicClient();
}

export const DEFAULT_MODEL =
  process.env.LLM_MODEL || 'claude-haiku-4-5-20251001';

export const FALLBACK_MODEL =
  process.env.LLM_FALLBACK_MODEL || 'claude-sonnet-4-6';
