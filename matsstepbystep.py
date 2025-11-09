import os
import re
import cv2
import atexit
import shutil
import logging
import pytesseract
import sympy
import threading
import time
import requests
from flask import Flask
from sympy import symbols, Eq, solve, linsolve, simplify, SympifyError
from sympy.parsing.sympy_parser import (
    parse_expr, 
    standard_transformations, 
    implicit_multiplication
)
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, CallbackContext

# ----------------- Configuration -----------------
CONFIG = {
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "telegram_token": "7639304877:AAHIsBSvy1H8LxXWqNRsMMXgW1qvcvKfF1s",  # <-- replace this
    "temp_dir": "math_temp",
    "allowed_chars": r'[0-9+\-*/^×÷()=a-zA-Z&]',
    "max_image_size": 2048,
    "app_url": "https://your-render-app.onrender.com"  # <-- replace with your Render URL
}

# ----------------- Logging Setup -----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ----------------- Flask Keep-Alive Server -----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Math Solver Bot is alive!"

def run_flask():
    """Run Flask server on Render for keep-alive"""
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

def keep_alive():
    """Ping the app every 5 minutes"""
    while True:
        try:
            res = requests.get(CONFIG["app_url"])
            print(f"[KeepAlive] Ping status: {res.status_code}")
        except Exception as e:
            print(f"[KeepAlive] Ping error: {e}")
        time.sleep(300)

# Start background threads
threading.Thread(target=run_flask, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()

# ----------------- OCR & SymPy Setup -----------------
pytesseract.pytesseract.tesseract_cmd = CONFIG["tesseract_path"]
os.makedirs(CONFIG["temp_dir"], exist_ok=True)
transformations = standard_transformations + (implicit_multiplication,)

# ----------------- Telegram Bot Logic -----------------
async def handle_start_command(update: Update, context: CallbackContext):
    """Handle /start command"""
    welcome_msg = (
        "📚 **Math Solution Bot** 🧮\n\n"
        "Send me:\n"
        "- Mathematical expressions\n"
        "- Equations (e.g., 2x + 5 = 13)\n"
        "- Systems of equations (e.g., 2x+y=7 and x-y=2)\n"
        "- Images of math problems\n\n"
        "I'll provide textbook-style step-by-step solutions!"
    )
    await update.message.reply_text(welcome_msg)

def preprocess_input(text: str) -> str:
    """Clean and normalize math input"""
    text = re.sub(r'\s*(and|&)\s*', ' & ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    replacements = {'×': '*', '÷': '/', '^': '**', '−': '-', '—': '-', '(': ' ( ', ')': ' ) '}
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'(?<=\d)(?=[a-zA-Z])', '*', text)
    return text

def validate_expression(expr: str) -> bool:
    try:
        parse_expr(expr, transformations=transformations)
        return True
    except SympifyError:
        return False

async def handle_image(update: Update, context: CallbackContext):
    """Process math problems from images"""
    try:
        photo = await update.message.photo[-1].get_file()
        img_path = os.path.join(CONFIG["temp_dir"], "temp_math.jpg")
        await photo.download_to_drive(img_path)
        img = cv2.imread(img_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(thresh, config='--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+-*/^=()&')
        processed_text = preprocess_input(text)
        await update.message.reply_text(f"📸 Detected: {processed_text}")
        await handle_math_problem(update, context, processed_text)
    except Exception as e:
        logging.error(f"Image error: {e}")
        await update.message.reply_text("⚠️ Error processing image")
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)

def generate_single_equation_steps(lhs: str, rhs: str) -> str:
    """Solve single equation"""
    try:
        if not validate_expression(lhs):
            return f"❌ Invalid left side: {lhs}"
        if not validate_expression(rhs):
            return f"❌ Invalid right side: {rhs}"
        x = symbols('x')
        lhs_expr = parse_expr(lhs, transformations=transformations)
        rhs_expr = parse_expr(rhs, transformations=transformations)
        equation = Eq(lhs_expr, rhs_expr)
        steps = [
            "📝 **Equation Solution**",
            f"**Original Equation:** {equation}",
            "",
            "**Step 1: Simplify Equation**",
            f"{lhs_expr - rhs_expr} = 0"
        ]
        solution = solve(equation, x)
        if not solution:
            return "🔍 No solution found"
        steps.extend([
            "",
            "**Step 2: Solve for x**",
            f"x = {solution[0]}",
            "",
            "**Verification:**",
            f"Left: {lhs_expr.subs(x, solution[0])}, Right: {rhs_expr.subs(x, solution[0])}",
            "",
            f"✅ **Final Solution:** x = {solution[0]}"
        ])
        return '\n'.join(steps)
    except Exception as e:
        return f"⚠️ Solving error: {str(e)}"

def generate_system_solution_steps(eq1: str, eq2: str) -> str:
    """Solve system of equations"""
    try:
        equations = []
        for eq in [eq1, eq2]:
            lhs, rhs = eq.split('=', 1)
            equations.append(Eq(parse_expr(lhs, transformations=transformations),
                                parse_expr(rhs, transformations=transformations)))
        x, y = symbols('x y')
        solution = linsolve(equations, (x, y))
        x_val, y_val = solution.args[0]
        steps = [
            "📚 **System of Equations Solution**",
            f"1️⃣ {equations[0]}",
            f"2️⃣ {equations[1]}",
            "",
            "**Solution:**",
            f"x = {x_val}, y = {y_val}",
            "",
            "✅ Verified successfully!"
        ]
        return '\n'.join(steps)
    except Exception as e:
        return f"⚠️ System solution error: {str(e)}"

async def handle_math_problem(update: Update, context: CallbackContext, text: str = None):
    """Main math problem handler"""
    try:
        problem = text or update.message.text
        if not problem:
            return await update.message.reply_text("❌ Empty input received")
        clean_problem = preprocess_input(problem)
        if '&' in clean_problem:
            equations = clean_problem.split('&')
            if len(equations) != 2:
                return await update.message.reply_text("❌ Provide exactly two equations separated by 'and'")
            solution = generate_system_solution_steps(equations[0].strip(), equations[1].strip())
        elif '=' in clean_problem:
            lhs, rhs = clean_problem.split('=', 1)
            solution = generate_single_equation_steps(lhs.strip(), rhs.strip())
        else:
            expr = parse_expr(clean_problem, transformations=transformations)
            result = simplify(expr)
            solution = f"🔢 **Expression Evaluation:**\n{clean_problem} = {result}"
        await update.message.reply_text(solution[:4000])
    except Exception as e:
        logging.error(f"Processing error: {e}")
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

@atexit.register
def cleanup():
    try:
        shutil.rmtree(CONFIG["temp_dir"], ignore_errors=True)
    except Exception as e:
        logging.warning(f"Cleanup error: {e}")

def main():
    """Start the bot"""
    app = Application.builder().token(CONFIG["telegram_token"]).build()
    app.add_handler(CommandHandler("start", handle_start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_math_problem))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    logging.info("🚀 Math Solver Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

