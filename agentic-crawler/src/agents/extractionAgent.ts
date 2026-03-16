import { type LLMClient, type CostTracker, DEFAULT_MODEL, FALLBACK_MODEL } from '../llm/client.js';
import { type FaqPair } from '../schemas/faq.js';
import { cleanHtml, estimateTokens } from '../utils/htmlCleaner.js';

// ~60k tokens of HTML is the safe ceiling before costs spike
const MAX_TOKEN_BUDGET = 60_000;

// Patterns that indicate the LLM couldn't find a real answer
const JUNK_ANSWER_PATTERNS = [
  /not directly addressed/i,
  /not mentioned in the (provided |given )?html/i,
  /^placeholder/i,
  /no (faq|information) (found|available)/i,
];

const SYSTEM_PROMPT = `You are a precise data extraction agent. Your only job is to extract FAQ question-and-answer pairs from HTML.

Rules:
- Only extract content that is explicitly present in the HTML — never infer or fabricate
- Each pair must have BOTH a distinct question AND a distinct answer — never copy the question as the answer
- If an answer spans multiple paragraphs, join them with newline characters
- If the FAQ items belong to a named section or category, include it in the "category" field
- Return ONLY valid JSON — no markdown fences, no explanation, nothing else

Output format:
{"pairs": [{"question": "...", "answer": "...", "category": "..."}]}

If no FAQ pairs are found, return exactly: {"pairs": []}`;

export async function extractFaqPairs(
  rawHtml: string,
  pageUrl: string,
  llmClient: LLMClient,
  costTracker?: CostTracker
): Promise<FaqPair[]> {
  const cleaned = cleanHtml(rawHtml);

  // Truncate if too large to avoid context overflow
  let content = cleaned;
  const tokens = estimateTokens(cleaned);
  if (tokens > MAX_TOKEN_BUDGET) {
    console.warn(
      `[extraction] HTML ~${tokens} est. tokens — truncating to budget for ${pageUrl}`
    );
    content = cleaned.slice(0, MAX_TOKEN_BUDGET * 4);
  }

  const messages = [
    {
      role: 'user' as const,
      content: `${SYSTEM_PROMPT}\n\nSource URL: ${pageUrl}\n\nHTML:\n${content}`,
    },
  ];

  let responseContent: string;
  try {
    const response = await llmClient.complete(messages, DEFAULT_MODEL);
    responseContent = response.content;
    costTracker?.record(response.usage, DEFAULT_MODEL, pageUrl);
  } catch (err) {
    console.warn(`[extraction] Primary model failed for ${pageUrl} — trying fallback:`, err);
    const response = await llmClient.complete(messages, FALLBACK_MODEL);
    responseContent = response.content;
    costTracker?.record(response.usage, FALLBACK_MODEL, `${pageUrl} (fallback)`);
  }

  const raw = parseResponse(responseContent, pageUrl);
  return filterQuality(raw);
}

function parseResponse(raw: string, pageUrl: string): FaqPair[] {
  try {
    // Strip any markdown fences the LLM may have added despite instructions
    const cleaned = raw.replace(/```(?:json)?\n?/g, '').trim();
    const parsed = JSON.parse(cleaned) as { pairs?: unknown[] };

    if (!Array.isArray(parsed.pairs)) {
      console.warn(`[extraction] Unexpected response shape for ${pageUrl}`);
      return [];
    }

    return parsed.pairs
      .filter(
        (p): p is { question: string; answer: string; category?: string } =>
          typeof (p as any).question === 'string' && typeof (p as any).answer === 'string'
      )
      .map((p) => ({
        question: p.question.trim(),
        answer: p.answer.trim(),
        ...(p.category ? { category: p.category.trim() } : {}),
      }));
  } catch (err) {
    console.error(`[extraction] Failed to parse LLM response for ${pageUrl}:`, err);
    console.error('[extraction] Raw response (first 500 chars):', raw.slice(0, 500));
    return [];
  }
}

// ---------------------------------------------------------------------------
// Post-extraction quality filter
// Removes pairs where the LLM duplicated the question as the answer,
// left the answer empty, or admitted it couldn't find an answer.
// ---------------------------------------------------------------------------
function filterQuality(pairs: FaqPair[]): FaqPair[] {
  const before = pairs.length;
  const filtered = pairs.filter((p) => {
    if (!p.answer) return false;
    if (p.question.trim().toLowerCase() === p.answer.trim().toLowerCase()) return false;
    if (JUNK_ANSWER_PATTERNS.some((re) => re.test(p.answer))) return false;
    return true;
  });

  const removed = before - filtered.length;
  if (removed > 0) {
    console.warn(`[extraction] Filtered out ${removed} low-quality pair(s)`);
  }
  return filtered;
}
