from flask import Flask, render_template, request, redirect, url_for
import json
import os

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data/news.json")

def load_news():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_news(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/")
def index():
    news = load_news()
    return render_template("index.html", news=news)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    news = load_news()
    if request.method == "POST":
        section = request.form["section"]
        title = request.form["title"]
        text = request.form["text"]

        if section == "main":
            news["main"] = {"title": title, "text": text}
        elif section == "side":
            news["side"].append({"title": title, "text": text})
        elif section == "list":
            news["list"].append({"title": title, "text": text})

        save_news(news)
        return redirect(url_for("admin"))

    return render_template("admin.html", news=news)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
