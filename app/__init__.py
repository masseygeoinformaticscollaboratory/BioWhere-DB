from __future__ import annotations
import logging
from logging.config import dictConfig
from flask import Flask
from .config import Settings
from .db import init_pool, close_pool

def create_app(config: Settings | None = None) -> Flask:
    cfg = config or Settings.from_env()

    dictConfig({
        "version": 1,
        "formatters": {"std": {"format": "[%(levelname)s] %(asctime)s %(name)s - %(message)s"}},
        "handlers": {"wsgi": {"class": "logging.StreamHandler", "formatter": "std"}},
        "root": {"level": "INFO" if not cfg.DEBUG else "DEBUG", "handlers": ["wsgi"]},
    })
    log = logging.getLogger(__name__)

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        DEBUG=cfg.DEBUG,
        JSON_SORT_KEYS=False,
    )

    # Init DB pool
    init_pool(cfg)
    log.info("DB pool ready")

    # Register blueprints
    from .blueprints.main import bp as main_bp
    from .blueprints.api import bp as api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    try:
        @app.after_serving
        def _close_pool():
            close_pool()
    except Exception:
        # If you're on an older Flask that doesn't have after_serving,
        # just skip auto-close (or use atexit).
        import atexit
        atexit.register(close_pool)

    return app
