import os

port = os.getenv("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Concurrency model: 1 worker with 8 threads
workers = 1
threads = 8
worker_class = "gthread"

# Timeouts: 120s timeout prevents SocketIO long-polling requests from triggering worker timeouts
timeout = 120
keepalive = 5
graceful_timeout = 30

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"


def post_worker_init(worker):
    """Start background services safely inside the worker process after fork."""
    try:
        from services.gps_simulator import simulator
        if simulator and not simulator.is_running:
            simulator.start()
            worker.log.info("GPS simulator started safely in worker process.")
    except Exception as e:
        worker.log.warning(f"Could not start simulator in worker: {e}")

