import time

def rate_limit(delay_seconds: float = 2.0):
    """Enforce a minimum delay between API calls.
    Uses a simple sleep; callers should ensure this is called after each request.
    """
    if delay_seconds > 0:
        time.sleep(delay_seconds)
