# app.py
from flask import Flask
from config import Config
from extensions import db, migrate, socketio, csrf
from routes import bp
import os


def create_app():
    app = Flask(__name__, static_folder="static")
    app.config.from_object(Config)

    # 🔹 INIT EXTENSIONS
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")

    # 🔹 BLUEPRINT
    app.register_blueprint(bp)

    # 🔹 CREATE UPLOAD FOLDERS
    os.makedirs(app.config["USER_IMAGE_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["ADMIN_PROFILE_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["ADMIN_ID_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["FOUND_PET_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["LOST_PET_UPLOADS"], exist_ok=True)

    # 🔹 SOCKET EVENTS (after app exists)
    import socketio_events

    return app


app = create_app()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
