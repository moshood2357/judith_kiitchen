from datetime import datetime
import enum
from flask_login import UserMixin
from .extensions import db


# =========================
# ENUMS
# =========================

class OrderStatus(enum.Enum):
    pending    = "pending"
    processing = "processing"
    accepted   = "accepted"
    preparing  = "preparing"
    shipped    = "shipped"
    delivered  = "delivered"
    completed  = "completed"
    cancelled  = "cancelled"



class PaymentStatus(enum.Enum):
    unpaid = "unpaid"
    paid = "paid"
    failed = "failed"



# =========================
# USERS
# =========================

class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)

    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))

    role = db.Column(db.String(20), default="customer")
    is_admin = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    addresses = db.relationship("Address", backref="user", lazy=True)
    orders = db.relationship("Order", backref="user", lazy=True)
    cart = db.relationship("Cart", backref="user", uselist=False)
    wishlist_items = db.relationship("Wishlist", backref="user", lazy=True)


# =========================
# ADDRESS
# =========================

class Address(db.Model):
    __tablename__ = "address"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)

    address_line_1 = db.Column(db.String(255), nullable=False)
    address_line_2 = db.Column(db.String(255))
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(20))

    is_default = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# CATEGORY
# =========================

class Category(db.Model):
    __tablename__ = "category"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(150), unique=True, nullable=False)

    description = db.Column(db.Text)
    image = db.Column(db.String(255))

    products = db.relationship("Product", backref="category", lazy=True)


# =========================
# PRODUCT
# =========================

class Product(db.Model):
    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)

    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)

    description = db.Column(db.Text, nullable=False)
    short_description = db.Column(db.String(255))

    price = db.Column(db.Numeric(10, 2), nullable=False)
    discount_price = db.Column(db.Numeric(10, 2))

    sku = db.Column(db.String(100), unique=True)
    stock_quantity = db.Column(db.Integer, default=0)

    brand = db.Column(db.String(100))
    image = db.Column(db.String(255))

    is_active = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# CART
# =========================

class Cart(db.Model):
    __tablename__ = "cart"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    items = db.relationship(
        "CartItem",
        backref="cart",
        cascade="all, delete-orphan",
        lazy=True
    )
    
    user_key = db.Column(db.String(100), index=True, nullable=True)



class CartItem(db.Model):
    __tablename__ = "cart_item"

    id = db.Column(db.Integer, primary_key=True)

    cart_id = db.Column(db.Integer, db.ForeignKey("cart.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    quantity = db.Column(db.Integer, default=1)

    # snapshot data (important for order integrity)
    unit_price = db.Column(db.Numeric(10, 2))
    product_name = db.Column(db.String(200))
    product_image = db.Column(db.String(255))

    from_wishlist = db.Column(db.Boolean, default=False)
    

    product = db.relationship("Product")


# =========================
# WISHLIST
# =========================

class Wishlist(db.Model):
    __tablename__ = "wishlist"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_key = db.Column(db.String(100), index=True, nullable=True)



# =========================
# ORDER
# =========================

class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    address_id = db.Column(db.Integer, db.ForeignKey("address.id"), nullable=False)

    order_number = db.Column(db.String(100), unique=True, nullable=False)

    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    shipping_fee = db.Column(db.Numeric(10, 2), default=0)
    tax = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    delivery_method = db.Column(db.String(50))

    fulfillment_type = db.Column(db.String(20), default="delivery")  # "delivery" | "pickup"
    pickup_date  = db.Column(db.Date, nullable=True)
    pickup_time  = db.Column(db.String(20), nullable=True)

    status = db.Column(db.Enum(OrderStatus), default=OrderStatus.pending, nullable=False)
    payment_status = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.unpaid, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    prep_time       = db.Column(db.Integer, nullable=True)
    timer_started_at = db.Column(db.DateTime, nullable=True)
    timer_status    = db.Column(db.String(20), default="pending")  # pending, running, completed
      
    guest_email = db.Column(db.String(120))
    
    rejection_reason = db.Column(db.Text, nullable=True)

    note = db.Column(db.Text, nullable=True)

    
    ready_at = db.Column(db.DateTime, nullable=True)

    delivery_miles = db.Column(db.Float, nullable=True)
    delivery_fee   = db.Column(db.Float, nullable=True)

    # relationships
    address = db.relationship("Address", backref="orders")
    items = db.relationship(
        "OrderItem",
        backref="order",
        cascade="all, delete-orphan",
        lazy=True
    )
    payment = db.relationship("Payment", backref="order", uselist=False)


# =========================
# ORDER ITEM
# =========================

class OrderItem(db.Model):
    __tablename__ = "order_item"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

    # snapshot (important for historical accuracy)
    product_name = db.Column(db.String(200))
    product_image = db.Column(db.String(255))

    product = db.relationship("Product")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)


# =========================
# PAYMENT
# =========================

class Payment(db.Model):
    __tablename__ = "payment"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)

    payment_method = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(255), unique=True)

    amount = db.Column(db.Numeric(10, 2), nullable=False)

    status = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.unpaid, nullable=False)

    reference = db.Column(db.String(255), unique=True)
    gateway_response = db.Column(db.Text)

    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)


# =========================
# REVIEW
# =========================

class Review(db.Model):
    __tablename__ = "review"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# COUPON
# =========================

class Coupon(db.Model):
    __tablename__ = "coupon"

    id = db.Column(db.Integer, primary_key=True)

    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), nullable=False)
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)

    minimum_order_amount = db.Column(db.Numeric(10, 2), default=0)
    expiration_date = db.Column(db.DateTime)

    is_active = db.Column(db.Boolean, default=True)


# =========================
# NEWSLETTER
# =========================

class NewsletterSubscriber(db.Model):
    __tablename__ = "newsletter_subscriber"

    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(120), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)



class CheckoutDraft(db.Model):
    __tablename__ = "checkout_draft"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user_key = db.Column(db.String(255), index=True)  # IMPORTANT

    full_name = db.Column(db.String(150))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))

    address_line_1 = db.Column(db.String(255))
    address_line_2 = db.Column(db.String(255))

    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))

    cart_snapshot = db.Column(db.Text)

    delivery_method = db.Column(db.String(50))
    country = db.Column(db.String(100))

    fulfillment_type = db.Column(db.String(20), default="delivery")  # "delivery" | "pickup"
    pickup_date  = db.Column(db.Date, nullable=True)
    pickup_time  = db.Column(db.String(20), nullable=True)

    note = db.Column(db.Text, nullable=True)

    delivery_miles = db.Column(db.Float, nullable=True)
    delivery_fee   = db.Column(db.Float, nullable=True)

    
    # Totals snapshot
    subtotal = db.Column(db.Numeric(10, 2))
    shipping_fee = db.Column(db.Numeric(10, 2), default=0)
    tax = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2))


    billing_address_line_1 = db.Column(db.String(255))
    billing_address_line_2 = db.Column(db.String(255))

    billing_city = db.Column(db.String(100))
    billing_state = db.Column(db.String(100))
    billing_postal_code = db.Column(db.String(20))

    same_as_delivery = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow) 
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed    = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)