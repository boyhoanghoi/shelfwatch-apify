# Scheduled watchlist → your alert workflow

## Remember history automatically

Create an Apify task from a successful run, keeping `monitorName` unchanged.
Add a daily schedule for that task. The Actor's named private storage persists
across runs in the running user's account; no previousSnapshot field is needed.
Do not schedule overlapping runs of the same monitor. A busy run exits with
`MonitorBusy` and no product-check event. A crashed lease expires within 10 minutes.

Use a separate monitor name per client/list. State is keyed by normalized original
URL, not SKU. Changing a URL/locale creates a distinct history. Products removed
from the watchlist keep their stored baseline; re-adding them resumes history.

## Deliver only useful observations

An Apify run-success webhook can trigger your n8n/Make/backend workflow:

1. Read the run ID from the webhook event and obtain its default KV store ID using
   the Apify run API.
2. GET the KV record `ALERTS` using an Apify credential owned by you. For example:

   ```text
   GET https://api.apify.com/v2/key-value-stores/STORE_ID/records/ALERTS
   Authorization: Bearer YOUR_APIFY_TOKEN
   ```

3. Filter the array by `type`, e.g. `PRICE_DROP` and `BACK_IN_STOCK`; exclude
   `FIRST_OBSERVATION` if you do not want baseline notifications.
4. Deduplicate by `eventId` in your own datastore before forwarding a message.
5. Send to a destination **you configure and authorize**. An empty array should
   produce no notification. To handle partial/failed runs, inspect DIAGNOSTICS and
   recover embedded `changes` from dataset rows already saved.

The Actor itself has no email, Slack, Telegram or arbitrary webhook destination
input. No credentials are requested for other services and no messages are sent
by this repository. JSON and NDJSON preserve exact event/source identifiers; CSV
neutralizes spreadsheet formula prefixes.

## Stable IDs, retries and failures

`eventId` hashes monitor/product identity, before/after state, the prior saved
observation time, change type and variant ID. Replaying against the same baseline
yields the same ID despite a new current observation timestamp. A later identical
restock/price cycle has a different prior saved time and remains a distinct event.
Baseline promotions happen after paid dataset writes. There is no
transaction spanning the dataset and named KV store. A paid save followed by a KV
failure fails the run and may repeat on retry; do not treat it as exactly-once.

The main dataset contains every saved check, including NO_ALERT. `ALERTS` contains
only the saved checks' emitted observations, which can be empty or multiple per
product. Filters alter alerts, not the check fee. Use `SUMMARY.chargedChecks` and
run charge metadata to reconcile billable units. `baselineWrites` can be smaller
than saved checks during a storage failure and is a reason to inspect diagnostics.

## Source and comparison scope

Every current variant has raw price, reference/compare-at price and availability.
Unknown currency blocks price comparisons. The source's 250-variant ceiling means
missing variants cannot safely become removal notifications. Price moves below
your threshold still promote the last saved state; thresholds are not cumulative.
No output proves sales, exact inventory, pricing violations or a checkout outcome.
