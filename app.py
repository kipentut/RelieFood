from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import json
import random
from google import genai

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ GEMINI CLIENT (FIXED)
client = genai.Client(api_key="AIzaSyBdSZeKgalmkMlTpM9IbeTBm8_vWF4r7aY")

# ---------- TEMPORARY USER STORE ----------
USERS = {}


# ---------- LOAD DATA ----------
def load_recipes():
    with open("recipes.json", "r") as file:
        return json.load(file)


# ---------- PANTRY INGREDIENTS ----------
IGNORE_INGREDIENTS = {
    "salt", "pepper", "oil", "butter",
    "sugar", "water", "soy", "sauce"
}


# ---------- NORMALIZE WORD ----------
def normalize(word):
    word = word.lower().strip()
    if word.endswith("s"):
        word = word[:-1]
    return word


# ---------- USER INPUT ----------
def get_user_set(user_input):
    words = user_input.replace(",", " ").split()
    return set(normalize(word) for word in words)


# ---------- MATCH RECIPES ----------
def find_recipes(user_input):
    recipes = load_recipes()
    user_set = get_user_set(user_input)

    results = []

    for item in recipes:
        ingredient_set = set()

        for ing in item["ingredients"]:
            words = ing.lower().split()
            for w in words:
                if w.isalpha() and w not in IGNORE_INGREDIENTS:
                    ingredient_set.add(normalize(w))

        essential = [ing for ing in ingredient_set if ing not in IGNORE_INGREDIENTS]

        matches = sum(1 for ing in essential if ing in user_set)

        if matches >= 2:
            results.append((matches, item))

    results.sort(reverse=True, key=lambda x: x[0])

    return [item for _, item in results[:3]]


# ---------- RANDOM ----------
def get_random_recipe():
    return random.choice(load_recipes())


# ---------- GEMINI AI ----------
def generate_ai_recipe(user_input):
    import json
    import re
    from google.genai import types

    try:
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=f"""
Generate a realistic cooking recipe using: {user_input}

Return ONLY JSON:
{{
  "title": "Recipe Name",
  "ingredients": ["ingredient1"],
  "steps": [
    "Step 1",
    "Step 2",
    "Step 3",
    "Step 4"
  ]
}}
""")
                ]
            )
        ]

        response_text = ""

        # ✅ SIMPLIFIED STREAM LOOP
        for chunk in client.models.generate_content_stream(
            model="gemini-3-flash-preview",  # ✅ THIS IS YOUR WORKING MODEL
            contents=contents
        ):
            if chunk.text:
                response_text += chunk.text

        print("\n✅ AI RAW OUTPUT:\n", response_text)

        # ✅ extract JSON only
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))

        raise ValueError("No JSON found")

    except Exception as e:
        print("❌ AI ERROR:", e)

        return {
            "title": "AI Generated Recipe",
            "ingredients": [i.strip() for i in user_input.split(",")],
            "steps": [
                "Clean and prepare all ingredients properly before starting the cooking process.",
                "Heat a pan over medium heat and cook the ingredients gradually while stirring to ensure even cooking.",
                "Add remaining ingredients and mix thoroughly to combine flavors properly.",
                "Continue cooking until fully done and serve warm."
            ]
        }

# ---------- SIGNUP ----------
@app.route("/signup", methods=["POST"])
def signup():
    email = request.form.get("email")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")

    if email in USERS:
        return "User already exists", 400

    if password != confirm_password:
        return "Passwords do not match", 400

    USERS[email] = password
    session["user"] = email
    return redirect(url_for("index"))


# ---------- SIGNIN ----------
@app.route("/signin", methods=["POST"])
def signin():
    email = request.form.get("email")
    password = request.form.get("password")

    if email in USERS and USERS[email] == password:
        session["user"] = email
        return redirect(url_for("index"))
    else:
        return "Invalid email or password", 401


@app.route("/signin_page")
def signin_page():
    return render_template("signin.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("signin_page"))


# ---------- ROUTES ----------
@app.route("/")
def home():
    return redirect(url_for("signin_page"))


@app.route("/signup")
def signup_page():
    return render_template("signup.html")


@app.route("/index")
def index():
    return render_template("index.html")


@app.route("/generate")
def generate():
    return render_template("generate.html")


@app.route("/infographic")
def infographic():
    return render_template("infographic.html")


@app.route("/storage")
def storage():
    return render_template("storage.html")


@app.route("/portion")
def portion_page():
    return render_template("portion.html")


# ---------- API: GENERATE ----------
@app.route("/generate_recipe", methods=["POST"])
def generate_recipe():
    data = request.get_json()
    ingredients = data.get("ingredients", "").strip()

    if not ingredients:
        return jsonify([])

    results = find_recipes(ingredients)

    # ✅ DATABASE FIRST
    if results:
        return jsonify([
            {"title": r["title"], "ai": False}
            for r in results
        ])

    # ✅ AI FALLBACK
    ai_recipe = generate_ai_recipe(ingredients)

    return jsonify([{
        "title": ai_recipe["title"],
        "ai": True,
        "full": ai_recipe
    }])


# ---------- API: DETAILS ----------
@app.route("/recipe_details", methods=["POST"])
def recipe_details():
    data = request.get_json()
    title = data.get("title")
    ingredients = data.get("ingredients", "")

    recipes = load_recipes()

    for r in recipes:
        if r["title"] == title:
            return jsonify(r)

    return jsonify(generate_ai_recipe(ingredients))


# ---------- API: RANDOM ----------
@app.route("/random_recipe")
def random_recipe():
    recipe = get_random_recipe()
    return jsonify({
        "title": recipe["title"],
        "ingredients": recipe["ingredients"],
        "steps": recipe["steps"]
    })


# ---------- PORTION CALCULATOR ----------
def calculate_portion(age, sex, height, weight):
    try:
        age = int(age)
        height = float(height)
        weight = float(weight)

        if sex.lower() == "male":
            calories = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            calories = 10 * weight + 6.25 * height - 5 * age - 161

        portions = round(calories / 600, 1)

        return {"calories": round(calories), "portion": portions}

    except:
        return {"calories": 0, "portion": 0}


@app.route("/calculate_portion", methods=["POST"])
def calculate_portion_api():
    data = request.get_json()

    return jsonify(calculate_portion(
        data.get("age"),
        data.get("sex"),
        data.get("height"),
        data.get("weight")
    ))


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True)