# Penny Watch NWLA — $0 GitHub Free Edition (NO Cloudflare)

**What's included:** a fully runnable, static, mobile-friendly website; a Python standard-library ingestion and price-analysis engine; SQLite historical database; compressed downloadable CSV snapshots for **each recorded scan**; broad authorized catalog discovery; deep-markdown and exact-SKU penny-lead rankings; sourced regional report imports; exact-variant retailer comparisons; a printable Bossier-first Monday list; optional Telegram notifications; and GitHub Actions schedules for **5:00 AM and 1:00 PM America/Chicago**, plus Monday preparation at **5:45 AM**.

**What is NOT included:** a guaranteed all-Home-Depot-item scanning API. No authorized unrestricted, store-specific Home Depot product/price feed has been supplied. Without one, the site starts with no verified observations; schedules record missing coverage, not false success. **It is not deployed yet.** It does not access Facebook private groups or circumvent Home Depot restrictions.

## The cost and visibility tradeoff

- **GitHub Free**: $0 (public repository + GitHub Pages + standard hosted GitHub Actions); no Cloudflare, Replit, or TinyFish. GitHub Actions currently supports timezone-aware schedules; scheduled starts can be delayed or omitted during high load.
- **GitHub Pages on GitHub Free must be public.** Its displayed inventory/prices, ZIP exports, and repository history are visible to anyone. Do not upload personal information, private Facebook messages, purchase receipts, passwords, client data, internal notes, or credentials. All price data is assumed public-source-only. Secrets remain private in GitHub Actions repository secrets.
- GitHub Pages recommends **~1 GB max published site size**. The package preflights at 800 MB and stops rather than deleting archives. GitHub's repository history also grows with each commit. A lifetime unlimited archive of enormous full-catalog twice-daily scans cannot be guaranteed indefinitely for $0. An optional local-only setup uses your own computer and storage.
- GitHub Free has a **2,000 hosted-runner minutes/month allowance for private repositories**; regular standard runners for public repositories are free within policy. The collector uses only Python's built-in modules. Source provider costs, if any, are not included.

Official references:
- https://docs.github.com/en/pages/getting-started-with-github-pages/quickstart
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
- https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- https://www.homedepot.com/c/Terms_of_Use

## Publish with a free GitHub account (no coding subscription)

1. Sign up/sign in at https://github.com/ . Create a **PUBLIC** repository called `penny-watch-nwla` with default branch `main`. A free personal account is sufficient.
2. Unzip and upload **the contents** of this folder (including the hidden `.github` directory) to the root of that repository. Don't upload just the ZIP as a single file.
3. Under the repository's **Settings → Pages → Build and deployment**, choose **GitHub Actions** as the source. The site is published to a `github.io` URL automatically after a workflow succeeds. Do not assume a URL until GitHub displays it.
4. Under **Actions**, choose **Penny Watch — collect and publish**, then **Run workflow** to produce your first run, dashboard, and archive. With no feeds configured it correctly shows `source_unconfigured`, `0` saved prices.
5. In **Settings → Secrets and variables → Actions**, add only the feeds you have permission to collect. Required names are below. Never put credentials in repository files, public JavaScript, site pages, CSVs, or chat.
6. After a sourced feed is connected, **Run workflow** again to ingest real records. Confirm each of the 3 stores has a nonzero stored count and a downloadable scan ZIP. Treat missing stores as partial coverage.
7. Optionally set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repository secrets after creating a free Telegram bot, starting a conversation with it, and obtaining the chat ID. The workflow sends scan reports and the Monday checklist when configured. If not configured, the notification status is `not_configured`.
8. Before using both this and the **existing ChatGPT Penny Watch automations** on the same data, retire the duplicates or keep them explicitly separate. The existing ChatGPT-hosted Site will NOT be automatically migrated or connected by publishing this repository.

### Feed secret names

For Bossier City #0364, Bert Kouns #0356 and Pines Road #0381:

- **Broad discovery:** `CATALOG_FEED_0364`, `CATALOG_FEED_0356`, `CATALOG_FEED_0381`
- **5 AM + 1 PM price scans:** `PRICE_FEED_0364`, `PRICE_FEED_0356`, `PRICE_FEED_0381`
- **250-priority-SKU recheck:** `PRIORITY_FEED_0364`, `PRIORITY_FEED_0356`, `PRIORITY_FEED_0381`
- **PennyCentral/Spotted/accessible reports:** `REPORTS_FEED_URL`
- **Identical-variant retailer offers:** `RETAIL_FEED_URL`
- **Optional shared bearer token for authorized sources:** `AUTH_FEED_BEARER`

Feeds must be **owner-authorized HTTPS JSON/CSV feeds**. Catalog feeds return `items` with exact `sku`, `name`, optional `upc`, brand, category and product ID. Price feeds return `items` with exact `store_id`, `sku`, `price`, `price_type`, `source`, `source_url`, and timezone-aware `observed_at` and may specify an `expected_count`. Priority feeds accept HTTPS POST `{"store_id":"0364","skus":["..."]}` and must return the same price fields. All 3 store coverage requires all stores to have expected counts and observed rows. Source collection is **not activated by merely having this code**.

An example public-facing feed response (illustrative only):

```json
{"expected_count": 1, "items": [{"store_id":"0364", "sku":"1234567890", "name":"ILLUSTRATIVE ONLY", "price":12.97, "regular_price":30.00, "price_type":"online", "source":"Authorized feed", "source_url":"https://example.com/not-real", "observed_at":"2026-11-14T11:00:00Z"}]}
```

**Do not assume a public catalog URL is an authorized feed.** Home Depot's terms and technical defenses restrict automated acquisition in certain circumstances. The app does not defeat login walls, CAPTCHA, rate limits, blocked robots, or private-group access. It does not buy anything or contact stores.

## Import public/authorized CSV records without a feed

For occasional imports, upload CSVs inside the repository's `imports` folder using filenames beginning `catalog-`, `prices-`, `reports-` or `comparisons-`, then use **Actions → Run workflow**. Columns are in `samples/`. Imported files are de-duplicated by checksum. **Do not copy the illustrative sample files into `imports`**; they contain intentionally fake test data. Once committed to a public repository, files and history remain public; only use publicly shareable sourced records.

- `catalog-*`: expands your SKU universe without asserting a price.
- `prices-*`: exact observed store prices with a source URL, price type and timestamp.
- `reports-*`: public, properly sourced community penny reports; exact SKU matching only. A nationwide penny report does NOT prove a local register price.
- `comparisons-*`: competitor pricing for the exact same variant, including shipping costs.

## Storage, history and integrity

- The canonical SQLite database lives in `data/penny_watch.sqlite` and is committed after successful workflows, along with generated site data and ZIP archives.
- Each scan produces `docs/exports/<run-id>.zip` containing one Excel/Sheets-compatible CSV. The site shows a direct ZIP download for each run; **even empty runs have an explicit archived zero-row CSV** rather than pretending full inventory was scanned.
- Scan rows are append-only in `ticks`. The `current` table stores the most recent price separately; the website exposes price-history charts via SKU-hashed shards.
- The dashboard explicitly shows expected vs observed store coverage. A successful tracked-source run is called `complete_tracked_scope`; it **never** means every Home Depot product was captured. First observations without a valid baseline do not receive a fabricated discount percentage.
- GitHub Pages is read-only. In-store verification notes entered on the webpage are stored in **the current browser's localStorage only**; they are not synchronized. Export findings separately if you need them across devices.
- All sources, regional reports, and cross-retailer listings preserve source links and observations; reporting confidence and visit priority are separate from local checkout confirmation.
- The 800 MB safety check runs AFTER committing archives to the repository: it stops Pages publication before the cap, but does not silently erase newly collected records. For large inventories, move archives to a self-managed local backup and use the local mode below; the free public repository is not infinite storage.

## Local-only private mode (no GitHub required)

Install Python 3.10+ on a computer that remains on during collections. From the project directory:

```sh
python src/pennywatch.py init
python src/pennywatch.py build
python src/pennywatch.py serve
```

Open `http://127.0.0.1:8000/` in that computer's browser. Schedule `python src/pennywatch.py collect --slot manual` with Windows Task Scheduler (daily 5:00 AM and 1:00 PM) or cron on a Mac/Linux machine, and schedule `python src/pennywatch.py monday` Monday 5:45 AM. Set authorized source environment variables locally. The database, exports and in-store notes stay on that machine; local mode has no free cloud website for access from other devices. Data collection still requires configured authorized sources. If the computer sleeps or is off, scans do not run.

## Automated tests

`python -m unittest discover -s tests -v` checks three-store validity, exact-SKU matching, duplicate protection, the discount baseline, source/report provenance, snapshot ZIP integrity, no-fake-completeness on missing stores, history shard reconstruction, and Central Time schedule. `python src/pennywatch.py build` produces the static `docs` site. The site has no runtime backend, login, or paid dependencies.

## Limitations to read before using

1. GitHub Actions scheduled starts are best effort, not guaranteed precise or always delivered at 5:00/13:00; read the workflow logs for execution timestamps.
2. GitHub Pages Free sites are public. Never upload proprietary or personal information.
3. There is no unlimited catalog API or full stock/checkout database. A complete online price inventory is not established.
4. Large repository histories and many scan ZIPs will eventually exceed free practical storage limits. Publishing stops with explicit warning rather than silently dropping history.
5. Community reports (PennyCentral, Spotted, public Facebook posts) are clues, not confirmed store-specific penny transactions.
6. Retail comparison requires exact variant and shipping, not just matching titles or model families.
7. The old ChatGPT Site's failed zero-row ingestion is not repaired by creating this new separate codebase.