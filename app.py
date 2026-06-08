from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import os
import requests
from dotenv import load_dotenv
from google import genai
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = "supersecretkey"
load_dotenv()

# GEMINI CLIENT
API_KEY = os.environ.get("GOOGLE_API_KEY")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
client = None
if API_KEY:
    client = genai.Client(api_key=API_KEY)
else:
    print("Warning: GOOGLE_API_KEY not set. Gemini client disabled; AI features will use fallback responses.")

if not UNSPLASH_ACCESS_KEY:
    print("Warning: UNSPLASH_ACCESS_KEY not set. Recipe images will not be loaded from Unsplash.")


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

    # If no API key / client available, return a safe fallback without calling Gemini
    if client is None:
        print("AI skipped: no API key available, returning fallback recipe")
        recipe_title = f"Recipe with {', '.join(ingredients[:3])}"
        fallback_recipe = {
            "error": "AI unavailable: no valid API key found. Please set GOOGLE_API_KEY in .env.",
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

    try:
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

        # FIXED MODEL NAME & Added config
        response = client.models.generate_content(
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
        print("AI ERROR:", e)
        print("Falling back to a recipe using the provided ingredients.")

        recipe_title = "AI Generated Recipe"
        image_url = search_unsplash_image(recipe_title)
        fallback_recipe = {
            "error": f"AI unavailable: {str(e)}",
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
