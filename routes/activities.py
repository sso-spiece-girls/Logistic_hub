from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy.orm import load_only, joinedload
from models import Activity, User

activities = Blueprint("activities", __name__, url_prefix="/attivita")


@activities.route("/")
@login_required
def lista():
    page = request.args.get("page", 1, type=int)
    pagination = Activity.query.options(
        joinedload(Activity.user).load_only(User.username),
        load_only(Activity.action, Activity.description, Activity.created_at),
    ).order_by(Activity.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False,
    )
    return render_template("activities.html", pagination=pagination)
