# app.py
from flask import Flask
from config import Config
from extensions import db, migrate
from routes import bp
import os
from extensions import db, socketio
from flask_wtf.csrf import CSRFProtect
from flask_wtf.csrf import generate_csrf


from flask_wtf.csrf import CSRFProtect



csrf = CSRFProtect()
def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.from_object(Config)
    csrf.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*")
    app.register_blueprint(bp)
     

    # Create upload folders if not exist
    os.makedirs(app.config["USER_IMAGE_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["ADMIN_PROFILE_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["ADMIN_ID_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["FOUND_PET_UPLOADS"], exist_ok=True)
    os.makedirs(app.config["LOST_PET_UPLOADS"], exist_ok=True)  # 🔹 NEW
    import socketio_events
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
# app factory, e.g. create_app() in __init__.py or app.py