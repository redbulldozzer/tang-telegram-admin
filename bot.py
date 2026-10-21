#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import subprocess
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== Загрузка переменных окружения =====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# Терпимо относимся к пробелам: "id1, id2"
_admin_env = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = set(int(x) for x in _admin_env.replace(" ", "").split(",") if x)

# Путь к кластерному скрипту
TANGCTL = "/usr/local/bin/tangctl"

if not BOT_TOKEN or not ADMIN_IDS:
    raise RuntimeError("BOT_TOKEN и ADMIN_IDS должны быть заданы в .env")

# ===== Логирование =====
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)

# ===== Утилиты =====
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    """
    Запускает команду и возвращает (rc, out).
    stdout и stderr объединяем, чтобы проще показывать ошибки.
    """
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (cp.stdout or "") + (cp.stderr or "")
        return cp.returncode, out.strip()
    except Exception as e:
        return 1, f"Ошибка запуска: {e}"

# ===== Декоратор «только для админов» =====
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        uid = user.id if user else 0
        if not is_admin(uid):
            logging.warning(f"⛔ Отказано пользователю {uid}")
            # Мягко игнорируем не-админов
            return
        logging.info(f"✅ Разрешён доступ: {uid} / @{user.username if user else '-'}")
        return await func(update, context)
    return wrapper

# ===== Команды =====
@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот готов.\n"
        "Команды:\n"
        "/status_tang — статус на обеих нодах\n"
        "/start_tang — включить на обеих\n"
        "/stop_tang — выключить на обеих\n"
        "/restart_tang — перезапуск на обеих\n"
        "/reboot — перезагрузка текущего узла"
    )

@admin_only
async def status_tang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rc, out = run_cmd(["sudo", "-n", TANGCTL, "check"])
    if rc == 0:
        msg = "✅ tang включен (оба узла)"
    elif rc == 2:
        msg = "🛑 tang выключен (оба узла)"
    else:
        # частично или узел недоступен — добавим краткие детали по строкам
        lines = [l for l in (out or "").splitlines() if l.strip()]
        details = "\n".join(f"• {l}" for l in lines) if lines else "(нет деталей)"
        msg = f"⚠️ tang включен частично\n{details}"
    await update.message.reply_text(msg)

@admin_only
async def start_tang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rc, out = run_cmd(["sudo", "-n", TANGCTL, "start"], timeout=60)
    await update.message.reply_text("✅ Запущено на обеих" if rc == 0 else f"❌ Ошибка:\n{out}")

@admin_only
async def stop_tang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rc, out = run_cmd(["sudo", "-n", TANGCTL, "stop"], timeout=60)
    await update.message.reply_text("🛑 Остановлено на обеих" if rc == 0 else f"❌ Ошибка:\n{out}")

@admin_only
async def restart_tang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rc, out = run_cmd(["sudo", "-n", TANGCTL, "restart"], timeout=60)
    await update.message.reply_text("🔁 Перезапущено на обеих" if rc == 0 else f"❌ Ошибка:\n{out}")

@admin_only
async def reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("♻️ Перезагрузка узла…")
    # Если нужно без ожидания — Popen, но sudoers должен это разрешать
    subprocess.Popen(["sudo", "-n", "/sbin/reboot"])

# ===== Запуск бота =====
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status_tang", status_tang))
    app.add_handler(CommandHandler("start_tang", start_tang))
    app.add_handler(CommandHandler("stop_tang", stop_tang))
    app.add_handler(CommandHandler("restart_tang", restart_tang))
    app.add_handler(CommandHandler("reboot", reboot))

    app.run_polling()

if __name__ == "__main__":
    main()
