from flask import Blueprint, render_template, current_app

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def landing():
    # Ensure index.html exists in templates
    return render_template("index.html")
