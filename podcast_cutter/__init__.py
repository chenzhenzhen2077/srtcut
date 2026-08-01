"""Application factory for Podcast Cutter."""

from pathlib import Path

from flask import Flask, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from .config import Config


def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.config["WORK_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["BIN_DIR"]).mkdir(parents=True, exist_ok=True)

    from .routes import api

    app.register_blueprint(api)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(_error):
        return jsonify(
            {
                "error": "上传文件超过大小限制",
                "max_upload_mb": app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
            }
        ), 413

    return app
