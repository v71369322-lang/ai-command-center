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


class CircuitBreaker:
    """Single-worker dependency circuit with one bounded half-open probe."""
    def __init__(self, threshold=5, cooldown=30):
        self.threshold, self.cooldown = threshold, cooldown
        self.failures = 0
        self.state = 'CLOSED'
        self.opens_until = 0

    def admit(self, now=None):
        now = time.monotonic() if now is None else now
        if self.state == 'HALF_OPEN':
            return False
        if self.state == 'OPEN':
            if now < self.opens_until:
                return False
            self.state = 'HALF_OPEN'
        return True

    def success(self):
        self.failures, self.state = 0, 'CLOSED'

    def failure(self, now=None):
        now = time.monotonic() if now is None else now
        self.failures = min(self.failures + 1, self.threshold)
        if self.state == 'HALF_OPEN' or self.failures == self.threshold:
            self.state, self.opens_until = 'OPEN', now + self.cooldown
