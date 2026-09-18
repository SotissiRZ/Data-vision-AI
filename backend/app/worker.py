from __future__ import annotations

import time

from app.core.config import get_settings
from app.services.job_service import QUEUE_KEY, run_job
from app.services.metadata_store import init_metadata_store


def main():
    init_metadata_store()
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("Le paquet redis est requis pour lancer le worker") from exc
    r = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    print("DataVision worker ready", flush=True)
    while True:
        try:
            item = r.blpop(QUEUE_KEY, timeout=5)
            if not item:
                continue
            _, job_id = item
            print(f"Running job {job_id}", flush=True)
            run_job(job_id)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"Worker error: {exc}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
