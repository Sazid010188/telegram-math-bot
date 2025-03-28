import os
import re
import cv2
import atexit
import shutil
import logging
import pytesseract
import sympy
from sympy import symbols, Eq, solve, linsolve, simplify, SympifyError
from sympy.parsing.sympy_parser import (
    parse_expr, 
    standard_transformations, 
    implicit_multiplication
)
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, CallbackContext
# Configuration
CONFIG = {
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "telegram_token": "7639304877:AAHIsBSvy1H8LxXWqNRsMMXgW1qvcvKfF1s",
    "temp_dir": "math_temp",
    "allowed_chars": r'[0-9+\-*/^×÷()=a-zA-Z&]',
    "max_image_size": 2048
}

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Tesseract OCR configuration
pytesseract.pytesseract.tesseract_cmd = CONFIG["tesseract_path"]
os.makedirs(CONFIG["temp_dir"], exist_ok=True)

# Expression parsing configuration
transformations = standard_transformations + (implicit_multiplication,)

async def handle_start_command(update: Update, context: CallbackContext):
    """Handle /start command with formatted instructions"""
    welcome_msg = """
    📚 **Math Solution Bot** 🧮
    
    Send me:
    - Mathematical expressions
    - Equations (e.g., 2x + 5 = 13)
    - Systems of equations (e.g., 2x+y=7 and x-y=2)
    - Images of math problems
    
    I'll provide textbook-style step-by-step solutions!
    """
    await update.message.reply_text(welcome_msg)

def preprocess_input(text: str) -> str:
    """Clean and normalize mathematical input with proper equation separation"""
    # Preserve equation separation and basic formatting
    text = re.sub(r'\s*(and|&)\s*', ' & ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Replace common math symbols
    replacements = {
        '×': '*', '÷': '/', '^': '**',
        '−': '-', '—': '-', '(': ' ( ', ')': ' ) '
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Add explicit multiplication
    text = re.sub(r'(?<=\d)(?=[a-zA-Z])', '*', text)
    return text

def validate_expression(expr: str) -> bool:
    """Validate mathematical expression syntax"""
    try:
        parse_expr(expr, transformations=transformations)
        return True
    except SympifyError:
        return False

async def handle_image(update: Update, context: CallbackContext):
    """Process math problems from images with enhanced OCR"""
    try:
        photo = await update.message.photo[-1].get_file()
        img_path = os.path.join(CONFIG["temp_dir"], "temp_math.jpg")
        await photo.download_to_drive(img_path)
        
        # Image preprocessing pipeline
        img = cv2.imread(img_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # OCR processing with custom config
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
    """Generate textbook steps for solving single equations with validation"""
    try:
        # Validate both sides
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
            f"Substitute x = {solution[0]} back:",
            f"Left side: {lhs_expr.subs(x, solution[0])}",
            f"Right side: {rhs_expr.subs(x, solution[0])}",
            "",
            f"✅ **Final Solution:** x = {solution[0]}"
        ])
        
        return '\n'.join(steps)
        
    except SympifyError as e:
        return f"❌ Equation parsing error: {str(e)}"
    except Exception as e:
        return f"⚠️ Solving error: {str(e)}"

def generate_system_solution_steps(eq1: str, eq2: str) -> str:
    """Generate detailed system solution steps with validation"""
    try:
        errors = []
        equations = []
        
        # Validate and parse both equations
        for i, eq in enumerate([eq1, eq2]):
            if '=' not in eq:
                errors.append(f"Equation {i+1} missing '=': {eq}")
                continue
                
            lhs, rhs = eq.split('=', 1)
            if not validate_expression(lhs):
                errors.append(f"Invalid left side in equation {i+1}: {lhs}")
            if not validate_expression(rhs):
                errors.append(f"Invalid right side in equation {i+1}: {rhs}")
            
            try:
                equations.append(Eq(
                    parse_expr(lhs, transformations=transformations),
                    parse_expr(rhs, transformations=transformations)
                ))
            except SympifyError as e:
                errors.append(f"Equation {i+1} error: {str(e)}")
                
        if errors:
            return "\n".join(["❌ Validation errors:"] + errors)
            
        x, y = symbols('x y')
        steps = [
            "📚 **System of Equations Solution**",
            f"1. {equations[0]}",
            f"2. {equations[1]}",
            ""
        ]
        
        # Elimination Method
        steps.append("**Method 1: Elimination**")
        try:
            # Solve using linear system
            solution = linsolve(equations, (x, y))
            x_val, y_val = solution.args[0]
            
            steps.extend([
                "**Step 1: Align Equations**",
                f"Original system:",
                f"1. {equations[0]}",
                f"2. {equations[1]}",
                "",
                "**Step 2: Solve Using Matrix Elimination**",
                f"Solution: x = {x_val}, y = {y_val}",
                ""
            ])
            
        except Exception as e:
            steps.append(f"⚠️ Elimination method failed: {str(e)}")
        
        # Substitution Method
        steps.append("**Method 2: Substitution**")
        try:
            expr = solve(equations[1], x)[0]
            substituted = equations[0].subs(x, expr)
            y_sol = solve(substituted, y)[0]
            x_sol = expr.subs(y, y_sol)
            
            steps.extend([
                "**Step 1: Solve Equation 2 for x**",
                f"x = {expr}",
                "",
                "**Step 2: Substitute into Equation 1**",
                f"{equations[0].subs(x, expr)}",
                f"Solution: y = {y_sol}",
                "",
                "**Step 3: Back-Substitute y**",
                f"x = {x_sol}",
                ""
            ])
            
        except Exception as e:
            steps.append(f"⚠️ Substitution method failed: {str(e)}")
        
        # Verification
        steps.extend([
            "**Final Verification:**",
            f"Substitute x = {x_val}, y = {y_val} into original equations:",
            f"1. {equations[0].lhs} = {equations[0].rhs.subs({x: x_val, y: y_val})}",
            f"2. {equations[1].lhs} = {equations[1].rhs.subs({x: x_val, y: y_val})}",
            "",
            f"✅ **Confirmed Solution:** x = {x_val}, y = {y_val}"
        ])
        
        return '\n'.join(steps)
        
    except Exception as e:
        return f"⚠️ System solution error: {str(e)}"

async def handle_math_problem(update: Update, context: CallbackContext, text: str = None):
    """Main math problem handler with comprehensive error handling"""
    try:
        problem = text or update.message.text
        if not problem:
            return await update.message.reply_text("❌ Empty input received")
            
        clean_problem = preprocess_input(problem)
        
        if '&' in clean_problem:
            equations = clean_problem.split('&')
            if len(equations) != 2:
                return await update.message.reply_text("❌ Please provide exactly two equations separated by 'and'")
                
            solution = generate_system_solution_steps(
                equations[0].strip(), 
                equations[1].strip()
            )
        elif '=' in clean_problem:
            if clean_problem.count('=') != 1:
                return await update.message.reply_text("❌ Invalid equation format - should contain exactly one '='")
            lhs, rhs = clean_problem.split('=', 1)
            solution = generate_single_equation_steps(lhs.strip(), rhs.strip())
        else:
            if not validate_expression(clean_problem):
                return await update.message.reply_text("❌ Invalid expression syntax")
            try:
                expr = parse_expr(clean_problem, transformations=transformations)
                result = simplify(expr)
                solution = f"🔢 **Expression Evaluation:**\n{clean_problem} = {result}"
            except SympifyError as e:
                solution = f"❌ Expression error: {str(e)}"
        
        await update.message.reply_chat_action("typing")
        await update.message.reply_text(solution[:4000])  # Respect Telegram message limit
        
    except Exception as e:
        logging.error(f"Processing error: {e}")
        await update.message.reply_text(f"⚠️ Critical error: {str(e)}")

@atexit.register
def cleanup():
    """Clean temporary files on exit"""
    try:
        shutil.rmtree(CONFIG["temp_dir"], ignore_errors=True)
    except Exception as e:
        logging.warning(f"Cleanup error: {e}")

def main():
    """Initialize and run the bot"""
    app = Application.builder().token(CONFIG["telegram_token"]).build()
    
    app.add_handler(CommandHandler("start", handle_start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_math_problem))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    
    logging.info("🚀 Math Solution Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
