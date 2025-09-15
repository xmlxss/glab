from flask import Flask, render_template, redirect, url_for, flash
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests
from datetime import datetime
import config

app = Flask(__name__)
app.secret_key = "supersecret"

engine = create_engine(config.DATABASE_URI, connect_args={"check_same_thread": False})
Base = declarative_base()

class MergeRequest(Base):
    __tablename__ = "merge_requests"
    id = Column(Integer, primary_key=True)
    iid = Column(Integer)
    title = Column(String)
    state = Column(String)
    created_at = Column(DateTime)
    merged_at = Column(DateTime, nullable=True)
    author = Column(String)         
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db_session = Session()

def fetch_merge_requests():
    headers = {"PRIVATE-TOKEN": config.PRIVATE_TOKEN}
    page = 1
    per_page = 100

    while True:
        url = f"{config.GITLAB_BASE_URL}/projects/{config.PROJECT_ID}/merge_requests"
        params = {"state": "all", "per_page": per_page, "page": page}
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            break

        for mr in data:
            existing = db_session.query(MergeRequest).filter_by(id=mr["id"]).first()
            if existing:
                existing.state = mr["state"]
                existing.merged_at = (
                    datetime.fromisoformat(mr["merged_at"].replace("Z", "+00:00"))
                    if mr["merged_at"]
                    else None
                )
            else:
                db_session.add(
    MergeRequest(
        id=mr["id"],
        iid=mr["iid"],
        title=mr["title"],
        state=mr["state"],
        created_at=datetime.fromisoformat(mr["created_at"].replace("Z", "+00:00")),
        merged_at=(datetime.fromisoformat(mr["merged_at"].replace("Z", "+00:00"))
                if mr["merged_at"] else None),
        author=mr["author"]["username"],
    )
)
        page += 1

    db_session.commit()


@app.route("/open")
def open_dashboard():
    open_mrs = db_session.query(MergeRequest).filter(MergeRequest.state == "opened").all()
    total_open = len(open_mrs)

    if total_open == 0:
        avg_age_days = 0
        author_counts = []
    else:
        ages = [(datetime.utcnow() - mr.created_at).total_seconds() / 86400 for mr in open_mrs]
        avg_age_days = sum(ages) / total_open
        author_counts = []
        headers = {"PRIVATE-TOKEN": config.PRIVATE_TOKEN}
        for mr in open_mrs:
            url = f"{config.GITLAB_BASE_URL}/projects/{config.PROJECT_ID}/merge_requests/{mr.iid}"
            r = requests.get(url, headers=headers)
            r.raise_for_status()
            author = r.json()["author"]["username"]
            author_counts.append(author)

        from collections import Counter
        author_counts = Counter(author_counts).most_common()

    return render_template(
        "open_dashboard.html",
        total_open=total_open,
        avg_age_days=avg_age_days,
        author_counts=author_counts
    )

@app.route("/")
def dashboard():
    mrs = db_session.query(MergeRequest).filter(MergeRequest.merged_at != None).all()
    if not mrs:
        avg_days = None
    else:
        durations = [(mr.merged_at - mr.created_at).total_seconds() / 86400 for mr in mrs]
        avg_days = sum(durations) / len(durations)
    return render_template("dashboard.html", avg_days=avg_days, total=len(mrs))

@app.route("/refresh")
def refresh():
    fetch_merge_requests()
    flash("Data refreshed successfully!", "success")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
