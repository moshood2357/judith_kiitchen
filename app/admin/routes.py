import os
import uuid
from werkzeug.utils import secure_filename

from flask import render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from datetime import datetime
from app import csrf

from app.forms import DeleteForm
from app.utils.decorators import admin_required
from app.utils.helpers import generate_slug

from . import admin_bp
from app.extensions import db
from app.models import CartItem, OrderStatus, PaymentStatus, Product, Category, Order, Wishlist

from slugify import slugify


# =========================
# ONLINE ORDERS ONLY
# =========================
# Walk-in (counter) orders live on the kitchen display and order board only.
# `is_(None)` keeps older orders that have no fulfillment_type set - a plain
# `!= "walk_in"` would silently drop those rows in SQL.
NOT_WALK_IN = or_(Order.fulfillment_type.is_(None), Order.fulfillment_type != "walk_in")


def online_orders():
    return Order.query.filter(NOT_WALK_IN)


# ====================
# AJAX ENDPOINT TO GET LATEST ORDER ID
# ====================
@admin_bp.route("/orders/latest-id")
@login_required
@admin_required
def latest_order_id():
    from flask import jsonify
    # Online orders only, so a walk-in never triggers the "new order" alert
    order = online_orders().order_by(Order.id.desc()).first()
    total = online_orders().count()
    return jsonify({
        "latest_id":    order.id if order else 0,
        "total_orders": total
    })


# =========================
# ADMIN DASHBOARD
# =========================

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():

    # =========================
    # STATS (NUMBERS ONLY)
    # =========================
    total_products = Product.query.count()
    total_categories = Category.query.count()

    # Online orders only; walk-ins aren't part of the orders table
    total_orders = online_orders().count()

    # Sales include walk-ins: it's all money the kitchen took.
    # To count online sales only, add NOT_WALK_IN to the filter below.
    total_sales = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.payment_status == PaymentStatus.paid
    ).scalar()

    delete_form = DeleteForm()

    # =========================
    # DISPLAY DATA (LISTS ONLY)
    # =========================
    recent_products = Product.query.order_by(Product.created_at.desc()).limit(12).all()

    categories_available = Category.query.order_by(Category.id.desc()).all()

    return render_template(
        'admin/dashboard.html',

        # stats
        products=total_products,
        categories=total_categories,
        orders=total_orders,
        total_sales=total_sales,

        # display data
        recent_products=recent_products,
        categories_available=categories_available,
        delete_form=delete_form
    )


# =========================
# PRODUCTS LIST
# =========================
@admin_bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():

    # GET categories for dropdown
    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':

        name = request.form.get('name')
        description = request.form.get('description')
        short_description = request.form.get('short_description')
        category_id = request.form.get('category_id')
        price = request.form.get('price')
        stock_quantity = request.form.get('stock_quantity')

        if not category_id:
            flash("Please select a category", "danger")
            return redirect(request.url)

        if not name or not price:
            flash("Name and price are required", "danger")
            return redirect(request.url)

        # convert category_id to int
        category_id = int(category_id)

        # slug auto generation
        slug = generate_slug(name)

        # image upload
        image = request.files.get('image')
        image_filename = None

        if image and image.filename != "":
            filename = secure_filename(image.filename)

            # prevent overwrite (IMPORTANT)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"

            upload_path = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                unique_filename
            )

            image.save(upload_path)
            image_filename = unique_filename

        # create product
        product = Product(
            name=name,
            slug=slug,
            description=description,
            short_description=short_description,
            price=price,
            category_id=category_id,
            stock_quantity=stock_quantity,
            image=image_filename
        )

        db.session.add(product)
        db.session.commit()

        flash("Product added successfully!", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template(
        'admin/add_product.html',
        categories=categories
    )


# =========================
# DELETE PRODUCT
# =========================
@admin_bp.route('/product/delete/<slug>', methods=['POST'])
@login_required
@admin_required
def delete_product(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()

    # manually clean dependencies
    CartItem.query.filter_by(product_id=product.id).delete()
    Wishlist.query.filter_by(product_id=product.id).delete()

    db.session.delete(product)
    db.session.commit()

    flash("Product deleted successfully", "success")
    return redirect(url_for('admin.dashboard'))


# =========================
# ORDERS VIEW
# =========================
@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    page = request.args.get('page', 1, type=int)
    orders = (online_orders()
              .order_by(Order.id.desc())
              .paginate(page=page, per_page=20))
    return render_template('admin/orders.html', orders=orders)


# =========================
# UPDATE ORDER STATUS
# =========================
@admin_bp.route("/orders/update/<int:id>", methods=["POST"])
@csrf.exempt
@login_required
@admin_required
def update_order_status(id):
    from flask import request, jsonify
    from app.utils.email import send_order_confirmation_customer, send_order_rejected_customer

    order     = Order.query.get_or_404(id)
    data      = request.get_json()
    status    = data.get("status")
    prep_time = data.get("prep_time")
    reason    = data.get("rejection_reason", "").strip()

    print(f"update_order_status called: order={id}, status={status}, prep_time={prep_time}")

    try:
        order.status = OrderStatus[status]

        if prep_time:
            order.prep_time = int(prep_time)

        if status == "cancelled" and reason:
            order.rejection_reason = reason

        db.session.commit()
        print(f"DB commit successful for order {id}")

        # Walk-ins have no email address, so only email online customers
        has_email = bool(order.user or order.guest_email)

        if status == "accepted" and has_email:
            try:
                send_order_confirmation_customer(order)
                print(f"Customer email sent for order {id}")
            except Exception as e:
                print(f"Customer email failed: {e}")

        if status == "cancelled" and reason and has_email:
            try:
                send_order_rejected_customer(order, reason)
                print(f"Rejection email sent for order {id}")
            except Exception as e:
                print(f"Rejection email failed: {e}")

        print(f"Returning success for order {id}")
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        print(f"update_order_status error: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False}), 500


@admin_bp.route('/category/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_category():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        image_file = request.files.get('image')

        if not name:
            flash("Category name is required", "danger")
            return redirect(url_for('admin.add_category'))

        slug = slugify(name)

        # prevent duplicates
        if Category.query.filter_by(slug=slug).first():
            flash("Category already exists", "warning")
            return redirect(url_for('admin.add_category'))

        filename = None

        # handle image upload
        if image_file and image_file.filename != "":
            ext = image_file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"

            upload_path = os.path.join(current_app.root_path, 'static/uploads/categories')
            os.makedirs(upload_path, exist_ok=True)

            image_file.save(os.path.join(upload_path, filename))

        category = Category(
            name=name,
            slug=slug,
            description=description,
            image=filename
        )

        db.session.add(category)
        db.session.commit()

        flash("Category created successfully", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/add_category.html')


@admin_bp.route('/category/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_category(id):

    category = Category.query.get_or_404(id)

    # OPTIONAL SAFETY: prevent deleting categories with products
    if Product.query.filter_by(category_id=id).first():
        flash("Cannot delete category with existing products", "danger")
        return redirect(url_for('admin.dashboard'))

    db.session.delete(category)
    db.session.commit()

    flash("Category deleted successfully", "success")
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/category/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(id):
    category = Category.query.get_or_404(id)

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        image_file = request.files.get('image')

        if not name:
            flash("Category name is required", "danger")
            return redirect(request.url)

        # update fields
        category.name = name
        category.slug = slugify(name)
        category.description = description

        # update image if provided
        if image_file and image_file.filename != "":
            ext = image_file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"

            upload_path = os.path.join(current_app.root_path, 'static/uploads/categories')
            os.makedirs(upload_path, exist_ok=True)

            image_file.save(os.path.join(upload_path, filename))
            category.image = filename

        db.session.commit()

        flash("Category updated successfully", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template(
        'admin/edit_category.html',
        category=category
    )


# =========================
# EDIT PRODUCT
# =========================
@admin_bp.route('/products/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(id):

    product = Product.query.get_or_404(id)
    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':

        name = request.form.get('name')
        description = request.form.get('description')
        short_description = request.form.get('short_description')
        category_id = request.form.get('category_id')
        price = request.form.get('price')
        stock_quantity = request.form.get('stock_quantity')

        if not name or not price:
            flash("Name and price are required", "danger")
            return redirect(request.url)

        if not category_id:
            flash("Please select a category", "danger")
            return redirect(request.url)

        # update fields
        product.name = name
        product.slug = generate_slug(name)
        product.description = description
        product.short_description = short_description
        product.price = price
        product.category_id = int(category_id)
        product.stock_quantity = stock_quantity

        # handle image update
        image = request.files.get('image')

        if image and image.filename != "":
            filename = secure_filename(image.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"

            upload_path = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                unique_filename
            )

            image.save(upload_path)

            # OPTIONAL: delete old image
            if product.image:
                old_path = os.path.join(
                    current_app.config['UPLOAD_FOLDER'],
                    product.image
                )
                if os.path.exists(old_path):
                    os.remove(old_path)

            product.image = unique_filename

        db.session.commit()

        flash("Product updated successfully!", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template(
        'admin/edit_product.html',
        product=product,
        categories=categories
    )