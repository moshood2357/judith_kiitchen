from flask import jsonify, redirect, render_template, request, flash
from flask_login import login_required
from . import main
from app.models import Category, Product, NewsletterSubscriber
from app.extensions import db


@main.route('/')
def home():
    featured_products = Product.query.order_by(Product.created_at.desc()).limit(8).all()
    categories = Category.query.limit(12).all()

    return render_template(
        'main/index.html',
        featured_products=featured_products,
        categories=categories
    )

@main.route('/shop')
def shop():
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category', type=int)
    sort = request.args.get('sort')

    categories = Category.query.all()

    query = Product.query

    #  FILTER BY CATEGORY
    if category_id:
        query = query.filter(Product.category_id == category_id)

    #  SORTING
    if sort == "newest":
        query = query.order_by(Product.created_at.desc())

    elif sort == "low_high":
        query = query.order_by(Product.price.asc())

    elif sort == "high_low":
        query = query.order_by(Product.price.desc())

    
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.paginate(page=page, per_page=10)

    return render_template(
        'main/shop.html',
        products=products,
        categories=categories,
        selected_category=category_id,
        selected_sort=sort
    )



@main.route('/product/<slug>')
def product_details(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()

    related_products = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id
    ).limit(4).all()

    return render_template(
        'main/product_details.html',
        product=product,
        related_products=related_products
    )


@main.route('/search')
def search():
    query = request.args.get('q', '')

    products = Product.query.filter(
        Product.name.ilike(f'%{query}%')
    ).all()

    return render_template(
        'main/search_results.html',
        products=products,
        query=query
    )


@main.route('/about-us')
def about():
    return render_template('main/about.html')


@main.route('/contact-us')
def contact():
    return render_template('main/contact.html')

@main.route('/subscribe', methods=['POST'])
def subscribe():
    email = request.form.get('email')

    # Validate email
    if not email:
        flash("Please enter a valid email", "danger")
        return redirect(request.referrer)

    # Check if already subscribed
    existing = NewsletterSubscriber.query.filter_by(email=email).first()

    if existing:
        flash("You're already subscribed!", "info")
        return redirect(request.referrer)

    # Save to DB
    subscriber = NewsletterSubscriber(email=email)
    db.session.add(subscriber)
    db.session.commit()

    flash("Subscribed successfully 🎉", "success")
    return redirect(request.referrer)   



@main.route('/api/search')
def api_search():

    query = request.args.get('q', '').strip()

    if not query:
        return jsonify([])

    products = Product.query.filter(
        Product.name.ilike(f"%{query}%")
    ).limit(8).all()

    return jsonify([
        {
            "name": p.name,
            "price": p.price,
            "slug": p.slug,
            "image": p.image
        }
        for p in products
    ])



@main.route('/category/<slug>')
def category_products(slug):

    page = request.args.get('page', 1, type=int)
    per_page = 12

    category = Category.query.filter_by(slug=slug).first_or_404()

    products = Product.query.filter_by(category_id=category.id)\
        .paginate(page=page, per_page=per_page)

    return render_template(
        "main/category_products.html",
        category=category,
        products=products.items,
        pagination=products
    )