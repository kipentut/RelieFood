from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import json
import random

app = Flask(__name__)
app.secret_key = "supersecretkey"   # required for session handling

# ---------- TEMPORARY USER STORE ----------
# Keys = email, Values = password
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
        ingredient_set = set(normalize(ing) for ing in item["ingredients"])

        essential = [ing for ing in ingredient_set if ing not in IGNORE_INGREDIENTS]
        if not essential:
            continue

        if all(ing in user_set for ing in essential):
            results.append(item)

    return results

# ---------- RANDOM ----------
def get_random_recipe():
    return random.choice(load_recipes())

# ---------- AI FALLBACK (PLACEHOLDER) ----------
def generate_ai_recipe(user_input):
    return {
        "title": "AI Generated Recipe",
        "ingredients": user_input.split(", "),
        "steps": [
            "Prepare all ingredients.",
            "Cook based on combination.",
            "Season to taste.",
            "Serve hot."
        ],
        "note": "This recipe is AI-generated and may not guarantee taste or accuracy."
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
    if results:
        return jsonify([{"title": r["title"]} for r in results])

    ai_recipe = generate_ai_recipe(ingredients)
    return jsonify([{"title": ai_recipe["title"], "ai": True}])

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

# ---------- API: PORTION ----------
@app.route("/calculate_portion", methods=["POST"])
def calculate_portion_api():
    data = request.get_json()
    result = calculate_portion(
        data.get("age"),
        data.get("sex"),
        data.get("height"),
        data.get("weight")
    )
    return jsonify(result)

# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True)
