# Penny Watch NWLA — GitHub Free

A public, mobile-friendly, read-only dashboard for tracking sourced Home Depot clearance prices and community penny leads across three NW Louisiana stores. **No Cloudflare, Replit, TinyFish or paid hosting is required.**

**Important status:** This repo contains the website and a scheduled collection engine. It has no configured Home Depot price or catalog feeds. It cannot and does not claim to scan the complete online or physical Home Depot inventory. The database starts empty. All data published by GitHub Pages is **public**.

## Stores

- Bossier City, Airline Drive — 0364
- Shreveport, Bert Kouns — 0356
- West Shreveport, Pines Road — 0381

## First-time deployment

1. In GitHub, open **Settings → Pages → Build and deployment**, select **GitHub Actions** as the source. This one-time setting is required.
2. Open **Actions → Penny Watch - Scan and Publish**. Confirm a run completes successfully. Use **Run workflow** if needed.
3. GitHub will show the published URL under **Settings → Pages** after successful deployment. There is no verified site URL until that happens.
4. The site initially displays **zero verified prices**. This is intentional; no demo prices masquerade as live inventory.

## Free-source integrations (November 2026)

The **Free Source Reports** tab distinguishes community reports from actual local prices:

| Source | Integration | Notes |
|---|---|---|
| [Penny Recon](https://www.pennyrecon.com/) | Automated twice-daily published JSON import; also refreshed on deployment | Reports, regional signal, SKU, and source attribution. No store-specific price. Feed freshness and errors recorded. |
| [PennyCentral](https://www.pennycentral.com/penny-list) | Manual sourced export adapter | Its [terms](https://www.pennycentral.com/terms-of-service) explicitly prohibit scraping; no automated extractor. Only upload data you are permitted to use. |
| [PennyLoot](https://www.pennyloot.com/) | Manual sourced export adapter | No publicly authorized bulk feed verified. |
| [SpottedFlips](https://www.spottedflips.com/penny) | Manual sourced export adapter | Public penny sightings; no bulk feed authorization established. |
| [HDScanner](https://github.com/KenStager/HDScanner) | Free CSV/JSON export import | Run separately only where access is permitted. Correct store and exact store SKU are required. |
| [2scraper Home Depot](https://github.com/2scraper/homedepot-scraper) | Free CSV/JSON export import | Maps the distinct store_sku field, **not** its misleading internet product field named sku. Rejects unrelated stores. |
| [Omkar Home Depot](https://github.com/omkarcloud/homedepot-scraper) | Free CSV/JSON export import | Requires an exact store_sku and store_id; missing values are rejected, not guessed. |

To import an export through GitHub, use **Add file → Upload files** into the repository imports folder. Name files using one of these prefixes: 2scraper-, hdscanner-, omkar-, pennycentral-, pennyloot-, or spotted-, with a .csv or .json extension. Blank source-specific starter files: [store-export CSV](samples/free-store-export-template.csv) and [community-export CSV](samples/free-community-export-template.csv). Export files need a timestamp including timezone, exact store number, true store SKU, actual observed price, and a direct HTTPS evidence link. Do not use another store's price as your own. Community files need exact SKU, date and original report link.

The collector never tries to defeat anti-bot protections, paid access gates, or websites' restrictions. No scraping from private Facebook groups has been installed. Other free sources can be added when they publish a permitted structured feed.

**Data reliability:** Penny Recon's reported score is **not** an independent verification. Only store-specific records get store prices. A community SKU can be a useful lead without being available, marked down, or priced at a penny at any of the three local stores.

**Current automatic status:** Penny Recon feed is wired for automatic attempts at the scheduled collection runs. Whether GitHub's cloud runner can reach it must be verified in workflow history. HDScanner, 2scraper, Omkar, PennyCentral and PennyLoot are integrated through export-import, not automatically scraped or run on GitHub.

## Supported data sources

Configure repository Actions **secrets** with HTTPS URLs only for feeds you are permitted to access:

- `CATALOG_FEED_0364`, `CATALOG_FEED_0356`, `CATALOG_FEED_0381`: JSON or CSV lists of products with an exact SKU.
- `PRICE_FEED_0364`, `PRICE_FEED_0356`, `PRICE_FEED_0381`: JSON or CSV current prices for that exact store and SKU. Timestamp and original source link are required.
- `REPORTS_FEED_URL`: permitted public penny-report feed, with SKU, state, source URL and report date.
- `RETAIL_FEED_URL`: optional same-variant retailer comparisons.
- `AUTH_FEED_BEARER`: optional shared token used to authenticate permitted feeds.

There is no built-in unrestricted Home Depot scraper. Permission to view a webpage is not equivalent to permission to scrape it in bulk. Do not bypass access controls or collect private Facebook group posts.

For CSV imports, put valid sourced files under `imports/` prefixed by `catalog-`, `prices-`, `reports-` or `comparisons-`. Source-column templates are in `samples/`. Never upload fictitious sample rows to live imports.

A valid price observation needs `store_id`, `sku`, `price`, `price_type`, `source`, `source_url`, and ISO 8601 `observed_at` with timezone. For example, `price_type` can be `online`, `clearance`, `shelf`, `pos`, or `unknown`. The distinction matters: online or community prices do not verify an in-store point-of-sale penny transaction. Regular prices are optional; the dashboard will not fabricate missing discount baselines.

## Schedule and archive

The workflow contains timezone-aware schedules for **5:00 AM** and **1:00 PM** in America/Chicago, and a Monday checklist refresh at **5:45 AM**. GitHub Actions can start late or skip scheduled occurrences. The collector runs only when GitHub executes the workflow.

Collected observations are stored in an append-only SQLite price table and committed back into the public repository. Every recorded collection produces a ZIP with a spreadsheet-compatible CSV under `docs/exports/`. The dashboard provides historical and current CSV links. GitHub storage is not infinite; a full-product, twice-daily, multi-year archive may eventually require a different data-storage design.

The workflow distinguishes `source_unconfigured`, `no_prices`, `partial`, `partial_unknown_coverage` and `complete_tracked_scope`. Even `complete_tracked_scope` means only that the **provided tracked sources** were captured; it does not establish all Home Depot inventory was checked.

The Monday list is sorted Bossier City first. In-store verification notes are stored only on the device/browser where they are entered; they do **not** synchronize to GitHub. You can download checklist CSVs for offline use.

## Current limitations

- No verified price feeds are connected.
- No comprehensive Home Depot inventory source or local checkout-price API is established.
- Penny Recon is the only built-in automated community feed; PennyCentral, PennyLoot, Facebook and retailer comparisons require permitted sourced exports or feeds. Their existence does not guarantee automated collection.
- Telegram or other push/email alerts are **not connected or active** in this repository; scheduled reports appear in GitHub Actions logs and website history when runs complete.
- A priority-only SKU collector is not yet connected. The current engine fetches configured catalog/price sources, then ranks observed clearance candidates.
- The site and all exports are public on GitHub Free. Never add secrets, client records, receipts, private reports or personal information to the repository.
- This is separate from the pre-existing ChatGPT-hosted Penny Watch site and automations. Publishing it does not migrate or repair the other system.

## Verification

A smoke-test suite (`python -m unittest discover -s tests -v`) validates source-unconfigured handling, archive ZIP generation, and store/SKU validation. The GitHub workflow runs these tests and Python syntax checking before collecting or publishing.

For manual local use, run `python src/pennywatch.py init` and `python src/pennywatch.py build`, then serve the `docs/` directory with a local static web server. Without configured feeds, the system accurately reports no sourced prices.

## Documentation

- [GitHub Pages](https://docs.github.com/en/pages)
- [GitHub Actions scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [Home Depot Terms of Use](https://www.homedepot.com/c/Terms_of_Use)
