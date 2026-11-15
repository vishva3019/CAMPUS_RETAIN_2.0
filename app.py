"""Entry point for Vercel and `flask --app app ...`. The application lives in campus_retain/."""
from campus_retain import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config.get("ENV_NAME") == "development")
