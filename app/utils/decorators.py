from functools import wraps
from flask import abort
from flask_login import current_user

from flask import redirect, url_for

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        if current_user.role != "admin":
            return redirect(url_for("main.home"))

        return f(*args, **kwargs)
    return wrapper