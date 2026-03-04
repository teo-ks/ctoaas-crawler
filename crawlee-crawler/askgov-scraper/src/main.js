import 'dotenv/config';
import { PlaywrightCrawler, log, ProxyConfiguration } from 'crawlee';

const proxyConfiguration = new ProxyConfiguration({
    proxyUrls: [
        `http://groups-RESIDENTIAL:${process.env.APIFY_PROXY_PASSWORD}@proxy.apify.com:8000`
    ]
});

const crawler = new PlaywrightCrawler({
    proxyConfiguration, // comment out to not use proxy
    async requestHandler({ page, request, log, enqueueLinks }) {
        const url = request.url;
        log.info(`--- Processing: ${url} ---`);
        log.info(`Page Title: ${await page.title()}`);

        // 1. EXTRACTION: If we are on a question page
        if (url.includes('/questions/')) {
            await page.waitForTimeout(2000); // Wait 2 seconds for rendering

            const extractedData = await page.evaluate(() => {
                const h1 = document.querySelector('h1');
                const question = h1 ? h1.innerText.trim() : document.title;

                let answer = '';
                const paragraphs = document.querySelectorAll('article p, main p, .prose p, article li, .prose li');

                paragraphs.forEach(p => {
                    const text = p.innerText.trim();
                    if (text) answer += text + '\n';
                });

                if (!answer) {
                    document.querySelectorAll('p').forEach(p => {
                        const text = p.innerText.trim();
                        if (text.length > 25) answer += text + '\n';
                    });
                }

                return { question, answer: answer.trim() };
            });

            if (extractedData.question && extractedData.answer) {
                log.info(`✅ Extracted Q&A: ${extractedData.question.substring(0, 30)}...`);

                // Save the data to a single JSON file instead of individual files
                await crawler.pushData({
                    url: url,
                    question: extractedData.question,
                    answer: extractedData.answer
                });
            }
            return; // Stop processing this page
        }

        // 2. PAGINATION: Click "View more" button repeatedly using Playwright locators
        let clickCount = 0;
        let viewMoreVisible = true;

        while (viewMoreVisible && clickCount < 5) {
            // Find the button containing the text "View more"
            const viewMoreBtn = page.locator('button', { hasText: 'View more' }).first();

            if (await viewMoreBtn.isVisible()) {
                clickCount++;
                log.info(`🖱️ Clicking "View more" (Click #${clickCount})...`);
                await viewMoreBtn.click();

                // Wait 2 seconds for the new list items to render
                await page.waitForTimeout(2000);
            } else {
                viewMoreVisible = false;
                log.info(`✅ Finished pagination. Clicked "View more" ${clickCount} times.`);
            }
        }

        // 3. ENQUEUE
        const enqueued = await enqueueLinks({
            selector: 'a[href]', // Look at all links
            transformRequestFunction(req) {
                // Filter logic to catch AskGov routing
                const h = req.url.toLowerCase();
                if (h.includes('/ecda') || h.includes('/questions') || h.includes('topic=')) {
                    return req;
                }
                return false;
            }
        });

        log.info(`🔍 Queued ${enqueued.processedRequests.length} links to explore.`);
    },

    // Optional: Failsafe settings
    maxRequestRetries: 3,
    maxRequestsPerCrawl: 100,
});

// Add the starting point and run the crawler
log.info('🚀 Starting crawler...');
await crawler.addRequests(['https://ask.gov.sg/ecda']);
await crawler.run();

// Export the default dataset to JSON file
log.info('💾 Exporting data to JSON file...');
await crawler.exportData('./storage/output.json', 'json');
log.info('✅ Done! Data saved to storage/output.json');