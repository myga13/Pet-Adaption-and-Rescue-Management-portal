from flask import Flask
from config import Config
from extensions import db, migrate
from routes import bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init DB + Migrations
    db.init_app(app)
    migrate.init_app(app, db)

    # Register Blueprints
    app.register_blueprint(bp)

    # Create upload folders if not exist
    import os
    os.makedirs(app.config["USER_IMAGE_UPLOADS"], exist_ok=True)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
