# Filename: gpt_blueprint.py
# Description: Defines the single Blueprint object for all GPT-related routes.

from flask import Blueprint
from flask_cors import CORS

gpt_bp = Blueprint("gpt", __name__)
CORS(gpt_bp, resources={r"/*": {"origins": "*"}})

# The main app will register this one object.

