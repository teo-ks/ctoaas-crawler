import { z } from 'zod';

export const FaqPairSchema = z.object({
  question: z.string().min(1),
  answer: z.string().min(1),
  category: z.string().optional(),
  url: z.string().optional(),
});

export type FaqPair = z.infer<typeof FaqPairSchema>;

export const FaqOutputSchema = z.object({
  domain: z.string(),
  startUrl: z.string(),
  scrapedAt: z.string(),
  totalPairs: z.number(),
  pairs: z.array(FaqPairSchema),
});

export type FaqOutput = z.infer<typeof FaqOutputSchema>;
