from app import create_app, hardening
from config import Config

app = hardening.init_app(create_app())

if __name__ == "__main__":
    if Config.DEBUG:                                  # development only: interactive debugger and reloader
        app.run(host=Config.HOST, port=Config.PORT, debug=True)
    else:                                             # production: a real WSGI server, no debugger, bounded request size
        from waitress import serve
        serve(app, host=Config.HOST, port=Config.PORT, threads=8, ident="Schoolink", max_request_body_size=Config.MAX_CONTENT_LENGTH,
              channel_timeout=60, cleanup_interval=30,
              trusted_proxy="127.0.0.1", trusted_proxy_count=1, trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"},
              clear_untrusted_proxy_headers=True)
