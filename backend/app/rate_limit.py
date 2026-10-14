"""Per-IP rate limiting (slowapi). Limits themselves come from config.

Counts are kept in memory, which is fine for a single server process. With several
instances you'd point slowapi at Redis so they share counts.

Behind Render's proxy, the client IP arrives in X-Forwarded-For. uvicorn is started
with --proxy-headers so that request.client.host is the real client, not the proxy.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
