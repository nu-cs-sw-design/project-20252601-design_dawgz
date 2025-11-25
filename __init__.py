from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from app.config import db_user, db_password, db_host, db_port, db_name

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    # Connect to PostgreSQL database
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # optional, disables overhead

    db.init_app(app)

    # Import and register blueprints
    from routes.gpt import gpt_bp

    app.register_blueprint(gpt_bp, url_prefix='/gpt')

    return app
