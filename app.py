"""Flask Web 应用入口。"""

import logging
import os
import sys

from flask import Flask, send_from_directory

from services.runtime_config import RuntimeConfigProvider
from services.task_manager import TaskManager
from services.pipeline_runner import run_pipeline
from web.routes.health import health_bp
from web.routes.config_api import config_bp, init_config_routes
from web.routes.tasks_api import tasks_bp, init_tasks_routes
from web.routes.zotero_api import zotero_bp, init_zotero_routes
from web.routes.services_api import services_bp, init_services_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    config_provider = RuntimeConfigProvider()
    task_manager = TaskManager(max_concurrent=1)

    init_config_routes(config_provider)
    init_tasks_routes(task_manager, config_provider, run_pipeline)
    init_zotero_routes(config_provider)
    init_services_routes(config_provider)

    app.register_blueprint(health_bp, url_prefix="/api/v1")
    app.register_blueprint(config_bp, url_prefix="/api/v1")
    app.register_blueprint(tasks_bp, url_prefix="/api/v1")
    app.register_blueprint(zotero_bp, url_prefix="/api/v1")
    app.register_blueprint(services_bp, url_prefix="/api/v1")

    @app.route("/")
    def index():
        return send_from_directory(
            os.path.join(os.path.dirname(__file__), "templates"),
            "index.html",
        )

    logger.info("Flask app created, config version=%d", config_provider.get_version())
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
