import asyncio
import time
import dns.resolver
import nest_asyncio
import random
import threading
import json
import os
from datetime import datetime
import pytz

# โหลดข้อมูลยอดซื้อจากไฟล์
if os.path.exists("meta.json"):
    with open("meta.json", "r") as f:
        user_meta = json.load(f)
else:
    user_meta = {}

# โหลด stock จากไฟล์ stock.json
with open("stock.json", "r", encoding="utf-8") as f:
    stock = json.load(f)

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, filters
)
from keep_alive import keep_alive

import os
from telegram import Bot

TOKEN = os.getenv("BOT_TOKEN")  # ดึง token จาก environment variable

if TOKEN is None:
    print("❌ BOT_TOKEN ยังไม่ถูกตั้งค่าใน environment variables")
else:
    bot = Bot(token=TOKEN)
    bot.delete_webhook()
    print("✅ ล้าง webhook เรียบร้อยแล้ว")

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# 📦 สินค้า

# 🎰 ระบบสุ่ม (Gacha)
gacha_stock = {
    "Mochi Kisaki": {"chance": 15},
    "💼Secret Archive Drop💼": {"chance": 5},
    "Mochi Shimakaze": {"chance": 15},
    "Mochi White Bikini": {"chance": 120},
    "Mochi Laplus": {"chance": 20},
    "Rainxang SpiderGirl": {"chance": 10},
    "Mochi Red&Blue": {"chance": 50},
    "Byzeko Christmas": {"chance": 30},
    "Mochi Strawberry Bikini": {"chance": 25},
}

approved_users = set()
denied_users = set()

pending_orders = {}
user_gmails = {}
if os.path.exists("meta.json"):
    with open("meta.json", "r") as f:
        user_meta = json.load(f)
else:
    user_meta = {}
user_states = {}  # เก็บสถานะคำสั่งของผู้ใช้แต่ละคน

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("🏠 เริ่มใช้งาน /start"), KeyboardButton("👤 โปรไฟล์ของฉัน")],
        [KeyboardButton("🎰 สุ่มสินค้า (20฿)"), KeyboardButton("🛍 สินค้า")],
        [KeyboardButton("📖 วิธีสั่งซื้อ"), KeyboardButton("🗂 หมวดหมู่สินค้า")],
        [KeyboardButton("💬 ติดต่อแอดมิน"), KeyboardButton("🔄 รีเมนู")]
    ],
    resize_keyboard=True
)

meta_lock = threading.Lock()

from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

def generate_receipt(user_id, gmail, item, price):
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()

    # ใช้เวลาไทย
    bangkok = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bangkok).strftime("%Y-%m-%d %H:%M")

    receipt_id = f"SS-{user_id}-{int(time.time())}"

    lines = [
        "Secret_Shop Receipt",
        f"Date: {now}",
        f"Order: {receipt_id}",
        f"Telegram ID: {user_id}",
        f"Gmail: {gmail}",
        f"Item: {item}",
        f"Price: {price} Bath",
        "Thank You For Buying"
    ]

    y = 20
    for line in lines:
        draw.text((30, y), line, font=font, fill=(0, 0, 0))
        y += 35

    path = f"receipt_{user_id}.png"
    img.save(path)
    return path

def save_user_meta():
    import os
    print("📁 meta.json path:", os.path.abspath("meta.json"))
    
    print("🧠 เรียก save_user_meta()")  # <--- เพิ่มบรรทัดนี้

    current_meta = {}
    if os.path.exists("meta.json"):
        try:
            with open("meta.json", "r") as f:
                current_meta = json.load(f)
        except Exception:
            print("❌ อ่าน meta.json ไม่ได้")  # เพิ่มตรงนี้ด้วย

    # รวมค่าใหม่เข้าไป
    for uid, new_data in user_meta.items():
        old_data = current_meta.get(str(uid), {})
        if "new_spent" in new_data:
            old_data["total_spent"] = old_data.get("total_spent", 0) + new_data["new_spent"]
        if "new_gacha" in new_data:
            old_data["gacha_count"] = old_data.get("gacha_count", 0) + new_data["new_gacha"]
        for k, v in new_data.items():
            if k in ["new_spent", "new_gacha"]:
                continue
            old_data[k] = v
        current_meta[str(uid)] = old_data

    try:
        with open("meta.json", "w") as f:
            json.dump(current_meta, f, indent=2)
        print("✅ meta.json อัปเดตแล้ว")  # <--- บรรทัดนี้สำคัญ
    except Exception as e:
        print(f"❌ เขียน meta.json ไม่ได้: {e}")

    # อัปเดตในตัวแปร
    user_meta.clear()
    user_meta.update(current_meta)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎉*ยินดีต้อนรับสู่ Secret_Shop!*\n\n"
        "🛍 ร้านขายรูปภาพและวิดีโอสุดพิเศษ\n"
        "📦 ส่งไฟล์ผ่าน Google Drive\n\n"
        "🧾 *เริ่มต้นใช้งาน:*\n"
        "1️⃣ พิมพ์ /menu หรือกดปุ่ม 'สินค้า'\n"
        "2️⃣ ดูรายละเอียดและทำตามขั้นตอน\n"
        "3️⃣ ส่ง Gmail และสลิปชำระเงิน\n\n"
        "📲 *พร้อมเพย์:* 086-346-9001\n"
        "\n ระบบสุ่มมีโอกาสออก 100% เรทจะขึ้นอยู่กับราคาสินค้า\n"
        "\n💬 'ติดต่อแอดมิน' ด้านล่าง",
        parse_mode="Markdown",
        reply_markup=main_menu
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 คำสั่งที่ใช้ได้:\n"
        "/start - เริ่มต้นใหม่\n"
        "/menu - แสดงสินค้า\n"
        "/howto - วิธีสั่งซื้อ\n"
        "/help - ช่วยเหลือ"
    )

async def howto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_photo(
        photo="https://i.postimg.cc/L6z2ywLc/qr-code.jpg",
        caption=(
            "🛒 วิธีสั่งซื้อ:\n"
            "1️⃣ พิมพ์ /menu แล้วเลือกสินค้า\n"
            "2️⃣ โอนเงินตามยอด → สแกน QR ด้านบน หรือโอนผ่าน PromptPay: 086-346-9001\n"
            "3️⃣ พิมพ์ Gmail ของคุณในแชทนี้\n"
            "4️⃣ ส่งภาพสลิป\n"
            "5️⃣ รอแอดมินตรวจสอบ"
        )
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_stock = dict(sorted(stock.items(), key=lambda x: x[1]["price"]))

    buttons = [[InlineKeyboardButton("🎰 สุ่มสินค้า (20฿)", callback_data="gacha")]] + \
              [[InlineKeyboardButton(f"{name} - {data['price']}฿", callback_data=f"select_{name}")]
               for name, data in sorted_stock.items()]

    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("🛍 เลือกสินค้าที่คุณสนใจ:", reply_markup=markup)
    await update.message.reply_text("📲 เลือกเมนูเพิ่มเติม:", reply_markup=main_menu)

async     def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # รวมหมวดหมู่ทั้งหมด พร้อมนับจำนวน
    from collections import defaultdict

    category_counts = defaultdict(int)
    for item in stock.values():
        cat = item.get("category", "อื่นๆ")
        category_counts[cat] += 1

    # สร้างปุ่ม    สำหรับแต่ละหมวด
    buttons = [
        [InlineKeyboardButton(f"{cat}", callback_data=f"category_{cat}")]
        for cat in category_counts
    ]

    # ข้อความแสดงรายการหมวดหมู่ + จำนวน
    text = "🗂 หมวดหมู่สินค้า:\n\n"
    icon_map = {
        "Mochi": "🐰",
        "Byzeko": "🎄",
        "Rainxang": "🕷"
    }

    for cat, count in category_counts.items():
        icon = icon_map.get(cat, "📁")
        text += f"{icon} {cat} ({count})\n"

    text += "\nกรุณาเลือกหมวดที่ต้องการ:"

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    user_data = user_states.setdefault(user_id, {})

    if data == "cancel":
        # 🔄 ล้างสถานะคำสั่ง
        user_data.pop("pending_item", None)
        user_data.pop("pending_price", None)

        # ✅ ลบข้อความทั้งหมดที่จำไว้
        for msg_id in user_data.get("message_ids", []):
            try:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_id)
            except Exception as e:
                print(f"❌ ลบข้อความ {msg_id} ไม่สำเร็จ: {e}")

        # ลบ message_ids หลังลบแล้ว
        user_data.pop("message_ids", None)

        # ✅ แจ้งผู้ใช้
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ ยกเลิกคำสั่งเรียบร้อยแล้ว คุณสามารถเริ่มใหม่ได้",
            reply_markup=main_menu
        )
        return


    if data.startswith("select_"):
        if user_data.get("pending_item"):
            await query.message.reply_photo(photo="https://i.postimg.cc/L6z2ywLc/qr-code.jpg")
            await query.message.reply_text(
                "⚠️ คุณมีคำสั่งที่ยังไม่เสร็จ\n"
                "กรุณากดยกเลิกคำสั่งก่อน โดยพิมพ์ /cancel หรือกดปุ่ม ❌"
            )
            return
            
        item = data.replace("select_", "")
        user_data["pending_item"] = item
        user_data["pending_price"] = stock[item]["price"]

        confirm_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ พิมพ์ Gmail แล้ว", callback_data="confirm_gmail")],
            [InlineKeyboardButton("❌ ยกเลิกคำสั่ง", callback_data="cancel")]
        ])

        msg1 = await query.message.reply_photo(
            photo=stock[item]["image"],
            caption=(
                f"📌 สินค้าที่เลือก: {item}\n"
                f"💰 ราคา: {stock[item]['price']} บาท\n"
                f"📝 รายละเอียด: {stock[item]['detail']}\n\n"
                "📲 พร้อมเพย์: 0863469001\n"
                "📤 ส่ง Gmail และสลิปมาที่แชทนี้ได้เลย\n"
                "✅ หากเรียบร้อย ระบบจะส่งลิงก์ให้โดยอัตโนมัติ\n"
            ),
            reply_markup=confirm_button
        )

    # ✅ แสดง QR ทุกครั้งที่กดซื้อ
        msg2 = await query.message.reply_photo(
            photo="https://i.postimg.cc/L6z2ywLc/qr-code.jpg",
            caption="📲 สแกน QR นี้เพื่อชำระเงิน"
    )

        user_data["message_ids"] = [msg1.message_id, msg2.message_id]

    elif data == "gacha":
        await gacha_start(update, context)
        return
        
    elif data.startswith("category_"):
        cat = data.replace("category_", "")
        items = {k: v for k, v in stock.items() if v["category"] == cat}

        if not items:
            await query.message.reply_text("❌ ไม่พบสินค้าในหมวดนี้")
            return

        for name, item in items.items():
            # ✅ สร้างปุ่ม "📥 สั่งซื้อ" ให้กดแล้วเรียก callback ไปสั่งซื้อ
            buy_button = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 สั่งซื้อ", callback_data=f"select_{name}")]
            ])

            # ✅ ส่งภาพสินค้า + รายละเอียด + ปุ่ม
            await query.message.reply_photo(
                photo=item["image"],
                caption=(
                    f"📦 ชื่อสินค้า: {name}\n"
                    f"💰 ราคา: {item['price']} บาท\n"
                    f"📝 {item['detail']}\n\n"
                    f"📥 กดปุ่มด้านล่างเพื่อสั่งซื้อ"
                ),
                reply_markup=buy_button
            )    

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id

    if "@" in text and text.endswith(".com"):
        user_gmails[str(user_id)] = text
        await update.message.reply_text("✅ ได้รับ Gmail แล้ว กรุณาส่งสลิปได้เลย")
    elif text == "🛍 สินค้า":
        await menu(update, context)
    elif text == "🔄 รีเมนู":
        await update.message.reply_text("📲 เมนูอัปเดตแล้ว ✅", reply_markup=main_menu)
    elif text == "📖 วิธีสั่งซื้อ":
        await howto(update, context)
    elif text == "🗂 หมวดหมู่สินค้า":
        await show_categories(update, context)
    elif text == "👤 โปรไฟล์ของฉัน":
        await profile(update, context)
    elif text == "💬 ติดต่อแอดมิน":
        await update.message.reply_text("📩 ติดต่อแอดมิน: @ShiroiKJP")
    elif text == "🎰 สุ่มสินค้า (20฿)":
        await gacha_start(update, context)
    elif text == "🏠 เริ่มใช้งาน /start":
        await start(update, context)
    else:
            await update.message.reply_text("❌ ไม่พบสินค้าที่ตรงกับคำค้นของคุณ")

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.from_user.id
        user_id = update.message.from_user.id
        if user_states.get(user_id, {}).get("pending_item"):
            user_states[user_id].pop("pending_item", None)
            user_states[user_id].pop("pending_price", None)
            await update.message.reply_text("❌ ยกเลิกคำสั่งเรียบร้อยแล้ว คุณสามารถเริ่มใหม่ได้")
        else:
            await update.message.reply_text("ℹ️ คุณไม่มีคำสั่งที่ต้องยกเลิก")


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ดึง ID ผู้ใช้
    user_id = str(update.message.from_user.id)

    # ดึงข้อมูลจาก user_meta (ถ้ายังไม่มี ให้เป็น dict ว่าง)
    data = user_meta.get(user_id, {})

    # ดึง Gmail ล่าสุดจาก user_gmails (ถ้ายังไม่มีให้แสดงว่า "ยังไม่มี")
    gmail = user_gmails.get(user_id, "ยังไม่มี")

    # ดึงยอดใช้จ่าย และจำนวนสุ่มจากข้อมูลใน user_meta
    total_spent = data.get("total_spent", 0)
    gacha_count = data.get("gacha_count", 0)

    # สร้างข้อความที่จะแสดง
    text = (
        "👤 โปรไฟล์ของคุณ:\n\n"
        f"🆔 Telegram ID: {user_id}\n"
        f"📧 Gmail ล่าสุด: {gmail}\n"
        f"💰 ยอดใช้จ่ายล่าสุด: {total_spent} บาท\n"
        f"🎰 สุ่มล่าสุด: {gacha_count} ครั้ง"
    )

    # ส่งข้อความกลับไปให้ผู้ใช้
    await update.message.reply_text(text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_id = update.message.from_user.id
    user_data = user_states.get(user_id, {})
    if "pending_item" not in user_data:
        await update.message.reply_text("⚠️ กรุณาเลือกสินค้าก่อน โดยพิมพ์ /menu")
        return

    item = user_data["pending_item"]
    price = user_data["pending_price"]

    photo_id = update.message.photo[-1].file_id
    gmail = user_gmails[str(user_id)]

    pending_orders[user_id] = {
        "item": item,
        "photo_id": photo_id,
        "gmail": gmail,
        "price": price
    }

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=(
            f"🧾 ออเดอร์ใหม่จาก {user_id}\n"
            f"สินค้า: {item}\n"
            f"Gmail: {gmail}\n"
            f"ยอด: {price} บาท\n\n"
            f"/approve_{user_id} ✅ | /deny_{user_id} ❌"
        )
    )
    await update.message.reply_text("📨 ส่งสลิปแล้ว กรุณารอแอดมินตรวจสอบ")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(update.message.text.split("_")[1])
        user_id_str = str(user_id)

        # ✅ เช็กว่า user มีออเดอร์ใน pending หรือไม่
        if user_id not in pending_orders:
            await update.message.reply_text(
                f"⚠️ ไม่มีออเดอร์ที่รออนุมัติจาก {user_id} หรืออาจอนุมัติไปแล้ว"
            )
            return

        order = pending_orders[user_id]

        # --- จุดที่เพิ่มข้อความพิเศษสำหรับ Secret Archive Drop ---
        if order['item'] == "💼Secret Archive Drop💼":
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🎉 คุณสุ่มได้แฟ้มลับ!\n"
                    "📤 โปรดส่ง Gmail และสลิปที่แชทนี้\n"
                    "🕵️‍♂️ จากนั้นแคปรูปนี้แล้วติดต่อแอดมิน @ShiroiKJP เพื่อขอลิงก์ลับ\n\n"
                    "✅ แอดมินจะส่งลิงก์ให้โดยตรง"
                )
            )

        # ส่งข้อความยืนยันการชำระเงินตามปกติ
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ ยืนยันการชำระเงิน\n"
                f"📧 Gmail: {order['gmail']}\n"
                f"🔗 ลิงก์สินค้า: {stock[order['item']]['url']}\n"
                f"🎉 คุณสุ่มได้: {order['item']}" if order['price'] == 20 else
                f"✅ ยืนยันการชำระเงิน\n📧 Gmail: {order['gmail']}\n🔗 ลิงก์สินค้า: {stock[order['item']]['url']}"
            )
        )

        # ✅ สร้างใบเสร็จ
        receipt_path = generate_receipt(
            user_id=user_id,
            gmail=order["gmail"],
            item=order["item"],
            price=order["price"]
        )

        try:
            with open(receipt_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption="🧾 ใบเสร็จของคุณ (เก็บไว้เป็นหลักฐานนะครับ)"
                )
            os.remove(receipt_path)
        except Exception as e:
            print(f"❌ ส่งใบเสร็จล้มเหลว: {e}")

        # ✅ อัปเดต meta.json
        try:
            if os.path.exists("meta.json"):
                with open("meta.json", "r") as f:
                    current_meta = json.load(f)
            else:
                current_meta = {}

            user_data = current_meta.get(user_id_str, {})
            user_data["total_spent"] = user_data.get("total_spent", 0) + order["price"]
            if order["price"] == 20:
                user_data["gacha_count"] = user_data.get("gacha_count", 0) + 1
            current_meta[user_id_str] = user_data

            with open("meta.json", "w") as f:
                json.dump(current_meta, f, indent=2)
            print("✅ เขียน meta.json สำเร็จ")
        except Exception as e:
            print(f"❌ เขียน meta.json ล้มเหลว: {e}")

        await update.message.reply_text(
            f"✅ ส่งลิงก์ให้ {user_id} แล้ว (สุ่มได้: {order['item']})" if order['price'] == 20 else
            f"✅ ส่งลิงก์ให้ {user_id} แล้ว"
        )

        del pending_orders[user_id]

        if user_id in user_states:
            user_states[user_id].pop("pending_item", None)
            user_states[user_id].pop("pending_price", None)

    except Exception as e:
        await update.message.reply_text(f"❌ เกิดข้อผิดพลาด: {e}")

async def deny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(update.message.text.split("_")[1])

        # ✅ เช็กว่ามีออเดอร์อยู่หรือไม่
        if user_id not in pending_orders:
            await update.message.reply_text(
                f"⚠️ ไม่มีออเดอร์ที่รอพิจารณาสำหรับ {user_id}"
            )
            return

        # ❌ แจ้งลูกค้า
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ การชำระเงินไม่ตรงยอด\n⛔ ร้านขอสงวนสิทธิ์ไม่คืนเงินที่โอนเล่น"
        )
        await update.message.reply_text(f"❌ ปฏิเสธออเดอร์ {user_id} แล้ว")

        # 🔄 ลบข้อมูลที่เกี่ยวข้อง
        del pending_orders[user_id]
        if user_id in user_states:
            user_states[user_id].pop("pending_item", None)
            user_states[user_id].pop("pending_price", None)

    except Exception as e:
        await update.message.reply_text(f"❌ เกิดข้อผิดพลาด: {e}")

async def gacha_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_data = user_states.setdefault(user_id, {})

        if user_data.get("pending_item"):
            await update.effective_message.reply_text(
                "⚠️ คุณมีคำสั่งที่ยังไม่เสร็จ กรุณากดยกเลิกคำสั่งก่อน โดยพิมพ์ /cancel หรือกดปุ่ม ❌"
            )
            return

        # 🎰 สุ่มสินค้า
        item_list = list(gacha_stock.keys())
        weight_list = [gacha_stock[k]["chance"] for k in item_list]
        item = random.choices(population=item_list, weights=weight_list, k=1)[0]

        user_data["pending_item"] = item
        user_data["pending_price"] = 20

        uid_str = str(user_id)
        if uid_str not in user_meta:
            user_meta[uid_str] = {}
        user_meta[uid_str]["new_gacha"] = user_meta[uid_str].get("new_gacha", 0) + 1
        save_user_meta()  # บันทึกลงไฟล์ทันที

        cancel_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ ยกเลิกคำสั่ง", callback_data="cancel")]
        ])

        # ✅ ส่งภาพสุ่ม
        msg1 = await update.effective_message.reply_photo(
            photo="https://i.postimg.cc/3JrJJDrm/image.jpg",
            caption=(
                "🎰 ระบบสุ่มสินค้า (20฿)\n\n"
                "📌 โปรดโอนเงิน 20 บาท ไปยัง PromptPay\n"
                "`0863469001`\n\n"
                "📤 ส่ง Gmail และสลิปมาที่แชทนี้ได้เลย\n"
                "✅ หากเรียบร้อย ระบบจะส่งลิงก์ให้โดยอัตโนมัติ"
            ),
            parse_mode="Markdown",
            reply_markup=cancel_button
        )

        # ✅ ส่ง QR
        msg2 = await update.effective_message.reply_photo(
            photo="https://i.postimg.cc/L6z2ywLc/qr-code.jpg",
            caption="📲 สแกน QR เพื่อโอนเงิน"
        )

        user_data["message_ids"] = [msg1.message_id, msg2.message_id]

        # 📦 ถ้าสุ่มได้ Secret Drop
        if item == "💼Secret Archive Drop💼":
            await update.effective_message.reply_photo(
                photo="https://i.postimg.cc/tCZ2hxVT/download.jpg",
                caption=(
                    f"🎁 คุณสุ่มได้: *{item}*\n\n"
                    "📌 คุณคือ 1 ในไม่กี่คนที่โชคดีได้แฟ้มลับ!\n"
                    "📤 ส่ง Gmail และสลิปมาที่แชทนี้\n"
                    "🕵️‍♂️ จากนั้นโปรดแคปรูปนี้แล้วติดต่อแอดมิน @ShiroiKJP เพื่อขอลิงก์ลับ\n\n"
                    "✅ แอดมินจะส่งลิงก์ให้โดยตรง"
                ),
                parse_mode="Markdown",
                reply_markup=cancel_button
            )

# แจ้งแอดมิน
            await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📥 แจ้งเตือน!\n"
                f"ผู้ใช้ @{update.effective_user.username or 'ไม่มี username'} (ID: {user_id})\n"
                f"สุ่มได้ *Secret Archive Drop* 🎁\n"
                f"กรุณาตรวจสอบและส่งลิงก์ลับให้โดยตรง"
            ),
            parse_mode="Markdown"
        )
            return  # จบการทำงานตรงนี้ ไม่ต้องแสดงข้อความสุ่มปกติ

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("me", profile))
    app.add_handler(CommandHandler("categories", show_categories))
    app.add_handler(CommandHandler("cancel", handle_cancel))
    app.add_handler(CommandHandler("howto", howto))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    app.add_handler(MessageHandler(filters.Regex(r"^/approve_\d+$"), approve))
    app.add_handler(MessageHandler(filters.Regex(r"^/deny_\d+$"), deny))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    keep_alive()
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']

    loop = asyncio.get_event_loop()
    while True:
        try:
            loop.run_until_complete(main())
        except Exception as e:
            print(f"❗ Bot crashed: {e}, restarting in 5s...")
            time.sleep(5)
