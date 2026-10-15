from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Challenge, Roadmap


def seed():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(Roadmap.id).limit(1)) is None:
            db.add_all([
                Roadmap(
                    title="Frontend Developer", domain="Web Development",
                    description="Build accessible, responsive interfaces from fundamentals to deployment.",
                    steps="HTML and semantic structure\nCSS, responsive layouts, and accessibility\nJavaScript and browser APIs\nReact fundamentals\nTesting and deployment",
                ),
                Roadmap(
                    title="AI / Machine Learning", domain="Artificial Intelligence",
                    description="Learn how to prepare data, train models, evaluate results, and build useful AI features.",
                    steps="Python and data structures\nNumPy, pandas, and data visualization\nStatistics and supervised learning\nModel evaluation and feature engineering\nDeploy a small ML application",
                ),
                Roadmap(
                    title="Backend Developer", domain="Backend Development",
                    description="Create secure APIs and data-backed services.",
                    steps="Python fundamentals\nHTTP and REST API design\nSQL and relational modeling\nAuthentication and authorization\nTesting, deployment, and monitoring",
                ),
            ])
        if db.scalar(select(Challenge.id).limit(1)) is None:
            db.add_all([
                Challenge(
                    title="Campus Accessibility Finder", domain="Civic Tech", difficulty="Beginner",
                    prompt="Design a simple way for students to report and discover accessible routes around campus. Sketch the core user flow and describe how you would protect reporter privacy.",
                    duration_minutes=45,
                ),
                Challenge(
                    title="Smart Study Planner", domain="Productivity", difficulty="Intermediate",
                    prompt="Create a prototype that turns a list of deadlines and available study hours into a realistic weekly plan. Explain how users can correct an unrealistic schedule.",
                    duration_minutes=60,
                ),
                Challenge(
                    title="Sustainable Hackathon", domain="Climate Tech", difficulty="Advanced",
                    prompt="Propose a data-backed tool that helps a campus reduce event waste. Define the users, MVP, useful data sources, and one measurable success metric.",
                    duration_minutes=90,
                ),
            ])
        db.commit()


if __name__ == "__main__":
    seed()
