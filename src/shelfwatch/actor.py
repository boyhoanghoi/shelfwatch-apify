import asyncio
from dataclasses import replace
import hashlib
import os
import time
import uuid

from .config import RunConfig
from .lease import MonitorLease
from .output import alerts_csv, alerts_ndjson, checks_csv, digest_markdown
from .runner import report_for, run_pipeline

BILLABLE_EVENT = "product-checked"


async def run_actor():
    from apify import Actor

    async with Actor:
        started = time.monotonic()
        try:
            config = RunConfig.from_dict(await Actor.get_input() or {})
        except ValueError as exc:
            await Actor.set_value("OUTPUT", {"error": str(exc), "results": []})
            Actor.exit_code, Actor.status_message = 1, "Invalid input; see OUTPUT."
            return
        if not Actor.configuration.is_at_home:
            raise RuntimeError("For local execution, use the shelfwatch CLI with --state-file. The Actor entrypoint uses cloud monitor locks.")
        manager = Actor.get_charging_manager()
        pricing = manager.get_pricing_info()
        if not pricing.is_pay_per_event or BILLABLE_EVENT not in pricing.per_event_prices:
            await Actor.set_value("OUTPUT", {"error": "Required product-checked pay-per-event configuration is missing.", "results": []})
            Actor.exit_code, Actor.status_message = 1, "Missing pricing configuration; no websites checked."
            return
        limit = manager.compute_push_data_limit(config.max_products, BILLABLE_EVENT, is_default_dataset=True)
        saved = []
        state_writes = 0
        lease = None
        failure = None
        state_store_id = None
        lock_queue_id = None
        if limit < 1:
            report = report_for([], [], config, 0, started, "spending_limit")
        else:
            original_config = config
            config = replace(config, max_products=min(config.max_products, limit))
            namespace = hashlib.sha256(os.environ.get("APIFY_ACTOR_ID", "shelfwatch").encode()).hexdigest()[:8]
            store_name = f"shelfwatch-{namespace}-{config.monitor_name}"
            try:
                queue = await Actor.open_request_queue(name=store_name + "-lock", force_cloud=True)
                lock_queue_id = queue.id
                client_key = uuid.uuid4().hex
                lease = MonitorLease(Actor.apify_client.request_queue(queue.id, client_key=client_key))
                await lease.acquire()
                store = await Actor.open_key_value_store(name=store_name, force_cloud=True)
                state_store_id = store.id

                async def load(key):
                    await lease.renew()
                    return await store.get_value(key)

                async def save(row, current):
                    nonlocal state_writes
                    await lease.renew()
                    if manager.compute_push_data_limit(1, BILLABLE_EVENT, is_default_dataset=True) < 1:
                        return False
                    result = await Actor.push_data(row, charged_event_name=BILLABLE_EVENT)
                    if not result.charged_count:
                        return False
                    saved.append(row)
                    # Paid dataset evidence exists before the baseline can advance.
                    await lease.renew()
                    await store.set_value(row["productKey"], current)
                    state_writes += 1
                    return True

                report = await run_pipeline(config, load, save)
                if config.max_products < original_config.max_products:
                    report["summary"]["affordableProductCap"] = config.max_products
            except Exception as exc:
                failure = type(exc).__name__
                # Keep already-saved checks accessible, even if a storage/lease operation failed.
                report = report_for(saved, [{"status": failure, "message": str(exc) if failure == "MonitorBusy" else "Monitor storage/lock operation failed; prior unsaved baselines were not advanced."}], config, None, started, "monitor_error")
                Actor.log.error(f"Monitor stopped: {failure}")
            finally:
                if lease is not None:
                    try:
                        await lease.release()
                    except Exception:
                        Actor.log.warning("Monitor unlock failed; its server-side lease will expire within 10 minutes.")
        report["summary"].update({"billingEvent": BILLABLE_EVENT,
                                  "chargedChecks": manager.get_charged_event_count(BILLABLE_EVENT),
                                  "baselineWrites": state_writes, "stateStoreId": state_store_id,
                                  "lockQueueId": lock_queue_id,
                                  "persistentState": True})
        await Actor.set_value("RESULTS", report["results"])
        await Actor.set_value("ALERTS", report["alerts"])
        await Actor.set_value("SUMMARY", report["summary"])
        await Actor.set_value("DIAGNOSTICS", report["diagnostics"])
        await Actor.set_value("checks.csv", checks_csv(report["results"]), content_type="text/csv; charset=utf-8")
        await Actor.set_value("alerts.csv", alerts_csv(report["alerts"]), content_type="text/csv; charset=utf-8")
        await Actor.set_value("alerts.ndjson", alerts_ndjson(report["alerts"]), content_type="application/x-ndjson; charset=utf-8")
        await Actor.set_value("digest.md", digest_markdown(report), content_type="text/markdown; charset=utf-8")
        await Actor.set_value("OUTPUT", report)
        if failure or (report["summary"]["failedProducts"] and not saved):
            Actor.exit_code = 1
        Actor.status_message = f"Saved {len(report['results'])} product checks; {len(report['alerts'])} change observations; {report['summary']['failedProducts']} failures."


def main():
    asyncio.run(run_actor())


if __name__ == "__main__":
    main()
