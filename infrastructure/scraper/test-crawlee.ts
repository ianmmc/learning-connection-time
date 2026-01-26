/**
 * Standalone Crawlee test - map a district website
 *
 * Run with: npx ts-node test-crawlee.ts
 */

import { PlaywrightCrawler, Dataset } from 'crawlee';

const TARGET_URL = 'https://www.pasco.k12.fl.us';
const MAX_REQUESTS = 50;  // Limit for testing

interface PageData {
  url: string;
  title: string;
  depth: number;
  linksFound: number;
  hasBellScheduleKeywords: boolean;
  hasSchoolKeywords: boolean;
}

async function main() {
  const results: PageData[] = [];

  const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: MAX_REQUESTS,
    maxConcurrency: 3,

    async requestHandler({ request, page, enqueueLinks, log }) {
      const title = await page.title();
      const content = await page.content();
      const contentLower = content.toLowerCase();

      // Check for bell schedule keywords
      const bellKeywords = ['bell schedule', 'bell times', 'school hours', 'start time', 'end time', 'dismissal'];
      const hasBellScheduleKeywords = bellKeywords.some(kw => contentLower.includes(kw));

      // Check for school-related keywords
      const schoolKeywords = ['elementary school', 'middle school', 'high school', 'academy'];
      const hasSchoolKeywords = schoolKeywords.some(kw => contentLower.includes(kw));

      // Count links on page
      const links = await page.$$('a[href]');

      const pageData: PageData = {
        url: request.url,
        title: title.substring(0, 100),
        depth: request.userData.depth || 0,
        linksFound: links.length,
        hasBellScheduleKeywords,
        hasSchoolKeywords,
      };

      results.push(pageData);

      log.info(`Crawled: ${request.url} (depth: ${pageData.depth}, links: ${pageData.linksFound}, bell: ${hasBellScheduleKeywords})`);

      // Enqueue links from same domain
      await enqueueLinks({
        strategy: 'same-domain',
        transformRequestFunction: (req) => {
          req.userData.depth = (request.userData.depth || 0) + 1;
          return req;
        },
      });
    },

    failedRequestHandler({ request, log }) {
      log.error(`Failed: ${request.url}`);
    },
  });

  console.log(`\nStarting Crawlee crawl of ${TARGET_URL}`);
  console.log(`Max requests: ${MAX_REQUESTS}\n`);

  await crawler.run([TARGET_URL]);

  // Summary
  console.log('\n' + '='.repeat(80));
  console.log('CRAWLEE RESULTS SUMMARY');
  console.log('='.repeat(80));
  console.log(`Total pages crawled: ${results.length}`);

  const bellPages = results.filter(r => r.hasBellScheduleKeywords);
  const schoolPages = results.filter(r => r.hasSchoolKeywords);

  console.log(`\nPages with bell schedule keywords: ${bellPages.length}`);
  bellPages.forEach(p => console.log(`  - ${p.url}`));

  console.log(`\nPages with school keywords: ${schoolPages.length}`);
  schoolPages.slice(0, 10).forEach(p => console.log(`  - ${p.url}`));
  if (schoolPages.length > 10) console.log(`  ... and ${schoolPages.length - 10} more`);

  console.log('\nAll URLs crawled:');
  results.forEach(r => console.log(`  [depth=${r.depth}] ${r.url}`));
}

main().catch(console.error);
