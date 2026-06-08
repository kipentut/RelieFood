from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os
import requests
from dotenv import load_dotenv
from google import genai
from flask_cors import CORS
from threading import Lock

app = Flask(__name__)
CORS(app)
app.secret_key = "supersecretkey"
load_dotenv()

# GEMINI CLIENTS
API_KEY_NAMES = [
    "GOOGLE_API_KEY",
    "GOOGLE_API_KEY_2",
    "GOOGLE_API_KEY_3",
    "GOOGLE_API_KEY_4",
    "GOOGLE_API_KEY_5",
]
GOOGLE_API_KEYS = [
    (key_name, os.environ.get(key_name, "").strip())
    for key_name in API_KEY_NAMES
    if os.environ.get(key_name, "").strip()
]
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
gemini_clients = [(key_name, genai.Client(api_key=api_key)) for key_name, api_key in GOOGLE_API_KEYS]
client = gemini_clients[0][1] if gemini_clients else None
gemini_rotation_index = 0
gemini_rotation_lock = Lock()

if gemini_clients:
    print(f"Gemini clients loaded: {len(gemini_clients)}")
else:
    print("Warning: no GOOGLE_API_KEY values set. Gemini client disabled; AI features will use fallback responses.")

if not UNSPLASH_ACCESS_KEY:
    print("Warning: UNSPLASH_ACCESS_KEY not set. Recipe images will not be loaded from Unsplash.")


def get_rotated_gemini_clients():
    global gemini_rotation_index

    if not gemini_clients:
        return []

    with gemini_rotation_lock:
        start_index = gemini_rotation_index % len(gemini_clients)
        gemini_rotation_index = (gemini_rotation_index + 1) % len(gemini_clients)

    return gemini_clients[start_index:] + gemini_clients[:start_index]


def search_unsplash_image(query):
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        search_url = "https://api.unsplash.com/search/photos"
        headers = {
            "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}",
            "Accept-Version": "v1"
        }
        params = {
            "query": query,
            "orientation": "landscape",
            "per_page": 1,
        }
        response = requests.get(search_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if not results:
            return None
        return results[0].get("urls", {}).get("regular")
    except Exception as unsplash_error:
        print("Unsplash error:", unsplash_error)
        return None


# ---------- RANDOM ----------
def generate_random_recipe():
    return generate_ai_recipe("a random recipe using common pantry ingredients", "")


# ---------- GEMINI AI ----------
def generate_ai_recipe(user_input, leftover="", combine_mode="transform"):
    import json
    from google.genai import types

    if combine_mode not in {"transform", "beside"}:
        combine_mode = "transform"

    ingredients = [item.strip() for item in user_input.split(",") if item.strip()]
    ingredient_text = "\n".join(f"- {item}" for item in ingredients)
    leftover_action = ""
    if leftover:
        if combine_mode == "beside":
            leftover_action = f" Serve with {leftover}, choosing whether it works better as the main dish or side dish."
        else:
            leftover_action = f" Refresh and transform the leftover {leftover} with the listed ingredients."

    # Build the prompt with optional leftover meal context
    leftover_text = ""
    if leftover:
        if combine_mode == "beside":
            leftover_text = f"\n\nThe user also has a leftover meal available: {leftover}. Use the user's chosen combine style: Cook beside it. Treat either the leftover meal or the listed ingredients as the main dish and the other as a side dish, choosing the direction that best fits the user's input. Make the recipe clear about what is the main dish and what is served beside it."
        else:
            leftover_text = f"\n\nThe user also has a leftover meal available: {leftover}. Use the user's chosen combine style: Transform the meal. Use the listed ingredients to upgrade, reinvent, or refresh the leftover meal into one cohesive dish."

    available_clients = get_rotated_gemini_clients()

    # If no API key / client available, return a safe fallback without calling Gemini
    if not available_clients:
        print("AI skipped: no API key available, returning fallback recipe")
        recipe_title = f"Recipe with {', '.join(ingredients[:3])}"
        fallback_recipe = {
            "error": "AI unavailable: no valid API key found. Please set at least one GOOGLE_API_KEY value in .env.",
            "title": recipe_title,
            "description": f"A simple dish based on your ingredient list.{leftover_action}",
            "servings": "2-3",
            "time": "20 mins",
            "difficulty": "Easy",
            "ingredients": ingredients + ([f"leftover {leftover}"] if leftover else []),
            "steps": [
                f"Prepare the ingredients: {', '.join(ingredients)}.",
                "Heat a pan over medium heat and cook the ingredients together with seasoning.",
                leftover_action.strip() if leftover_action else "Taste and adjust seasoning as needed.",
                "Serve warm and enjoy your meal."
            ]
        }
        image_url = search_unsplash_image(recipe_title)
        if image_url:
            fallback_recipe["image"] = image_url
        return fallback_recipe

    prompt_text = f"""
You are a professional recipe writer. Create one unique, ingredient-driven cooking recipe inspired by common recipes online using only the ingredients given by the user.
Use the ingredient descriptions exactly as provided. Do not add new ingredients except basic pantry seasonings like salt, pepper, oil, or butter if needed.
Create a recipe title based on real existing recipes that reflects the ingredients and write a short description of the finished dish.
Write step-by-step instructions that clearly explain how to cook the dish using the specific ingredients given.

Ingredients:
{ingredient_text}{leftover_text}
"""

    # Using config to enforce native JSON output matching your schema
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "description": {"type": "STRING"},
                "servings": {"type": "STRING"},
                "time": {"type": "STRING"},
                "difficulty": {"type": "STRING"},
                "ingredients": {"type": "ARRAY", "items": {"type": "STRING"}},
                "steps": {"type": "ARRAY", "items": {"type": "STRING"}},
                "image": {"type": "STRING"},
            },
            "required": ["title", "description", "servings", "time", "difficulty", "ingredients", "steps"],
        },
    )

    last_error = None
    for key_name, active_client in available_clients:
        try:
            print(f"Trying Gemini with {key_name}")
            response = active_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_text,
                config=config
            )

            print("\nAI RAW OUTPUT:\n", response.text)

            # Because we used response_mime_type, response.text is guaranteed to be clean JSON
            recipe = json.loads(response.text)
            recipe_image = search_unsplash_image(recipe.get("title"))
            if recipe_image:
                recipe["image"] = recipe_image
            return recipe

        except Exception as e:
            last_error = e
            print(f"AI ERROR with {key_name}:", e)
            print("Trying next Gemini key if available.")

    print("All Gemini keys failed. Falling back to a recipe using the provided ingredients.")

    recipe_title = "AI Generated Recipe"
    image_url = search_unsplash_image(recipe_title)
    fallback_recipe = {
        "error": f"AI unavailable: {str(last_error)}",
        "title": recipe_title,
        "description": f"A simple recipe created from your ingredients.{leftover_action}",
        "servings": "2-3",
        "time": "20 mins",
        "difficulty": "Easy",
        "ingredients": ingredients + ([f"leftover {leftover}"] if leftover else []),
        "steps": [
            f"Prepare the ingredients: {', '.join(ingredients)}.",
            "Cook the ingredients together with basic seasoning until everything is tender and flavors are combined.",
            leftover_action.strip() if leftover_action else "Taste and adjust seasoning as needed.",
            "Serve warm and enjoy your meal."
        ]
    }
    if image_url:
        fallback_recipe["image"] = image_url
    return fallback_recipe

# ---------- ROUTES ----------
@app.route("/")
def home():
    return redirect(url_for("splash"))


@app.route("/splash")
def splash():
    return render_template("splash.html")


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


# ---------- API: GENERATE ----------
@app.route("/generate_recipe", methods=["POST"])
def generate_recipe():
    data = request.get_json(silent=True) or {}
    print("DEBUG DATA:", data)

    ingredients = data.get("ingredients", "").strip()
    leftover = data.get("leftover", "").strip()
    combine_mode = data.get("combine_mode", "transform").strip()
    if not ingredients:
        return jsonify({})

    ai_recipe = generate_ai_recipe(ingredients, leftover, combine_mode)
    return jsonify(ai_recipe)


# ---------- API: DETAILS ----------
@app.route("/recipe_details", methods=["POST"])
def recipe_details():
    data = request.get_json() or {}
    ingredients = data.get("ingredients", "")
    return jsonify(generate_ai_recipe(ingredients))


# ---------- API: RANDOM ----------
@app.route("/random_recipe")
def random_recipe():
    ai_recipe = generate_random_recipe()
    return jsonify(ai_recipe)


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
