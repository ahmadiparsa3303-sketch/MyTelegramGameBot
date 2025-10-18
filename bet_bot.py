import logging
import random
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, timedelta

# ==============================================================================
#           تنظیمات و متغیرهای اصلی (حتماً ویرایش شوند)
# ==============================================================================

# 🔴 ۱. توکن ربات خود را اینجا وارد کنید
TOKEN = "8391879296:AAFvX3yUUM3-abvO7rsopuIwxsaEDELUB54"

# 🔴 ۲. آیدی عددی صاحب ربات
ADMIN_USER_ID = 1322527655

MINER_PRICE = 1000000
MINER_HOURLY_INCOME = 100000
COIN_COOLDOWN_MINUTES = 10

# 🆕 تنظیمات کارخانه بنز
BENZ_PRICE_PER_PERCENT = 100_000_000 # قیمت هر 1% سهام بنز
BENZ_HOURLY_INCOME_PER_PERCENT = 10_000_000 # درآمد ساعتی هر 1% سهام بنز

# مسیر فایل دیتابیس (فایل به طور خودکار در همین پوشه ساخته می‌شود)
DATA_FILE = 'bot_data.json'

# ==============================================================================
#           دیتابیس (دیکشنری‌های ذخیره اطلاعات)
# ==============================================================================

user_balances = {}       # موجودی در دسترس (Wallet)
user_savings = {}        # موجودی پس‌انداز (Bank)
user_cooldowns = {}      # زمان آخرین استفاده از /coin (ذخیره به صورت datetime)
user_miners = {}         # تعداد ماینرها
user_benz_shares = {}    # درصد سهام کارخانه بنز (مثلاً 5.5 برای 5.5 درصد)
last_take_time = {}      # زمان آخرین برداشت از ماینر و سهام (ذخیره به صورت datetime)

used_card_numbers = {}   # ذخیره شماره کارت و صاحب آن (Card_ID: User_ID)
NEXT_CARD_NUMBER = 10000

# 🆕 ذخیره نام کاربران برای لیدربورد
user_usernames = {} 

# تنظیمات اولیه لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ==============================================================================
#           توابع حفظ داده (ذخیره و بارگذاری)
# ==============================================================================

def save_data():
    """ذخیره تمام دیکشنری‌های اطلاعات در یک فایل JSON."""
    data = {
        'balances': user_balances,
        'savings': user_savings,
        # تبدیل آبجکت‌های datetime به رشته‌های استاندارد برای ذخیره در JSON
        'cooldowns': {str(uid): time.isoformat() for uid, time in user_cooldowns.items()}, 
        'miners': user_miners,
        'benz_shares': user_benz_shares,
        'last_take': {str(uid): time.isoformat() for uid, time in last_take_time.items()}, 
        'used_cards': used_card_numbers,
        'next_card': NEXT_CARD_NUMBER,
        'usernames': user_usernames # 🆕 ذخیره نام‌های کاربری
    }
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"خطا در ذخیره داده‌ها: {e}")

def load_data():
    """بارگذاری تمام دیکشنری‌های اطلاعات از فایل JSON."""
    global NEXT_CARD_NUMBER
    global user_balances, user_savings, user_cooldowns, user_miners, user_benz_shares, last_take_time, used_card_numbers, user_usernames
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # ۱. بارگذاری داده‌های اصلی (کلیدهای dict باید به int تبدیل شوند)
            user_balances.update({int(k): v for k, v in data.get('balances', {}).items()})
            user_savings.update({int(k): v for k, v in data.get('savings', {}).items()})
            user_miners.update({int(k): v for k, v in data.get('miners', {}).items()})
            user_benz_shares.update({int(k): v for k, v in data.get('benz_shares', {}).items()})
            
            # ۲. بارگذاری داده‌های زمان‌دار (تبدیل از رشته به datetime)
            user_cooldowns.update({int(k): datetime.fromisoformat(v) for k, v in data.get('cooldowns', {}).items()})
            last_take_time.update({int(k): datetime.fromisoformat(v) for k, v in data.get('last_take', {}).items()})
            
            # ۳. بارگذاری سیستم شماره کارت
            used_card_numbers.update({int(k): v for k, v in data.get('used_cards', {}).items()})
            NEXT_CARD_NUMBER = data.get('next_card', 10000)
            
            # 🆕 ۴. بارگذاری نام‌های کاربری
            user_usernames.update({int(k): v for k, v in data.get('usernames', {}).items()})
            
        logging.info("داده‌های ربات با موفقیت بارگذاری شد.")
    except FileNotFoundError:
        logging.warning("فایل دیتابیس (bot_data.json) پیدا نشد. با داده‌های جدید شروع می‌شود.")
    except Exception as e:
        logging.error(f"خطا در بارگذاری داده‌ها: {e}")

# ==============================================================================
#           توابع کمکی و منطق ربات
# ==============================================================================

def generate_unique_card_number(user_id):
    """تولید و تخصیص شماره کارت ۵ رقمی منحصر به فرد."""
    global NEXT_CARD_NUMBER
    # اگر کاربر قبلا شماره کارت دارد، همان را برمی‌گرداند.
    for card, uid in used_card_numbers.items():
        if uid == user_id:
            return card
    
    # تولید شماره جدید
    while NEXT_CARD_NUMBER in used_card_numbers:
        NEXT_CARD_NUMBER += 1
    
    card_number = NEXT_CARD_NUMBER
    used_card_numbers[card_number] = user_id 
    NEXT_CARD_NUMBER += 1
    return card_number

def initialize_user_data(user_id, username=None):
    """مقادیر اولیه کاربر را در صورت عدم وجود، تنظیم می‌کند و نام کاربری را ذخیره می‌کند."""
    user_balances.setdefault(user_id, 0)
    user_savings.setdefault(user_id, 0)
    user_miners.setdefault(user_id, 0)
    user_benz_shares.setdefault(user_id, 0.0) 
    last_take_time.setdefault(user_id, datetime.now())
    generate_unique_card_number(user_id)
    if username: # 🆕 ذخیره یا بروزرسانی نام کاربری
        user_usernames[user_id] = username

def calculate_miner_income(user_id, hours_elapsed):
    """درآمد ماینرها را بر اساس زمان سپری شده محاسبه می‌کند."""
    miners = user_miners.get(user_id, 0)
    earned_coins = int(hours_elapsed * miners * MINER_HOURLY_INCOME) 
    return earned_coins

def calculate_benz_income(user_id, hours_elapsed):
    """درآمد سهام بنز را بر اساس زمان سپری شده محاسبه می‌کند."""
    shares = user_benz_shares.get(user_id, 0.0)
    earned_coins = int(hours_elapsed * shares * BENZ_HOURLY_INCOME_PER_PERCENT)
    return earned_coins

def calculate_total_income(user_id):
    """درآمد انباشته کل (ماینر و بنز) را محاسبه می‌کند."""
    last_time = last_take_time.get(user_id, datetime.now())
    now = datetime.now()
    
    time_elapsed = now - last_time
    hours_elapsed = time_elapsed.total_seconds() / 3600
    
    miner_income = calculate_miner_income(user_id, hours_elapsed)
    benz_income = calculate_benz_income(user_id, hours_elapsed)
    
    total_earned = miner_income + benz_income
    
    return total_earned, hours_elapsed

def get_richest_users(count=10):
    """محاسبه و برگرداندن لیست تمام کاربران ثروتمند (کیف پول + پس‌انداز)."""
    richest = {}
    
    all_users = set(user_balances.keys()) | set(user_savings.keys())
    
    for user_id in all_users:
        total_wealth = user_balances.get(user_id, 0) + user_savings.get(user_id, 0)
        if total_wealth > 0:
            richest[user_id] = total_wealth
            
    sorted_richest = sorted(richest.items(), key=lambda item: item[1], reverse=True)
    
    # 🆕 افزودن نام کاربری/آیدی به خروجی
    result = []
    for user_id, wealth in sorted_richest:
        username = user_usernames.get(user_id, f"کاربر #{user_id}")
        result.append((user_id, username, wealth))
        
    return result

# 🆕 تابع جدید برای لیدربورد سهام بنز
def get_benz_share_holders(count=10):
    """محاسبه و برگرداندن لیست تمام کاربران سهامدار بنز."""
    share_holders = {}
    
    for user_id, shares in user_benz_shares.items():
        if shares > 0.0:
            share_holders[user_id] = shares
            
    sorted_holders = sorted(share_holders.items(), key=lambda item: item[1], reverse=True)
    
    # افزودن نام کاربری/آیدی به خروجی
    result = []
    for user_id, shares in sorted_holders:
        username = user_usernames.get(user_id, f"کاربر #{user_id}")
        result.append((user_id, username, shares))
        
    return result[:count]

# ==============================================================================
#           دستورات اصلی ربات
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پاسخ به دستور /start"""
    username = update.effective_user.username
    initialize_user_data(update.effective_user.id, username) # 🆕 ارسال نام کاربری
    save_data() # ذخیره تغییرات
    await update.message.reply_html(
        f"سلام {update.effective_user.mention_html()}! به ربات خوش آمدی. \nبرای دیدن دستورات، /help را بزن.",
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش لیست دستورات ربات."""
    help_text = (
        "لیست کامل دستورات بازی:\n"
        "--------------------------------------\n"
        "🔹 /start: استارت کردن ربات \n"
        
        "🔹 /help: نمایش همین راهنما \n"
        
        "🔹 /info: دیدن موجودی و وضعیت ماینر ها و سهام بنز (با ریپلای، اطلاعات دیگران را ببینید) \n"
        
        "🔹 /coin: دریافت سکه رایگان \n"
        
        "🔹 /bet: شرط بندی \n"
        
        "🔹 /pasandaz: انتقال سکه از کیف پول به بانک \n"
        
        "🔹 /bardasht: برداشت سکه از بانک \n"
        
        "🔹 /enteghal: انتقال سکه به کاربران \n"
        
        "🔹 /buyminer: خرید دستگاه ماینر \n"
        
        "🔹 /buybenz: خرید سهام کارخانه بنز \n"
        
        "🔹 /tf: برداشت سکه‌های استخراج شده توسط ماینرها و درآمد سهام بنز \n"
        
        "🔹 /richest: لیست ۱۰ کاربر ثروتمند برتر \n"
        
        "🔹 /benzrichest: لیست ۱۰ کاربر برتر سهامدار بنز \n"
    )
    await update.message.reply_text(help_text)

async def coin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دریافت سکه رایگان با کول‌داون ۱۰ دقیقه‌ای."""
    user_id = update.effective_user.id
    initialize_user_data(user_id, update.effective_user.username)
    now = datetime.now()
    
    last_time = user_cooldowns.get(user_id, now - timedelta(minutes=COIN_COOLDOWN_MINUTES + 1))
    time_since_last_coin = now - last_time
    
    if time_since_last_coin < timedelta(minutes=COIN_COOLDOWN_MINUTES):
        time_left = timedelta(minutes=COIN_COOLDOWN_MINUTES) - time_since_last_coin
        minutes = int(time_left.total_seconds() // 60)
        seconds = int(time_left.total_seconds() % 60)
        await update.message.reply_text(
            f"❌ صبر کنید! شما هر {COIN_COOLDOWN_MINUTES} دقیقه یکبار می‌توانید /coin بگیرید.\n"
            f"زمان باقی‌مانده: {minutes} دقیقه و {seconds} ثانیه."
        )
        return
        
    user_cooldowns[user_id] = now
    
    coins_gained = random.randint(1, 100000)
    user_balances[user_id] += coins_gained
    
    save_data()
    
    await update.message.reply_text(
        f"تبریک! شما {coins_gained:,} سکه دریافت کردید! 🎉\n"
        f"موجودی فعلی شما در کیف پول: {user_balances[user_id]:,} سکه است."
    )

async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شرط بندی ۵۰/۵۰ عادلانه با قابلیت 'all'."""
    user_id = update.effective_user.id
    initialize_user_data(user_id, update.effective_user.username)

    try:
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("لطفاً مقدار شرط را وارد کنید (مثال: /bet 10000) یا برای شرط‌بندی تمام موجودی، /bet all را بزنید.")
            return
            
        bet_input = context.args[0].lower()
        
        if bet_input == 'all':
            bet_amount = user_balances[user_id] 
        else:
            bet_amount = int(bet_input)
        
        if bet_amount <= 0:
            await update.message.reply_text("مقدار شرط باید مثبت باشد.")
            return

    except ValueError:
        await update.message.reply_text("مقدار شرط نامعتبر است. فقط عدد یا 'all' وارد کنید.")
        return

    if user_balances[user_id] < bet_amount:
        await update.message.reply_text(
            f"❌ موجودی کیف پول شما ({user_balances[user_id]:,}) کافی نیست."
        )
        return

    if random.choice([True, False]):
        user_balances[user_id] += bet_amount 
        msg = (f"👑 **برنده شدید!** 👑\n"
              f"مقدار برد: {bet_amount:,} سکه.\n"
              f"موجودی جدید شما در کیف پول: {user_balances[user_id]:,} سکه.")
    else:
        user_balances[user_id] -= bet_amount 
        msg = (f"💔 **متأسفانه باختید!** 💔\n"
              f"مقدار باخت: {bet_amount:,} سکه.\n"
              f"موجودی جدید شما در کیف پول: {user_balances[user_id]:,} سکه.")

    save_data()
    await update.message.reply_text(msg)

async def pasandaz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """انتقال سکه از کیف پول به بانک (/pasandaz)"""
    user_id = update.effective_user.id
    initialize_user_data(user_id, update.effective_user.username)

    try:
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("لطفاً مقدار سکه برای پس‌انداز را وارد کنید (مثال: /pasandaz 50000).")
            return
            
        save_amount = int(context.args[0])
        
        if save_amount <= 0:
            await update.message.reply_text("مقدار پس‌انداز باید مثبت باشد.")
            return

    except ValueError:
        await update.message.reply_text("مقدار نامعتبر است. فقط عدد وارد کنید.")
        return

    if user_balances[user_id] < save_amount:
        await update.message.reply_text(
            f"❌ موجودی کیف پول شما ({user_balances[user_id]:,}) کافی نیست."
        )
        return

    user_balances[user_id] -= save_amount
    user_savings[user_id] += save_amount
    
    save_data()
    
    await update.message.reply_text(
        f"✅ موفقیت!\n"
        f"مقدار {save_amount:,} سکه با موفقیت به بانک منتقل شد.\n"
        f"موجودی کیف پول: {user_balances[user_id]:,} سکه\n"
        f"موجودی بانک: {user_savings[user_id]:,} سکه"
    )

async def bardasht(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """برداشت سکه از بانک به کیف پول (/bardasht)"""
    user_id = update.effective_user.id
    initialize_user_data(user_id, update.effective_user.username)

    try:
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("لطفاً مقدار سکه برای برداشت را وارد کنید (مثال: /bardasht 10000).")
            return
            
        withdraw_amount = int(context.args[0])
        
        if withdraw_amount <= 0:
            await update.message.reply_text("مقدار برداشت باید مثبت باشد.")
            return

    except ValueError:
        await update.message.reply_text("مقدار نامعتبر است. فقط عدد وارد کنید.")
        return

    if user_savings[user_id] < withdraw_amount:
        await update.message.reply_text(
            f"❌ موجودی بانک شما ({user_savings[user_id]:,}) کافی نیست."
        )
        return

    user_savings[user_id] -= withdraw_amount
    user_balances[user_id] += withdraw_amount
    
    save_data()
    
    await update.message.reply_text(
        f"✅ موفقیت!\n"
        f"مقدار {withdraw_amount:,} سکه با موفقیت از بانک برداشت شد.\n"
        f"موجودی کیف پول: {user_balances[user_id]:,} سکه\n"
        f"موجودی بانک: {user_savings[user_id]:,} سکه"
    )

async def enteghal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """انتقال سکه با شماره کارت (/enteghal)"""
    sender_id = update.effective_user.id
    initialize_user_data(sender_id, update.effective_user.username)

    if len(context.args) != 2:
        await update.message.reply_text("❌ فرمت دستور اشتباه است. مثال صحیح: /enteghal 12345 10000")
        return

    try:
        receiver_card_number = int(context.args[0])
        transfer_amount = int(context.args[1])
        
        if len(str(receiver_card_number)) != 5:
            await update.message.reply_text("❌ شماره کارت باید دقیقاً ۵ رقمی باشد.")
            return

        if transfer_amount <= 0:
            await update.message.reply_text("مقدار انتقال باید مثبت باشد.")
            return

    except ValueError:
        await update.message.reply_text("❌ شماره کارت یا مقدار انتقال نامعتبر است.")
        return

    if user_balances[sender_id] < transfer_amount:
        await update.message.reply_text(
            f"❌ موجودی کیف پول شما ({user_balances[sender_id]:,}) برای انتقال کافی نیست."
        )
        return

    receiver_id = used_card_numbers.get(receiver_card_number)

    if receiver_id is None:
        await update.message.reply_text(f"❌ شماره کارت {receiver_card_number} پیدا نشد.")
        return
        
    if receiver_id == sender_id:
        await update.message.reply_text("❌ شما نمی‌توانید سکه را به حساب خودتان منتقل کنید.")
        return

    initialize_user_data(receiver_id)
    
    user_balances[sender_id] -= transfer_amount
    user_balances[receiver_id] += transfer_amount
    
    save_data()
    
    await update.message.reply_text(
        f"✅ انتقال موفقیت‌آمیز!\n"
        f"مقدار {transfer_amount:,} سکه به شماره کارت {receiver_card_number} منتقل شد.\n"
        f"موجودی جدید شما: {user_balances[sender_id]:,} سکه."
    )

async def buyminer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """خرید دستگاه ماینر"""
    user_id = update.effective_user.id
    initialize_user_data(user_id, update.effective_user.username)

    if user_balances[user_id] < MINER_PRICE:
        await update.message.reply_text(
            f"❌ موجودی کیف پول شما ({user_balances[user_id]:,}) برای خرید ماینر کافی نیست.\n"
            f"قیمت هر دستگاه: {MINER_PRICE:,} سکه."
        )
        return

    user_balances[user_id] -= MINER_PRICE
    user_miners[user_id] += 1
    
    # آخرین زمان برداشت در صورت صفر بودن ماینر و سهام
    if user_miners[user_id] == 1 and user_benz_shares.get(user_id, 0.0) == 0.0: 
        last_take_time[user_id] = datetime.now() 

    save_data()
    
    await update.message.reply_text(
        f"✅ یک دستگاه ماینر با موفقیت خریداری شد! ⛏️\n"
        f"تعداد ماینرهای شما: {user_miners[user_id]} دستگاه.\n"
        f"موجودی جدید کیف پول: {user_balances[user_id]:,} سکه."
    )

async def buybenz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """خرید سهام کارخانه مرسدس بنز بر اساس درصد."""
    user_id = update.effective_user.id
    initialize_user_data(user_id, update.effective_user.username)

    try:
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(f"لطفاً مقدار درصد سهام برای خرید را وارد کنید (مثال: /buybenz 1.5).\n"
                                             f"قیمت هر ۱٪ سهام: {BENZ_PRICE_PER_PERCENT:,} سکه.")
            return
            
        share_percent = float(context.args[0])
        
        if share_percent <= 0:
            await update.message.reply_text("درصد سهام باید مثبت باشد.")
            return
            
        if user_benz_shares[user_id] + share_percent > 100.0:
            # اگر با خرید جدید از ۱۰۰ درصد عبور کند، مقدار خرید را محدود می‌کنیم
            share_percent = round(100.0 - user_benz_shares[user_id], 2)
            if share_percent <= 0:
                 await update.message.reply_text("شما قبلاً ۱۰۰ درصد سهام را خریده‌اید.")
                 return

        cost = int(share_percent * BENZ_PRICE_PER_PERCENT)
        
    except ValueError:
        await update.message.reply_text("❌ مقدار درصد نامعتبر است. فقط عدد وارد کنید (مثال: 0.5 یا 10).")
        return

    if user_balances[user_id] < cost:
        await update.message.reply_text(
            f"❌ موجودی کیف پول شما ({user_balances[user_id]:,}) برای خرید سهام به ارزش {cost:,} سکه کافی نیست."
        )
        return

    user_balances[user_id] -= cost
    user_benz_shares[user_id] = round(user_benz_shares[user_id] + share_percent, 2)
    
    # اگر اولین خرید سرمایه‌گذاری باشد (ماینر هم صفر باشد)
    if user_benz_shares[user_id] == share_percent and user_miners.get(user_id, 0) == 0:
        last_take_time[user_id] = datetime.now()

    save_data()
    
    await update.message.reply_text(
        f"✅ **{share_percent}%** سهام مرسدس بنز با موفقیت خریداری شد!\n"
        f"سهام کل شما: {user_benz_shares[user_id]}%.\n"
        f"درآمد ساعتی شما از این سهام: {int(user_benz_shares[user_id] * BENZ_HOURLY_INCOME_PER_PERCENT):,} سکه.\n"
        f"موجودی جدید کیف پول: {user_balances[user_id]:,} سکه."
    )

async def tf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """برداشت سکه‌های استخراج شده (ماینر) و درآمد سهام (بنز) - /tf"""
    user_id = update.effective_user.id
    initialize_user_data(user_id, update.effective_user.username)
    
    miners_count = user_miners.get(user_id, 0)
    shares_count = user_benz_shares.get(user_id, 0.0)
    
    if miners_count == 0 and shares_count == 0:
        await update.message.reply_text("❌ شما هیچ منبع درآمدی (ماینر یا سهام بنز) برای برداشت ندارید. با /buyminer یا /buybenz خرید کنید.")
        return

    earned_coins, hours_elapsed = calculate_total_income(user_id)
    
    if earned_coins == 0:
        await update.message.reply_text("منابع درآمدی شما هنوز سکه‌ای کسب نکرده‌اند.")
        return

    user_balances[user_id] += earned_coins
    last_take_time[user_id] = datetime.now()
    
    save_data()
    
    await update.message.reply_text(
        f"💰 **برداشت موفق!**\n"
        f"مقدار {earned_coins:,} سکه از ماینرها و سهام شما برداشت شد.\n"
        f"موجودی کیف پول: {user_balances[user_id]:,} سکه."
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش موجودی کیف پول، بانک، وضعیت ماینرها، سهام بنز و شماره کارت.
    قابلیت ریپلای برای مشاهده info/ دیگران."""
    
    # 🆕 تعیین کاربری که اطلاعاتش درخواست شده
    target_user_id = update.effective_user.id
    target_username = update.effective_user.username
    
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_username = update.message.reply_to_message.from_user.username
        
    initialize_user_data(target_user_id, target_username) # اطمینان از مقداردهی اولیه

    # 🆕 بررسی اینکه آیا کاربر هدف در دیتابیس وجود دارد یا خیر
    if target_user_id not in user_balances:
        await update.message.reply_text(f"❌ کاربر مورد نظر (ID: {target_user_id}) هنوز در ربات ثبت‌نام نکرده است.")
        return
        
    # اطلاعات کاربر هدف
    target_user = update.effective_user if target_user_id == update.effective_user.id else update.message.reply_to_message.from_user
    
    user_card_number = next((card for card, uid in used_card_numbers.items() if uid == target_user_id), "یافت نشد")
    
    total_earned, hours_elapsed = calculate_total_income(target_user_id)
    
    # ------------------ ماینرها ------------------
    miners_count = user_miners.get(target_user_id, 0)
    miner_status = f"ندارد ❌"
    if miners_count > 0:
        miner_status = f"{miners_count} دستگاه (درآمد ساعتی: {miners_count * MINER_HOURLY_INCOME:,} سکه)"
        
    # ------------------ سهام بنز ------------------
    shares_percent = user_benz_shares.get(target_user_id, 0.0)
    benz_status = f"ندارد ❌"
    if shares_percent > 0.0:
        benz_hourly_income = int(shares_percent * BENZ_HOURLY_INCOME_PER_PERCENT)
        benz_status = f"{shares_percent}% (درآمد ساعتی: {benz_hourly_income:,} سکه)"

    # 🆕 عنوان پیام بر اساس اینکه اطلاعات خود کاربر یا دیگری درخواست شده است
    if target_user_id == update.effective_user.id:
        title = "📊 **اطلاعات موجودی شما**"
    else:
        title = f"🔍 **اطلاعات موجودی کاربر {target_user.mention_html()}**"

    info_text = (
        f"{title}\n"
        "--------------------------------------\n"
        f"💳 **شماره کارت (برای دریافت پول):** {user_card_number}\n"
        f"💼 **موجودی کیف پول (در دسترس):** {user_balances[target_user_id]:,} سکه\n"
        f"🏦 **موجودی بانک (پس‌انداز):** {user_savings[target_user_id]:,} سکه\n"
        "--------------------------------------\n"
        f"⛏️ **وضعیت ماینر:** {miner_status}\n"
        f"🏭 **سهام کارخانه مرسدس بنز:** {benz_status}\n"
        "--------------------------------------\n"
        f"💰 **درآمد در انتظار برداشت:** {total_earned:,} سکه\n"
        f"(برای برداشت از ماینرها و سهام، /tf را بزنید)"
    )
    await update.message.reply_html(info_text)

async def richest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش ۱۰ کاربر ثروتمند برتر همراه با رتبه شخصی."""
    
    user_id = update.effective_user.id
    all_richest_list = get_richest_users()
    top_10 = all_richest_list[:10]
    
    if not all_richest_list:
        await update.message.reply_text("هنوز هیچ کاربری دارایی قابل توجهی ندارد.")
        return

    message = "👑 <b>۱۰ کاربر ثروتمند برتر</b> 👑\n"
    message += "--------------------------------------\n"
    
    for index, (uid, username, wealth) in enumerate(top_10, 1):
        # ساخت لینک قابل کلیک با استفاده از تگ HTML
        # 🆕 استفاده از نام کاربری اگر موجود باشد
        display_name = f"@{username}" if username else f"کاربر #{uid}"
        user_link = f"<a href='tg://user?id={uid}'>{display_name}</a>"
        
        message += f"{index}. {user_link}\n"
        message += f"   - مجموع دارایی: <b>{wealth:,}</b> سکه\n"
        
    message += "--------------------------------------\n"
    
    # 🆕 جستجوی رتبه و ثروت کاربر فعلی
    my_rank = -1
    my_wealth = user_balances.get(user_id, 0) + user_savings.get(user_id, 0)
    for index, (uid, _, wealth) in enumerate(all_richest_list, 1):
        if uid == user_id:
            my_rank = index
            break
            
    if my_rank != -1:
        message += f"👤 **رتبه شما:** #{my_rank}\n"
        message += f"💰 **مجموع دارایی شما:** {my_wealth:,} سکه"
    else:
        message += "👤 شما هنوز در لیست رتبه‌بندی قرار ندارید (دارایی صفر یا کم)."
        
    await update.message.reply_html(message)


# 🆕 دستور جدید: لیدربورد سهام بنز
async def benzrichest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش ۱۰ کاربر برتر سهامدار کارخانه بنز."""
    
    share_holders_list = get_benz_share_holders()
    
    if not share_holders_list:
        await update.message.reply_text("هنوز هیچ کاربری سهام قابل توجهی در کارخانه بنز ندارد.")
        return

    message = "🏭 <b>۱۰ سهامدار برتر کارخانه بنز</b> 💰\n"
    message += "--------------------------------------\n"
    
    for index, (uid, username, shares) in enumerate(share_holders_list, 1):
        # ساخت لینک قابل کلیک با استفاده از تگ HTML
        display_name = f"@{username}" if username else f"کاربر #{uid}"
        user_link = f"<a href='tg://user?id={uid}'>{display_name}</a>"
        
        message += f"{index}. {user_link}\n"
        message += f"   - میزان سهام: <b>{shares}%</b>\n"
        
    message += "--------------------------------------\n"
    message += "برای مشاهده وضعیت خود، /info را بزنید."
        
    await update.message.reply_html(message)


async def get_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور /get برای ادمین (صاحب ربات)"""
    user_id = update.effective_user.id
    
    if user_id == ADMIN_USER_ID:
        initialize_user_data(user_id, update.effective_user.username)
        reward = 100000000 # 100 میلیون
        user_balances[user_id] += reward
        
        save_data()
        
        await update.message.reply_text(
            f"👑 ادمین عزیز، مقدار {reward:,} سکه به کیف پول شما اضافه شد.\n"
            f"موجودی جدید: {user_balances[user_id]:,} سکه."
        )
    else:
        await update.message.reply_text("❌ این دستور فقط برای صاحب ربات قابل استفاده است.")

# ==============================================================================
#           اجرای اصلی
# ==============================================================================

def main() -> None:
    """تابع اصلی برای اجرای ربات."""
    application = Application.builder().token(TOKEN).build()

    # 🔴 بارگذاری داده‌های قبلی در ابتدای اجرای ربات
    load_data() 

    # ثبت دستورات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("coin", coin)) 
    application.add_handler(CommandHandler("bet", bet)) 
    application.add_handler(CommandHandler("info", info)) 
    application.add_handler(CommandHandler("pasandaz", pasandaz)) 
    application.add_handler(CommandHandler("bardasht", bardasht)) 
    application.add_handler(CommandHandler("enteghal", enteghal)) 
    application.add_handler(CommandHandler("buyminer", buyminer))
    application.add_handler(CommandHandler("buybenz", buybenz))
    application.add_handler(CommandHandler("tf", tf))
    application.add_handler(CommandHandler("richest", richest))
    application.add_handler(CommandHandler("benzrichest", benzrichest)) # 🆕 لیدربورد بنز
    application.add_handler(CommandHandler("get", get_admin)) 
    
    print("ربات بازی با قابلیت حفظ اطلاعات در حال اجرا است...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    
if __name__ == "__main__":
    main()
