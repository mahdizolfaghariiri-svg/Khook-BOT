import json
import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------- تنظیمات (از متغیر محیطی) ----------
TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", "8000"))
DATA_FILE = "game_data.json"

ROLES_FA = {
    "killer": "قاتل",
    "accomplice": "همدست",
    "detective": "کارآگاه",
    "doctor": "دکتر",
    "citizen": "شهروند",
}
MAFIA_ROLES = {"killer", "accomplice"}


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"group_id": None, "join_password": "", "players": {}, "votes": {}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


data = load_data()


def is_admin(user_id):
    return ADMIN_ID and user_id == ADMIN_ID


def get_player(user_id):
    return data["players"].get(str(user_id))


def player_label(p):
    return f"پلیر {p['number']}"


async def send_to_group(context, text):
    if not data.get("group_id"):
        return False
    try:
        await context.bot.send_message(chat_id=data["group_id"], text=text)
        return True
    except Exception as e:
        logger.error(f"group send error: {e}")
        return False


# ---------- سرور سلامتی (تا Render و UptimeRobot بات را زنده نگه دارند) ----------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")
        self.wfile.flush()

    def log_message(self, *args):
        pass


def start_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info(f"HTTP health server started on port {PORT}")
    server.serve_forever()


# ---------- دستورهای عمومی ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐷 به بات بازی «پروندهٔ خوک» خوش آمدی!\n\n"
        "این بات ناشناس است؛ هویت تو هیچ‌جا نمایش داده نمی‌شود.\n\n"
        "دستورها:\n"
        "/join <شماره> <رمز> — ثبت‌نام با شماره پلیر\n"
        "/role — مشاهده نقش\n"
        "/vote <شماره> — رأی‌گیری\n"
        "/myvote — رأی فعلی تو\n"
        "/mafia <متن> — پیام مخفی مافیا (فقط تیم سرخ)\n\n"
        "هر پیام یا عکسی که مستقیم به بات بفرستی، با شماره‌ات در گروه منتشر می‌شود."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐷 راهنمای بات:\n\n"
        "بازیکن‌ها:\n"
        "/join <شماره> <رمز> — ثبت‌نام\n"
        "/role — نقش تو\n"
        "/vote <شماره> — رأی‌گیری\n"
        "/myvote — رأی فعلی\n"
        "/mafia <متن> — پیام مخفی مافیا\n"
        "ارسال هر پیام/عکس به بات = انتشار ناشناس در گروه\n\n"
        "مدیر:\n"
        "/setgroup — در گروه بازی اجرا کن\n"
        "/setpass <رمز> — رمز ورود\n"
        "/setrole <شماره> <نقش> — تعیین نقش\n"
        "/khook <متن> — پیام خوک\n"
        "/msg <شماره> <متن> — پیام خصوصی به پلیر\n"
        "/status — وضعیت بازی\n"
        "/clearvotes — پاک کردن رأی‌ها\n"
        "/reset — ریست کامل"
    )


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    args = context.args
    if get_player(uid):
        p = get_player(uid)
        await update.message.reply_text(f"تو قبلاً به‌عنوان {player_label(p)} ثبت‌نام کرده‌ای.")
        return
    if len(args) != 2:
        await update.message.reply_text("فرمت: /join <شماره پلیر> <رمز ورود>")
        return
    number, password = args[0], args[1]
    if password != data.get("join_password"):
        await update.message.reply_text("رمز ورود اشتباه است.")
        return
    if not number.isdigit() or not (1 <= int(number) <= 15):
        await update.message.reply_text("شماره پلیر باید بین ۱ تا ۱۵ باشد.")
        return
    for p in data["players"].values():
        if p["number"] == int(number):
            await update.message.reply_text(f"شماره {number} قبلاً گرفته شده است. با مدیر بازی تماس بگیر.")
            return
    data["players"][uid] = {"number": int(number), "role": "citizen"}
    save_data(data)
    await update.message.reply_text(
        f"✅ ثبت‌نام شدی! تو {player_label(data['players'][uid])} هستی.\n"
        "نقش تو هنوز «شهروند» است؛ مدیر بازی نقش واقعی را بعداً به تو اختصاص می‌دهد (با /role ببین)."
    )


async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = get_player(str(update.effective_user.id))
    if not p:
        await update.message.reply_text("اول با /join ثبت‌نام کن.")
        return
    await update.message.reply_text(f"شماره: {player_label(p)}\nنقش: {ROLES_FA.get(p['role'], p['role'])}")


async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = get_player(str(update.effective_user.id))
    if not p:
        await update.message.reply_text("اول با /join ثبت‌نام کن.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("فرمت: /vote <شماره پلیر>")
        return
    target = args[0]
    if not target.isdigit() or not (1 <= int(target) <= 15):
        await update.message.reply_text("شماره پلیر معتبر نیست.")
        return
    data["votes"][str(update.effective_user.id)] = int(target)
    save_data(data)
    await update.message.reply_text(f"🗳️ رأی تو ثبت شد: پلیر {int(target)}")


async def myvote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = data["votes"].get(str(update.effective_user.id))
    if v is None:
        await update.message.reply_text("هنوز رأی نداده‌ای.")
    else:
        await update.message.reply_text(f"رأی فعلی تو: پلیر {v}")


async def mafia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = get_player(str(update.effective_user.id))
    if not p:
        await update.message.reply_text("اول با /join ثبت‌نام کن.")
        return
    if p["role"] not in MAFIA_ROLES:
        await update.message.reply_text("🔒 این دستور فقط برای تیم سرخ (قاتل و همدست‌ها) است.")
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("فرمت: /mafia <متن>")
        return
    sent = 0
    for uid, pl in data["players"].items():
        if pl["role"] in MAFIA_ROLES:
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"🔴 پیام مخفی مافیا از {player_label(p)}:\n{text}")
                sent += 1
            except Exception as e:
                logger.error(e)
    await update.message.reply_text(f"✅ پیام برای {sent} عضو تیم سرخ ارسال شد.")


# ---------- ارسال ناشناس ----------
async def forward_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = get_player(str(update.effective_user.id))
    if not p:
        await update.message.reply_text("اول با /join ثبت‌نام کن.")
        return
    text = update.message.text.strip()
    if not text:
        return
    ok = await send_to_group(context, f"{player_label(p)}:\n{text}\n\n— ارسال ناشناس")
    if ok:
        await update.message.reply_text("✅ پیامت در گروه منتشر شد.")
    else:
        await update.message.reply_text("⚠️ گروه هنوز تنظیم نشده. به مدیر بگو /setgroup را در گروه اجرا کند.")


async def forward_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = get_player(str(update.effective_user.id))
    if not p:
        await update.message.reply_text("اول با /join ثبت‌نام کن.")
        return
    if not data.get("group_id"):
        await update.message.reply_text("⚠️ گروه هنوز تنظیم نشده.")
        return
    caption = f"{player_label(p)}: {update.message.caption or ''}\n\n— ارسال ناشناس"
    try:
        photo = update.message.photo[-1].file_id
        await context.bot.send_photo(chat_id=data["group_id"], photo=photo, caption=caption)
        await update.message.reply_text("✅ عکست در گروه منتشر شد.")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("⚠️ ارسال عکس ناموفق بود.")


# ---------- دستورهای مدیر ----------
async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("فقط مدیر می‌تواند.")
        return
    data["group_id"] = update.effective_chat.id
    save_data(data)
    await update.message.reply_text("✅ این گروه به‌عنوان گروه بازی ثبت شد.")


async def setpass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("فقط مدیر می‌تواند.")
        return
    if not context.args:
        await update.message.reply_text("فرمت: /setpass <رمز>")
        return
    data["join_password"] = context.args[0]
    save_data(data)
    await update.message.reply_text("✅ رمز ورود تنظیم شد.")


async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("فقط مدیر می‌تواند.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("فرمت: /setrole <شماره پلیر> <نقش>\nنقش‌ها: killer, accomplice, detective, doctor, citizen")
        return
    try:
        number = int(args[0])
    except ValueError:
        await update.message.reply_text("شماره نامعتبر است.")
        return
    role_key = args[1].lower()
    if role_key not in ROLES_FA:
        await update.message.reply_text("نقش نامعتبر است.")
        return
    for uid, pl in data["players"].items():
        if pl["number"] == number:
            pl["role"] = role_key
            save_data(data)
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"🎭 نقش تو: {ROLES_FA[role_key]}\nاین نقش را مخفی نگه دار!")
            except Exception as e:
                logger.error(e)
            await update.message.reply_text(f"✅ نقش پلیر {number} ← {ROLES_FA[role_key]}")
            return
    await update.message.reply_text("این شماره هنوز ثبت‌نام نکرده است.")


async def khook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("فقط مدیر می‌تواند.")
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("فرمت: /khook <متن>")
        return
    ok = await send_to_group(context, f"🐷 {text}\n\n— خوک")
    await update.message.reply_text("✅ پیام خوک در گروه منتشر شد." if ok else "⚠️ گروه تنظیم نشده.")


async def msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("فقط مدیر می‌تواند.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("فرمت: /msg <شماره پلیر> <متن>")
        return
    try:
        number = int(args[0])
    except ValueError:
        await update.message.reply_text("شماره نامعتبر است.")
        return
    text = " ".join(args[1:])
    for uid, pl in data["players"].items():
        if pl["number"] == number:
            try:
                await context.bot.send_message(chat_id=int(uid), text=text)
                await update.message.reply_text(f"✅ پیام به پلیر {number} ارسال شد.")
            except Exception as e:
                await update.message.reply_text("⚠️ ارسال ناموفق: " + str(e))
            return
    await update.message.reply_text("این شماره ثبت‌نام نکرده است.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("فقط مدیر می‌تواند.")
        return
    lines = ["📊 وضعیت بازی:"]
    if not data["players"]:
        lines.append("هنوز کسی ثبت‌نام نکرده.")
    for pl in sorted(data["players"].values(), key=lambda x: x["number"]):
        lines.append(f"پلیر {pl['number']} — {ROLES_FA.get(pl['role'], pl['role'])}")
    lines.append(f"\nگروه: {'تنظیم شده' if data.get('group_id') else 'تنظیم نشده'}")
    await update.message.reply_text("\n".join(lines))


async def clearvotes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("فقط مدیر می‌تواند.")
        return
    data["votes"] = {}
    save_data(data)
    await update.message.reply_text("✅ رأی‌ها پاک شد.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("فقط مدیر می‌تواند.")
        return
    data["players"] = {}
    data["votes"] = {}
    save_data(data)
    await update.message.reply_text("✅ همه‌چیز ریست شد (گروه و رمز حفظ شد).")


def main():
    if not TOKEN:
        logger.error("BOT_TOKEN تنظیم نشده است.")
        return
    threading.Thread(target=start_http_server, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("role", role))
    app.add_handler(CommandHandler("vote", vote))
    app.add_handler(CommandHandler("myvote", myvote))
    app.add_handler(CommandHandler("mafia", mafia))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(CommandHandler("setpass", setpass))
    app.add_handler(CommandHandler("setrole", setrole))
    app.add_handler(CommandHandler("khook", khook))
    app.add_handler(CommandHandler("msg", msg))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clearvotes", clearvotes))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.PHOTO, forward_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_text))
    logger.info("بات شروع به کار کرد...")
    app.run_polling()


if __name__ == "__main__":
    main()
