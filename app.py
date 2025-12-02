# app.py
from flask import Flask
from config import Config
from extensions import db, migrate
from routes import bp
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(bp)

    # Create upload folders if not exist
    os.makedirs(app.config["USER_IMAGE_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["ADMIN_PROFILE_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["ADMIN_ID_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["FOUND_PET_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["LOST_PET_UPLOADS"], exist_ok=True)  # 🔹 NEW

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
