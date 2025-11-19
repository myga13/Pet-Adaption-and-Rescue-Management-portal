import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = "my-secret-key"
    
    # MySQL connection
    SQLALCHEMY_DATABASE_URI = (
        "mysql+pymysql://root:root@127.0.0.1:3306/petrecueandadaptionmanagementportal"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Media / Uploads
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")
    USER_IMAGE_UPLOADS = os.path.join(MEDIA_ROOT, "user_images")

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
