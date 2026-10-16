# Market check — 16 October 2026

Chosen customer: a small e-commerce team/agency with a list of competing Shopify
products to check repeatedly, or a deal publisher watching known product URLs.
The repeat trigger is a fresh price/availability observation, not a one-off lead list.

## Evidence and competition

- [Trove Vault Shopify Products Scraper](https://apify.com/trovevault/shopify-products-scraper):
  unauthenticated [Actor API](https://api.apify.com/v2/acts/trovevault~shopify-products-scraper)
  on this date reported 733 total users, 94 users in the preceding 30 days and
  1,027 runs in its public 30-day run statistics. These are usage figures, not
  paying customers, revenue or proof that ShelfWatch will sell.
- [GaziDev monitor](https://apify.com/gazidev/shopify-products-monitor) and
  [Luke Hunter product tracker](https://apify.com/lukehunter/shopify-product-tracker)
  already offer price/stock monitoring. This is a competitive category; neither
  monitoring nor persistent state is claimed as unique.
- ShelfWatch focuses on a small explicit watchlist, variant evidence, automatic
  per-user state, overlap protection and alert-ready output. Its value must be
  tested with real users; lower implementation cost does not establish demand.

## Source contracts and limitations

- [Shopify Ajax product reference](https://shopify.dev/docs/api/ajax/reference/product):
  public theme product JSON, presentment currency, maximum 250 variants.
- [Ajax API scope](https://shopify.dev/docs/api/ajax): themes hosted by Shopify;
  custom/headless storefronts are outside this compatibility claim.
- [Shopify monetary-unit example](https://shopify.dev/docs/api/liquid/objects/selling_plan_checkout_charge):
  money values are scaled, including appended hundredths for JPY/KRW. ShelfWatch
  retains raw Ajax integers and uses scale 100; no ISO currency-exponent guessing.
- The official currency lookup is cart.js, but many observed robots files disallow
  cart access. ShelfWatch does **not** fetch cart.js. It records product HTML's
  Shopify active-currency/structured-markup evidence instead. This is a separate
  observation, not proof of every shopper's market; unknown currency suppresses
  price comparisons.
- [Apify limited permissions](https://docs.apify.com/actors/development/permissions):
  an Actor can access storage it created in earlier runs in the same user's account.
- [Apify queue locks](https://docs.apify.com/api/client/python/reference/class/RequestQueueClientAsync):
  used for a server-side lease, not an unsafe read/write flag in KV storage.

Live source probes and cloud checks are recorded separately in LAUNCH_STATUS.md.
Respect robots and access failures; no fallback bypass is included. Empty/failed
observations do not establish removal, sales, demand or stock quantities.

## Validation after launch

Find one agency or merchant who already checks 10–50 competing product URLs.
Offer a small sample and ask whether it changes an action they take. Track:
first successful check, creation of a repeating task, repeat use after a week,
false/missing alerts, paying users and net developer profit in Apify Insights.
Set a 14-day review before expanding scope. If nobody returns, interview users
and change the workflow rather than assuming more Actors create income.
