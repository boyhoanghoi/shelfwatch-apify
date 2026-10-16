import copy
import json
import sys
import types
import unittest
from unittest.mock import patch

from shelfwatch.actor import run_actor
from shelfwatch.runner import run_pipeline
from shelfwatch.state import product_key
from shelfwatch.transport import Page
from test_core import FakeClient, HTML, URL, source


class Manager:
    def __init__(self, limit=10):
        self.limit = limit
        self.count = 0
    def get_pricing_info(self):
        return types.SimpleNamespace(is_pay_per_event=True, per_event_prices={"product-checked": 0.002})
    def compute_push_data_limit(self, count, *args, **kwargs):
        return min(count, max(0, self.limit - self.count))
    def get_charged_event_count(self, event): return self.count


class Store:
    id = "state-store"
    def __init__(self): self.data = {}
    async def get_value(self, key): return copy.deepcopy(self.data.get(key))
    async def set_value(self, key, value): self.data[key] = copy.deepcopy(value)


class Queue:
    id = "lock-queue"
    def __init__(self): self.locked = False
    async def add_request(self, value): return {"requestId": "singleton"}
    async def list_and_lock_head(self, **kwargs):
        if self.locked: return {"items": []}
        self.locked = True
        return {"items": [{"id": "singleton"}]}
    async def prolong_request_lock(self, *args, **kwargs):
        if not self.locked: raise RuntimeError("Lock lost")
    async def delete_request_lock(self, key): self.locked = False


class FakeActor:
    def __init__(self, limit=10):
        self.configuration = types.SimpleNamespace(is_at_home=True)
        self.manager, self.store, self.queue = Manager(limit), Store(), Queue()
        self.apify_client = types.SimpleNamespace(request_queue=lambda *args, **kwargs: self.queue)
        self.log = types.SimpleNamespace(error=lambda *args: None, warning=lambda *args: None)
        self.values, self.rows = {}, []
        self.exit_code = 0
        self.reject_push = False
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def get_input(self): return {"productUrls": [URL], "monitorName": "tests"}
    def get_charging_manager(self): return self.manager
    async def open_request_queue(self, **kwargs): return self.queue
    async def open_key_value_store(self, **kwargs): return self.store
    async def set_value(self, key, value, **kwargs): self.values[key] = copy.deepcopy(value)
    async def push_data(self, row, **kwargs):
        if self.reject_push: return types.SimpleNamespace(charged_count=0)
        self.rows.append(copy.deepcopy(row))
        self.manager.count += 1
        return types.SimpleNamespace(charged_count=1)


class ActorTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, actor, client=FakeClient):
        async def pipeline(config, load, save):
            return await run_pipeline(config, load, save, client_factory=client)
        with patch.dict(sys.modules, {"apify": types.SimpleNamespace(Actor=actor)}), patch("shelfwatch.actor.run_pipeline", pipeline):
            await run_actor()

    async def test_cloud_state_survives_runs_and_edits_are_paid_once_per_product(self):
        actor = FakeActor()
        await self.execute(actor)
        self.assertEqual(actor.values["SUMMARY"]["baselineWrites"], 1)
        self.assertEqual(actor.manager.count, 1)
        self.assertEqual(actor.values["ALERTS"][0]["type"], "FIRST_OBSERVATION")
        class Changed(FakeClient):
            async def fetch(self, url, **kwargs):
                self.requests += 1
                return Page(url, json.dumps(source(800, False)) if url.endswith('.js') else HTML, 200, 'application/json' if url.endswith('.js') else 'text/html')
        await self.execute(actor, Changed)
        self.assertEqual(actor.manager.count, 2)
        self.assertEqual({a["type"] for a in actor.values["ALERTS"]}, {"PRICE_DROP", "OUT_OF_STOCK"})
        self.assertEqual(actor.store.data[product_key(URL)]["variants"]["31"]["p"], 800)
        await self.execute(actor, Changed)
        self.assertEqual(actor.values["ALERTS"], [])
        self.assertEqual(actor.values["RESULTS"][0]["checkStatus"], "NO_ALERT")
        self.assertEqual(actor.manager.count, 3)
        self.assertFalse(actor.queue.locked)

    async def test_zero_budget_and_rejected_push_do_not_create_or_update_baselines(self):
        for actor in [FakeActor(limit=0), FakeActor()]:
            actor.reject_push = True
            await self.execute(actor)
            self.assertEqual(actor.store.data, {})
            self.assertEqual(actor.values["RESULTS"], [])
            self.assertEqual(actor.values["SUMMARY"]["chargedChecks"], 0)
            self.assertFalse(actor.queue.locked)

    async def test_busy_monitor_does_not_fetch_bill_or_release_another_runs_lock(self):
        actor = FakeActor()
        actor.queue.locked = True
        async def no_pipeline(*args): raise AssertionError("A busy monitor must not fetch products")
        with patch.dict(sys.modules, {"apify": types.SimpleNamespace(Actor=actor)}), patch("shelfwatch.actor.run_pipeline", no_pipeline):
            await run_actor()
        self.assertEqual(actor.exit_code, 1)
        self.assertEqual(actor.manager.count, 0)
        self.assertTrue(actor.queue.locked)
        self.assertEqual(actor.values["DIAGNOSTICS"][0]["status"], "MonitorBusy")

    async def test_failed_state_write_keeps_dataset_evidence_and_old_baseline(self):
        actor = FakeActor()
        await self.execute(actor)
        old = copy.deepcopy(actor.store.data)
        async def fail(*args): raise OSError("Storage write failed")
        actor.store.set_value = fail
        await self.execute(actor)
        self.assertEqual(actor.exit_code, 1)
        self.assertEqual(actor.store.data, old)
        self.assertEqual(actor.values["SUMMARY"]["baselineWrites"], 0)
        self.assertEqual(len(actor.values["RESULTS"]), 1)
        self.assertEqual(actor.manager.count, 2)
        self.assertFalse(actor.queue.locked)

    async def test_missing_pricing_does_not_access_targets(self):
        actor = FakeActor()
        actor.manager.get_pricing_info = lambda: types.SimpleNamespace(is_pay_per_event=False)
        await self.execute(actor)
        self.assertEqual(actor.exit_code, 1)
        self.assertEqual(actor.store.data, {})
        self.assertEqual(actor.manager.count, 0)
