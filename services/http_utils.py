import time
import requests

def get_with_backoff(url, headers=None, timeout=15, max_retries=3, backoff_factor=1.5):
    """Simple GET with exponential backoff on 429 and network errors."""
    attempt = 0
    wait = 1.0
    while True:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                if attempt >= max_retries:
                    return resp
                time.sleep(wait)
                wait *= backoff_factor
                attempt += 1
                continue
            return resp
        except requests.RequestException as e:
            if attempt >= max_retries:
                raise
            time.sleep(wait)
            wait *= backoff_factor
            attempt += 1
