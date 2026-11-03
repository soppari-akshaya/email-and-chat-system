
from flask import Blueprint

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")

from chat_module import routes
