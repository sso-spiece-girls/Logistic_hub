import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
threads = 4
worker_class = "gthread"
timeout = 120
keepalive = 5
wsgi_app = "wsgi:app"
