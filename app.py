import os
import re
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models import ChatHistory, Task, User, db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_only_change_me")

# ---------------- DATABASE ----------------

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///herday.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

# ---------------- API ----------------

API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _extract_time(pattern, text):
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        raw = " ".join(match.group(1).split()).upper()
        if re.match(r"^\d{1,2}(AM|PM)$", raw):
            raw = raw[:-2] + " " + raw[-2:]
        return raw
    return None


def _build_local_schedule(user_text):
    text = user_text.lower()
    entries = []

    wake_time = _extract_time(r"wake up at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", user_text)
    breakfast_time = _extract_time(r"breakfast (?:around|at)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", user_text)
    work_start = _extract_time(r"start work at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", user_text)
    work_end = _extract_time(r"work until\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", user_text)
    lunch_time = _extract_time(r"lunch break at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", user_text)
    dinner_time = _extract_time(r"dinner (?:around|at)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))", user_text)
    bed_time = _extract_time(
        r"(?:go to bed|sleep)(?:\s+at)?(?:\s+around)?\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
        user_text,
    )

    if wake_time:
        entries.append(f"{wake_time} - Wake up")
    if breakfast_time:
        entries.append(f"{breakfast_time} - Breakfast")
    if work_start:
        entries.append(f"{work_start} - Start work")
    if lunch_time:
        entries.append(f"{lunch_time} - Lunch break")
    if work_end:
        entries.append(f"{work_end} - Finish work")

    if "exercise" in text or "workout" in text:
        entries.append("Evening - 30 minutes of exercise")
    if "reading" in text or "watching" in text or "relax" in text:
        entries.append("After exercise - Relax (reading or watching something)")

    if dinner_time:
        entries.append(f"{dinner_time} - Dinner")
    if bed_time:
        entries.append(f"{bed_time} - Bedtime")

    if len(entries) < 3:
        return None

    return "Here is a daily schedule based on what you shared:\n\n" + "\n".join(entries)


def _task_to_dict(task):
    return {
        "id": task.id,
        "title": task.title,
        "is_done": task.is_done,
        "created_at": task.created_at.isoformat(),
    }


def _build_task_context(user_id):
    tasks = (
        Task.query.filter_by(user_id=user_id)
        .order_by(Task.is_done.asc(), Task.created_at.asc())
        .limit(20)
        .all()
    )
    if not tasks:
        return "User has no tasks yet."

    lines = []
    for task in tasks:
        status = "done" if task.is_done else "pending"
        lines.append(f"- [{status}] {task.title}")
    return "User tasks:\n" + "\n".join(lines)


# ---------------- HOME ----------------


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")


# ---------------- REGISTER ----------------


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            return "Email already exists."

        hashed_password = generate_password_hash(password)

        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------- LOGIN ----------------


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["user_name"] = user.name
            return redirect(url_for("home"))

        return "Invalid credentials."

    return render_template("login.html")


# ---------------- LOGOUT ----------------


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- CHAT ----------------


@app.route("/chat", methods=["POST"])
def chat():
    if "user_id" not in session:
        return jsonify({"reply": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    user_input = payload.get("message", "").strip()

    if not user_input:
        return jsonify({"reply": "No message received."})

    message_lower = user_input.lower()
    classification_prompt = f"""
You are a classifier.

Determine if the following message is related to women's life,
wellbeing, health, emotions, work-life balance, relationships,
self-care, pregnancy, menstruation, career stress, daily routine,
or other topics commonly faced by women.

Message: "{user_input}"

Answer ONLY with:
YES
or
NO
"""
    

    planner_triggers = [
        "plan my day",
        "create a schedule",
        "make a routine",
        "organize my day",
    ]

    if any(trigger in message_lower for trigger in planner_triggers):
        reply = (
            "I'd love to help plan your day!\n\n"
            "Tell me a few things first:\n"
            "- What time do you wake up?\n"
            "- Do you have work or study hours?\n"
            "- Any meals or breaks you want included?\n"
            "- Hobbies or exercise?\n\n"
            "Share your routine and I'll build a schedule for you."
        )
        return jsonify({"reply": reply})

    greetings = ["hi", "hello", "hey", "good morning", "good evening"]

    if message_lower in greetings and len(message_lower.split()) <= 2:
        ChatHistory.query.filter_by(user_id=session["user_id"]).delete()
        db.session.commit()

        reply = (
            f"Hi {session['user_name']}! I'm HerDay. "
            "I can help you plan your day, organize tasks, or create a routine. "
            "What would you like help with today?"
        )
        return jsonify({"reply": reply})

    user_message = ChatHistory(
        user_id=session["user_id"],
        role="user",
        content=user_input,
    )

    db.session.add(user_message)
    db.session.commit()

    previous_messages = (
        ChatHistory.query.filter_by(user_id=session["user_id"])
        .order_by(ChatHistory.timestamp.desc())
        .limit(10)
        .all()
    )

    previous_messages = list(reversed(previous_messages))

    task_context = _build_task_context(session["user_id"])

    system_prompt = """
You are HerDay, a women-centric AI assistant.

Your purpose is to support women in their daily lives.

You can help with topics such as:

• emotional wellbeing
• stress and anxiety
• motivation and self confidence
• work-life balance
• productivity and routines
• career and workplace challenges
• relationships and friendships
• family responsibilities
• women's health (menstruation, pregnancy, PCOS, hormonal health)
• self care and personal growth
• study pressure
• nutrition and healthy lifestyle
• fitness and wellness
• basic financial well being

If a user asks about topics unrelated to women's life or wellbeing 
(such as technology, programming, sports, politics, beard shaving, 
general knowledge questions, etc.), DO NOT provide an explanation 
for that topic.

Instead politely say that the topic is outside your scope and 
invite the user to ask something related to women's wellbeing, 
daily life, health, productivity, or emotional support.
When rejecting a question outside your scope, respond briefly in 
1–2 sentences.

Do not repeat the same refusal sentence frequently. 
Vary the wording when declining questions outside your scope.
Keep refusal responses short (1–2 sentences).

Never comment on your own performance or say things like 
"I'm glad I stayed on track" or "I improved my response".
Always respond naturally like a supportive companion.

If a user says "yes", "okay", or gives a short reply in an emotional conversation,
continue gently asking supportive questions instead of ending the conversation.

Prefer clear, simple explanations. Avoid long academic paragraphs unless the user asks for detailed information.

HerDay should sound warm, calm, and supportive — like a thoughtful friend.
Avoid sounding like a technical assistant.

Use a few friendly emojis when appropriate to make the conversation warm and engaging. 
Do not overuse emojis. Usually include 1–3 emojis in a response.
Choose emojis that match the topic such as 🌸 💛 🌿 😊 🍳 📅.
Avoid excessive or random emojis.

When answering about children or babies, avoid overly strict medical assumptions.
Provide gentle guidance and suggest consulting a pediatrician if unsure.


Always respond with empathy, warmth, and support.
"""

    messages = [{"role": "system", "content": system_prompt}]

    for msg in previous_messages:
        messages.append({"role": msg.role, "content": msg.content})

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "llama-3.1-8b-instant",
        "messages": messages,
        "temperature": 0.5,
    }

    try:
        if not API_KEY:
            local_reply = _build_local_schedule(user_input)
            if local_reply:
                return jsonify({"reply": local_reply})
            return jsonify(
                {
                    "reply": "Please share your wake-up time, work/study hours, meals, exercise, and bedtime so I can build a schedule."
                }
            )

        response = requests.post(GROQ_URL, headers=headers, json=data, timeout=30)
        
        response.raise_for_status()
        result = response.json()

        reply = result.get("choices", [{}])[0].get("message", {}).get(
            "content",
            "Sorry, I couldn't generate a response right now.",
        )

        assistant_message = ChatHistory(
            user_id=session["user_id"],
            role="assistant",
            content=reply,
        )

        db.session.add(assistant_message)
        db.session.commit()

        return jsonify({"reply": reply})

    except requests.RequestException as e:
        print("GROQ REQUEST ERROR:", str(e))
        local_reply = _build_local_schedule(user_input)
        if local_reply:
            return jsonify({"reply": local_reply})
        return jsonify({"reply": "I couldn't reach the planner service right now. Please try again in a moment."}), 502
    except (ValueError, KeyError, IndexError, TypeError) as e:
        print("GROQ PARSE ERROR:", str(e))
        local_reply = _build_local_schedule(user_input)
        if local_reply:
            return jsonify({"reply": local_reply})
        return jsonify({"reply": "I received an unexpected response format. Please try again."}), 502
    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"reply": "Something went wrong while processing your request."}), 500






@app.route("/recipe")
def recipe():
    return render_template("recipe.html")

@app.route("/period")
def period():
    return render_template("period.html")

@app.route("/exercise")
def exercise():
    return render_template("exercise.html")
@app.route("/store")
def store():
    return render_template("store.html")
@app.route("/health")
def health():
    return render_template("health.html")
@app.route("/style")
def style():
    return render_template("styling.html")
# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run()
