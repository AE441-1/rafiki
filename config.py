import os

from dotenv import load_dotenv


load_dotenv()


class Config:

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "rafiki_mkombozi")

    SECRET_KEY = os.getenv("SECRET_KEY", "rafiki-mkombozi-secret-key")
    USSD_WEBHOOK_TOKEN = os.getenv("USSD_WEBHOOK_TOKEN", "")
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "")
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").strip().lower() == "true"
    SNIPPE_API_KEY = os.getenv("SNIPPE_API_KEY", "")
    SNIPPE_BASE_URL = os.getenv("SNIPPE_BASE_URL", "https://api.snippe.sh")