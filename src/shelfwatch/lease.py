"""Server-side queue locks serialize runs using the same monitor, without a KV check-then-set race."""
class MonitorBusy(RuntimeError):
    pass


class MonitorLease:
    def __init__(self, client):
        self.client = client
        self.request_id = None

    async def acquire(self):
        added = await self.client.add_request({"url": "https://shelfwatch.invalid/monitor-lock", "uniqueKey": "monitor-lock-v1"})
        head = await self.client.list_and_lock_head(lock_secs=600, limit=1)
        items = head.get("items", [])
        if not items:
            raise MonitorBusy("This monitorName is already running. Retry after it finishes; a crashed lock expires within 10 minutes.")
        self.request_id = items[0]["id"]
        if self.request_id != added["requestId"]:
            await self.release()
            raise MonitorBusy("Unexpected monitor lock queue contents; use a new monitorName.")

    async def renew(self):
        if self.request_id is None:
            raise MonitorBusy("Monitor lease is not held.")
        await self.client.prolong_request_lock(self.request_id, lock_secs=600)

    async def release(self):
        if self.request_id is not None:
            request_id, self.request_id = self.request_id, None
            await self.client.delete_request_lock(request_id)
