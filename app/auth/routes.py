import uuid

from argon2 import hash_password
from flask import render_template, redirect, url_for, flash, request, session

from flask_login import login_user, logout_user, login_required, current_user
from app.utils.email import send_email
from app.utils.serializer import get_serializer
from app.utils.password_reset_email import password_reset_email
from . import auth_bp

from app.services.cart_service import merge_cart, merge_guest_cart_to_user, merge_wishlist
from app.utils.helpers import get_user_key, merge_guest_to_user


from app.extensions import db
from app.models import User, CheckoutDraft
from werkzeug.security import generate_password_hash, check_password_hash

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


ph = PasswordHasher()

# =========================
# REGISTER
# =========================
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')

        # check if user exists
        existing_user = User.query.filter(
            (User.email == email) | (User.username == username)
        ).first()

        if existing_user:
            flash("User with email or username already exists", "danger")
            return redirect(url_for('auth.register'))

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
            phone=phone,
            password_hash=ph.hash(password),
            role="customer"   # default role
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully!", "success")
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


# =========================
# LOGIN
# =========================
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        action = request.form.get("action")

        # =========================
        # GUEST FLOW
        # =========================
        if action == "guest":
            session["guest_email"] = request.form.get("login")
            get_user_key()  # ensures guest ID exists

            flash("Continuing as guest", "info")
            return redirect(url_for('cart.start_checkout')) 

        # =========================
        # LOGIN FLOW
        # =========================
        login_input = request.form.get('login')  # email
        password = request.form.get('password')

        user = User.query.filter(
            (User.username == login_input) | (User.email == login_input)
        ).first()

        if user and ph.verify(user.password_hash, password):

            login_user(user)
            flash("Login successful", "success")

            # =========================
            # MERGE GUEST DATA → USER
            # =========================
            guest_key = session.get("user_key")

            if guest_key:
                merge_cart(user.id, guest_key)
                merge_wishlist(user.id, guest_key)
                session.pop("user_key", None)

            # =========================
            # ROLE-BASED REDIRECT
            # =========================
            if user.role == "admin":
                return redirect(url_for('admin.dashboard'))

            return redirect(url_for('main.home'))

        flash("Invalid credentials", "danger")

    return render_template('auth/login.html')


# =========================
# LOGOUT
# =========================

@auth_bp.route('/logout')
@login_required
def logout():

    # remove logged-in user session
    logout_user()

    # clear old identity completely
    session.pop("user_key", None)

    # create NEW guest identity
    session["user_key"] = str(uuid.uuid4())

    flash("Logged out successfully", "info")
    return redirect(url_for('auth.login'))




# =========================
# PROFILE
# =========================
@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():

    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')
        current_user.phone = request.form.get('phone')

        db.session.commit()

        flash("Profile updated successfully!", "success")
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', user=current_user)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        user = User.query.filter_by(email=email).first()

        #Always use same response pattern (security best practice)
        if user:
            try:
                serializer = get_serializer()
                token = serializer.dumps(user.email, salt='password-reset-salt')

                reset_link = url_for(
                    'auth.reset_password',
                    token=token,
                    _external=True
                )

                send_email(
                    to=user.email,
                    subject="Password Reset Request",
                    html_content=password_reset_email(reset_link)
                )

            except Exception as e:
                print("Reset email error:", e)

        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        serializer=get_serializer()
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        flash("Invalid or expired link", "danger")
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        if password != confirm:
            flash("Passwords do not match", "danger")
            return redirect(request.url)

        user = User.query.filter_by(email=email).first()
        user.password_hash = ph.hash(password)

        db.session.commit()

        flash("Password updated successfully", "success")
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html')



@auth_bp.route("/convert-guest", methods=["POST"])
def convert_guest():

    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    name     = request.form.get("name", "").strip()

    if not email or not password or not name:
        flash("All fields are required.", "danger")
        return redirect(request.referrer or url_for("main.home"))

    # split name into first and last
    parts      = name.split(" ", 1)
    first_name = parts[0]
    last_name  = parts[1] if len(parts) > 1 else parts[0]

    # check if user already exists
    user = User.query.filter_by(email=email).first()

    if user:
        flash("Account already exists. Please log in.", "info")
        return redirect(url_for("auth.login"))

    # create new user from guest
    new_user = User(
        first_name=first_name,
        last_name=last_name,
        username=name,
        email=email,
        password_hash=ph.hash(password)
    )

    db.session.add(new_user)
    db.session.commit()

    # merge guest cart into new user
    merge_guest_to_user(new_user)

    login_user(new_user)

    flash("Account created successfully!", "success")
    return redirect(url_for("main.home"))