import 'dotenv/config';
import { createLLMClient, CostTracker, DEFAULT_MODEL, FALLBACK_MODEL } from './llm/client.js';
import { runFaqCrawler } from './crawler/faqCrawler.js';

// Usage: npx tsx src/index.ts [url]
const startUrl = process.argv[2] || 'https://ask.gov.sg/ecda';

console.log('');
console.log('🕷️  Agentic FAQ Scraper');
console.log('─'.repeat(55));
console.log(`📍 Target:    ${startUrl}`);
console.log(`🤖 LLM mode:  ${process.env.LLM_BASE_URL ? `OpenAI-compatible → ${process.env.LLM_BASE_URL}` : 'Anthropic (direct)'}`);
console.log(`📦 Model:     ${DEFAULT_MODEL}`);
console.log(`📦 Fallback:  ${FALLBACK_MODEL}`);
console.log('─'.repeat(55));
console.log('');

const llmClient = createLLMClient();
const costTracker = new CostTracker();

const pairs = await runFaqCrawler({
  startUrl,
  llmClient,
  costTracker,
  apifyProxyPassword: process.env.APIFY_PROXY_PASSWORD,
});

costTracker.summary();

console.log(`\n✅ Done — extracted ${pairs.length} FAQ pairs`);
