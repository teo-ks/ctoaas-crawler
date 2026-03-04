async function pageFunction(context) {
    const { request, log } = context;
    const url = request.url;

    log.info(`--- Processing: ${url} ---`);
    log.info(`Page Title: ${document.title}`); // Helps identify Cloudflare blocks

    // 1. EXTRACTION: If we are on a question page
    if (url.includes('/questions/')) {
        await new Promise(resolve => setTimeout(resolve, 2000));

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

        if (question && answer) {
            log.info(`✅ Extracted Q&A: ${question.substring(0, 30)}...`);
            return {
                question: question,
                answer: answer.trim(),
                url: url
            };
        }
    }

    // 2. PAGINATION: Click "View more" button repeatedly to load all questions
    let clickCount = 0;
    let viewMoreVisible = true;

    while (viewMoreVisible) {
        // Find all buttons and filter for the one containing the text "View more"
        const buttons = Array.from(document.querySelectorAll('button'));
        const viewMoreBtn = buttons.find(b => b.innerText && b.innerText.includes('View more'));

        // If the button exists and is not hidden
        if (viewMoreBtn && viewMoreBtn.offsetParent !== null) {
            clickCount++;
            log.info(`🖱️ Clicking "View more" (Click #${clickCount})...`);
            viewMoreBtn.click();

            // Wait 2 seconds for the new list items to render before checking again
            await new Promise(resolve => setTimeout(resolve, 2000));
        } else {
            // Button is gone, meaning we've loaded everything
            viewMoreVisible = false;
            log.info(`✅ Finished pagination. Clicked "View more" ${clickCount} times.`);
        }

        // Failsafe to prevent an infinite loop in case the button gets stuck loading
        if (clickCount >= 50) {
            log.warning('⚠️ Reached 50 clicks limit. Stopping pagination to prevent infinite loop.');
            break;
        }
    }

    // 3. CRAWLING: Poll for links with a wider net
    let allLinks = [];

    for (let i = 0; i < 15; i++) {
        // Grab EVERY link on the fully expanded page
        const links = document.querySelectorAll('a[href]');

        // Filter via JavaScript to catch any variation of AskGov routing
        const validLinks = Array.from(links).filter(a => {
            const h = (a.getAttribute('href') || '').toLowerCase();
            return h.includes('/ecda') || h.includes('/questions') || h.includes('topic=');
        });

        if (validLinks.length > 0) {
            allLinks = validLinks;
            log.info(`Waited ${i} seconds. Found ${allLinks.length} valid links out of ${links.length} total links on the page!`);
            break;
        }

        await new Promise(resolve => setTimeout(resolve, 1000));
    }

    // DIAGNOSTIC LOG: If we still found 0 links, dump the visible text to the log
    if (allLinks.length === 0) {
        log.warning(`🚨 0 links found! The crawler might be blocked or stuck loading.`);
        log.warning(`Visible page text: ${document.body.innerText.substring(0, 250).replace(/\n/g, ' ')}`);
    }

    // 4. ENQUEUE PROPERLY
    let enqueuedCount = 0;
    for (const link of allLinks) {
        const href = link.getAttribute('href');
        if (href) {
            try {
                const fullUrl = new URL(href, url).href;
                await context.enqueueRequest({ url: fullUrl });
                enqueuedCount++;
            } catch (e) {
                // Ignore malformed URLs
            }
        }
    }

    log.info(`🔍 Queued ${enqueuedCount} links to explore.`);

    return null;
}