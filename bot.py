import json
from telebot import TeleBot, types
from telebot.types import LabeledPrice
import pandas as pd

TOKEN = "YOUR_BOT_TOKEN"
PROVIDER_TOKEN = "YOUR_PROVIDER_TOKEN"  # если пустой — оплата отключена
ADMIN_ID = 123456789  # твой Telegram ID

bot = TeleBot(TOKEN)

# ----------------- Вспомогательные функции -----------------
def load_products():
    with open("products.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_products(products):
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def load_orders():
    try:
        with open("orders.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_orders(orders):
    with open("orders.json", "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

# ----------------- Доставка -----------------
district_prices = {"Центр": 0, "Свердловский": 200, "Кировский": 200, "Советский": 200}

def calculate_total(items, district="Центр"):
    total = sum(i['price']*i['weight'] for i in items)
    delivery = district_prices.get(district, 200)
    if total >= 1000:
        delivery = 0
    return total + delivery

# ----------------- Хранение данных пользователей -----------------
user_data = {}  # корзины, комментарии, район

# ----------------- Старт -----------------
@bot.message_handler(commands=['start'])
def start(message):
    user_data[message.chat.id] = {"cart": []}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Каталог", "Корзина")
    bot.send_message(message.chat.id, "Добро пожаловать в Шеф Маркет!", reply_markup=markup)

# ----------------- Каталог -----------------
@bot.message_handler(func=lambda m: m.text == "Каталог")
def show_categories(message):
    products = load_products()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for cat in products.keys():
        markup.add(cat)
    markup.add("Назад")
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in load_products().keys())
def show_products(message):
    products = load_products()
    cat = message.text
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    for item in products[cat]:
        markup.add(item['name'])
    markup.add("Назад")
    bot.send_message(message.chat.id, f"Товары в категории {cat}:", reply_markup=markup)

@bot.message_handler(func=lambda m: any(m.text in [i['name'] for i in load_products()[c]] for c in load_products()))
def add_to_cart(message):
    products = load_products()
    for cat, items in products.items():
        for item in items:
            if item['name'] == message.text:
                if item['photo']:
                    bot.send_photo(message.chat.id, item['photo'])
                msg = bot.send_message(message.chat.id, f"Выберите вес (кг) для {item['name']}:")
                bot.register_next_step_handler(msg, lambda m: set_weight(m, item))
                return

def set_weight(message, item):
    try:
        weight = float(message.text)
        user_data[message.chat.id]["cart"].append({"name": item['name'], "price": item['price'], "weight": weight})
        bot.send_message(message.chat.id, f"{item['name']} ({weight} кг) добавлен в корзину ✅")
    except:
        bot.send_message(message.chat.id, "Ошибка! Введите число.")

# ----------------- Корзина -----------------
@bot.message_handler(func=lambda m: m.text == "Корзина")
def show_cart(message):
    cart = user_data[message.chat.id]["cart"]
    if not cart:
        bot.send_message(message.chat.id, "Корзина пуста 🛒")
        return
    text = "Ваш заказ:\n"
    for i in cart:
        text += f"{i['name']} — {i['weight']} кг — {i['price']*i['weight']} ₽\n"
    district = user_data[message.chat.id].get("district","Центр")
    total = calculate_total(cart, district)
    text += f"\nРайон доставки: {district}\nИтого: {total} ₽"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Оформить заказ", "Очистить корзину", "Назад")
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "Очистить корзину")
def clear_cart(message):
    user_data[message.chat.id] = {"cart": []}
    bot.send_message(message.chat.id, "Корзина очищена 🗑️")

# ----------------- Оформление заказа -----------------
@bot.message_handler(func=lambda m: m.text == "Оформить заказ")
def start_order(message):
    msg = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for d in district_prices.keys():
        msg.add(d)
    bot.send_message(message.chat.id, "Выберите район доставки:", reply_markup=msg)
    bot.register_next_step_handler(message, save_district)

def save_district(message):
    user_data[message.chat.id]['district'] = message.text
    msg = bot.send_message(message.chat.id, "Оставьте комментарий к заказу (или напишите 'нет'):")
    bot.register_next_step_handler(msg, save_comment)

def save_comment(message):
    comment = message.text
    chat_id = message.chat.id
    if comment.lower() == 'нет':
        comment = ""
    user_data[chat_id]['comment'] = comment
    proceed_checkout(message)

def proceed_checkout(message):
    cart = user_data[message.chat.id]["cart"]
    district = user_data[message.chat.id].get("district","Центр")
    total = calculate_total(cart, district)
    if not PROVIDER_TOKEN:
        save_order(message.chat.id, cart, total)
        bot.send_message(message.chat.id, f"Заказ принят ✅ Сумма: {total} ₽")
        return
    prices = [LabeledPrice(label=i['name'], amount=int(i['price']*i['weight']*100)) for i in cart]
    delivery_fee = district_prices.get(district,200)
    if total < 1000:
        prices.append(LabeledPrice(label="Доставка", amount=delivery_fee*100))
    bot.send_invoice(message.chat.id, title="Оплата заказа", description="Спасибо за заказ!",
                     provider_token=PROVIDER_TOKEN, currency="RUB", prices=prices,
                     start_parameter="shop", payload="order_payload")

def save_order(chat_id, cart, total):
    orders = load_orders()
    orders.append({
        "id": len(orders)+1,
        "client": chat_id,
        "items": cart,
        "total": total,
        "status": "новый",
        "comment": user_data[chat_id].get("comment", ""),
        "district": user_data[chat_id].get("district","Центр")
    })
    save_orders(orders)
    bot.send_message(ADMIN_ID, f"Новый заказ! ID {len(orders)}")
    user_data[chat_id]["cart"] = []

# ----------------- Админ-панель -----------------
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Доступ запрещен")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("/orders", "/edit_products", "/export_orders")
    bot.send_message(message.chat.id, "Админ-панель 🛠️", reply_markup=markup)

@bot.message_handler(commands=['orders'])
def list_orders(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Доступ запрещен")
        return
    orders = load_orders()
    if not orders:
        bot.send_message(message.chat.id, "Заказы отсутствуют 📦")
        return
    for order in orders:
        text = f"ID: {order['id']}\nКлиент: {order['client']}\nСумма: {order['total']} ₽\nСтатус: {order['status']}"
        markup = types.InlineKeyboardMarkup()
        statuses = ["новый", "готовится", "в пути", "доставлен"]
        for s in statuses:
            if s != order['status']:
                markup.add(types.InlineKeyboardButton(f"→ {s}", callback_data=f"status_{order['id']}_{s}"))
        markup.add(types.InlineKeyboardButton("Подробнее", callback_data=f"details_{order['id']}"))
        bot.send_message(message.chat.id, text, reply_markup=markup)

# ----------------- Экспорт заказов -----------------
@bot.message_handler(commands=['export_orders'])
def export_orders(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Доступ запрещен")
        return
    orders = load_orders()
    rows = []
    for o in orders:
        for i in o['items']:
            rows.append({
                "ID": o['id'],
                "Клиент": o['client'],
                "Товар": i['name'],
                "Вес": i['weight'],
                "Цена": i['price'],
                "Итого": i['price']*i['weight'],
                "Статус": o['status'],
                "Комментарий": o.get('comment', ""),
                "Район": o.get('district',"")
            })
    df = pd.DataFrame(rows)
    file_path = "orders.xlsx"
    df.to_excel(file_path, index=False)
    with open(file_path, "rb") as f:
        bot.send_document(message.chat.id, f)

# ----------------- Запуск бота -----------------
bot.polling(none_stop=True)
