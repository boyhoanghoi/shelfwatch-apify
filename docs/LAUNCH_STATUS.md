# ShelfWatch launch verification

Verified **16 October 2026 — Asia/Saigon**.

- [Public Actor](https://apify.com/reliable_quatrain/shopify-price-restock-monitor-shelfwatch).
- [GitHub repository](https://github.com/boyhoanghoi/shelfwatch-apify).
- Actor ID: `W1pbtOwadL0b3CykQ`; limited permissions.
- Public build: **0.1.4**, `9J2vyKidm2CQI5dv1`, SUCCEEDED.
- Package version: **0.1.0**; source commit `0dee2d2978cb6562ec24ee7fd8c4aad6c02cbb47`.
- **32 Python tests passed**, including strict normalization, currency/stock
  comparisons, repeated restock cycles versus stable retry IDs, scoped monitor
  IDs, baseline preservation after rejected saves, overlapping runs, failed state
  writes, spreadsheet safety, local checkpoint reuse and export-failure recovery.
- Official Apify CLI validated input, dataset and output schemas.
- Single pay-per-event price: **$0.002 per saved successful product check**,
  including first observations and checks with no alerts. No start/variant/alert
  event is configured. Existing four Actors were not modified or repriced.

## Final cloud checks

Both runs used ColourPop's Eeveelution palette and Death Wish's instant coffee
product URLs, monitor `release-demo-20261016-v3`, a two-product cap and a **$0.01
maximum Actor charge** per run. These public example merchants are not customers
or endorsements. They were independently checked by the Actor from Apify cloud.

| Check | Run ID | Observed result |
| --- | --- | --- |
| First saved baseline | `byGNh6QGmfJdCFo7B` | 2 checks, 2 FIRST_OBSERVATION events, 2 check charges, 2 baseline writes |
| Same-monitor repeat | `zim5ew5kvejcptn9z` | 2 checks, 0 alerts, 2 check charges, 2 baseline writes |

Both used build 0.1.4. Both had zero failed products and observed USD currency
from the product HTML. Their private state store ID was identical:
`eDdPFxRD7tXLAphfD`. Repeat rows contain prior observation timestamps; the named
records match each saved row's product ID and current observation time.

Dataset, SUMMARY and final chargedEventCounts agreed after allowing for eventual
charge-count updates. Checks CSV/alerts CSV row counts, NDJSON event contents,
Markdown digest counts, row/event monitor identity and baseline records were
verified. First observations are not real price drops/restocks or launch dates.

Measured infrastructure usage for these two final owner runs was approximately
**$0.001013** and **$0.001005**; the final build used approximately **$0.003459**.
These samples exclude earlier development builds/probes, are not customer revenue
and do not forecast the cost of larger or failing watchlists.

## Lock and failure checks

An intentional cloud lock-conflict check on build **0.1.2** used run
`WnSan80hZjWtXaArI`. A temporary server-side lock was acquired before invoking
the Actor. The Actor returned FAILED/MonitorBusy with **0 saved checks, 0 check
charges and 0 baseline writes**, without releasing the other client's lock. The
temporary verifier lock was then explicitly released. Actor/lease locking code
did not change between that check and public build 0.1.4.

An initial build-0.1.1 probe `o1ADvMMwn7KYoNS1B` could not read Allbirds robots.txt
from cloud, although the local probe worked. The Actor skipped it conservatively
and charged only the other successfully saved product. The cause was not proven;
no access bypass was added. A source probe `pJoJFqJQRANcO6tvb` verified the replacement
ColourPop/Death Wish examples before updating prefilled input.

Controlled tests cover price/restock edits and repeated cycles. No real merchant
price change or restock is asserted from the two final cloud samples. Source
availability, public JSON format and markup currency evidence can change.

## Public presentation and next steps

Anonymous Actor API confirmed public visibility, latest build and the sole
product-checked event price. Store returned HTTP 200 with the preview, monitor
instructions and unchanged-check pricing disclosure. The raw preview PNG also
returned HTTP 200. Full machine-readable evidence is in [launch.json](launch.json).

- [Vietnamese first run](FIRST_RUN_VI.md).
- [Integration and retry semantics](INTEGRATION.md).
- [Customer validation plan](ACQUISITION_PLAN_VI.md) and [unsent launch drafts](LAUNCH_POSTS.md).
- Preview: `assets/launch/shelfwatch-preview.png`, visible in Store README.
- Separate top-level icon is **not uploaded** (`pictureUrl: null`). The ready file
  is `assets/brand/icon-512.png`, with SVG source beside it; it can be set under
  [Publishing → Display information](https://console.apify.com/actors/W1pbtOwadL0b3CykQ/publication).

No recurring owner task or schedule was created. No email, DM or community post
was sent. No paid customer, customer revenue or payout has been verified. The
product is published; acquisition and repeat customer use remain to be validated.
