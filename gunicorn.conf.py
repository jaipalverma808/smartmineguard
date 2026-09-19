import os

# Server socket binding
bind = f"0.0.0.0:{os.getenv('PORT', 5000)}"

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
