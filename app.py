from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import db, Product, Category, Order, OrderItem
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация БД
db.init_app(app)

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin):
    def __init__(self, id, username, password, is_admin=False):
        self.id = id
        self.username = username
        self.password = password
        self.is_admin = is_admin


# Для простоты используем фиксированного пользователя
users = {
    1: User(1, 'admin', generate_password_hash('admin'), True),
    2: User(2, 'user', generate_password_hash('user'))
}


@login_manager.user_loader
def load_user(user_id):
    return users.get(int(user_id))


# Создание БД
with app.app_context():
    db.create_all()
    # Добавляем тестовые данные, если их нет
    if not Category.query.first():
        categories = [
            Category(name='Овощные культуры'),
            Category(name='Цветы'),
            Category(name='Плодовые кустарники')
        ]
        db.session.add_all(categories)
        db.session.commit()

        products = [
            Product(name='Томат "Бычье сердце"', description='Крупноплодный сорт', price=150, category_id=1,
                    image='tomato.jpg'),
            Product(name='Петуния ампельная', description='Яркие цветы для кашпо', price=200, category_id=2,
                    image='petunia.jpg'),
            Product(name='Смородина черная', description='Сладкие ягоды', price=300, category_id=3,
                    image='smorodina.jpg')
        ]
        db.session.add_all(products)
        db.session.commit()


# Главная страница
@app.route('/')
def index():
    categories = Category.query.all()
    featured_products = Product.query.order_by(Product.id.desc()).limit(4).all()
    return render_template('index.html', categories=categories, featured_products=featured_products)


# Страница товаров
@app.route('/products')
def products():
    category_id = request.args.get('category_id')
    if category_id:
        products = Product.query.filter_by(category_id=category_id).all()
    else:
        products = Product.query.all()
    categories = Category.query.all()
    return render_template('products.html', products=products, categories=categories)


# Страница одного товара
@app.route('/product/<int:product_id>')
def product(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product.html', product=product)


# Корзина
@app.route('/cart')
def cart():
    cart = session.get('cart', {})
    products_in_cart = []
    total = 0

    normalized_cart = {str(k): v for k, v in cart.items()}

    for product_id_str, quantity in normalized_cart.items():
        try:
            product = Product.query.get(int(product_id_str))
            if product:
                products_in_cart.append({
                    'product': product,
                    'quantity': quantity,
                    'sum': product.price * quantity
                })
                total += product.price * quantity
        except (ValueError, TypeError):
            continue

    session['cart'] = normalized_cart

    return render_template('cart.html', products=products_in_cart, total=total)


# Добавление в корзину
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if not isinstance(product_id, int):
        flash('Неверный идентификатор товара', 'danger')
        return redirect(request.referrer)

    try:
        quantity = int(request.form.get('quantity', 1))
    except (ValueError, TypeError):
        quantity = 1

    cart = session.get('cart', {})
    product_id_str = str(product_id)
    cart[product_id_str] = cart.get(product_id_str, 0) + quantity
    session['cart'] = cart
    flash('Товар добавлен в корзину', 'success')
    return redirect(request.referrer)


# Оформление заказа
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Для оформления заказа необходимо войти в систему', 'warning')
            return redirect(url_for('login'))

        cart = session.get('cart', {})
        if not cart:
            flash('Ваша корзина пуста', 'warning')
            return redirect(url_for('cart'))

        # Создаем заказ
        order = Order(
            user_id=current_user.id,
            name=request.form['name'],
            phone=request.form['phone'],
            address=request.form['address'],
            status='new'
        )
        db.session.add(order)
        db.session.commit()

        # Добавляем товары в заказ
        for product_id, quantity in cart.items():
            product = Product.query.get(product_id)
            if product:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    price=product.price
                )
                db.session.add(order_item)

        db.session.commit()
        session.pop('cart', None)
        flash('Ваш заказ успешно оформлен!', 'success')
        return redirect(url_for('index'))

    return render_template('order.html')


# Авторизация
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = next((u for u in users.values() if u.username == username), None)
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Вы успешно вошли в систему', 'success')
            return redirect(url_for('index'))
        flash('Неверное имя пользователя или пароль', 'danger')
    return render_template('login.html')


# Выход
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))


# Админка - список товаров
@app.route('/admin/products')
@login_required
def admin_products():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))
    products = Product.query.all()
    return render_template('admin/products.html', products=products)


# Админка - список заказов
@app.route('/admin/orders')
@login_required
def admin_orders():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))
    orders = Order.query.all()
    return render_template('admin/orders.html', orders=orders)


@app.before_request
def fix_cart():
    if 'cart' in session and not isinstance(session['cart'], dict):
        session.pop('cart', None)

if __name__ == '__main__':
    app.run(debug=True)