from flask import Blueprint, render_template
from flask_login import login_required
from models import Activity

activities = Blueprint("activities", __name__, url_prefix="/attivita")


@activities.route("/")
@login_required
def lista():
    page = 1
    attivita = Activity.query.order_by(Activity.created_at.desc()).all()
    return render_template("activities.html", attivita=attivita)
