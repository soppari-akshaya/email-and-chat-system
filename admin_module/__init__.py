from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

from admin_module import routes

