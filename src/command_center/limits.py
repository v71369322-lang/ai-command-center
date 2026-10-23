"""Bounded in-process HTTP admission, additional to durable PostgreSQL policy."""
from collections import OrderedDict
from threading import Lock
import time


class RateLimit:
    def __init__(self, capacity=60, period=60, clients=1024):
        self.capacity, self.period, self.clients = capacity, period, clients
        self.entries = OrderedDict()
        self.lock = Lock()

    def admit(self, identity, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            start, count = self.entries.pop(identity, (now, 0))
            if now - start >= self.period:
                start, count = now, 0
            allowed = count < self.capacity
            self.entries[identity] = (start, min(count + 1, self.capacity))
            if len(self.entries) > self.clients:
                self.entries.popitem(last=False)
            return allowed
