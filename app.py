from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

import hmac
import math
import os
import re
import secrets
import smtplib
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage

import mysql.connector
import requests

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from config import Config

from ai.recommendation_engine import (
    calculate_risk,
    generate_recommendations
)


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

app = Flask(__name__)
app.config.from_object(Config)

AFRICAN_COUNTRIES = (
    "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi",
    "Cabo Verde", "Cameroon", "Central African Republic", "Chad", "Comoros",
    "Cote d'Ivoire", "Democratic Republic of the Congo", "Djibouti", "Egypt",
    "Equatorial Guinea", "Eritrea", "Eswatini", "Ethiopia", "Gabon", "Gambia",
    "Ghana", "Guinea", "Guinea-Bissau", "Kenya", "Lesotho", "Liberia", "Libya",
    "Madagascar", "Malawi", "Mali", "Mauritania", "Mauritius", "Morocco",
    "Mozambique", "Namibia", "Niger", "Nigeria", "Republic of the Congo",
    "Rwanda", "Sao Tome and Principe", "Senegal", "Seychelles", "Sierra Leone",
    "Somalia", "South Africa", "South Sudan", "Sudan", "Tanzania", "Togo",
    "Tunisia", "Uganda", "Zambia", "Zimbabwe",
)
MARKET_CURRENCIES = ("TZS", "KES", "UGX", "RWF", "BIF", "USD")


def normalize_phone_number(value):
    return re.sub(r"\D+", "", str(value or ""))


def ensure_password_reset_table():
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                token_hash VARCHAR(255) NOT NULL,
                expires_at DATETIME NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_reset_user (user_id),
                INDEX idx_reset_expiry (expires_at)
            )
            """
        )
        db.commit()
    except mysql.connector.Error as error:
        print(f"Password reset table setup error: {error}")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


def find_user_by_identifier(identifier):
    if not identifier:
        return None

    normalized_identifier = str(identifier).strip()
    query_value = normalized_identifier.lower()
    db = None
    cursor = None
    user = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = %s
               OR phone IS NOT NULL
            ORDER BY id DESC
            """,
            (query_value,),
        )
        rows = cursor.fetchall()
        for row in rows:
            if (row.get("email") or "").lower() == query_value:
                return row
            if normalize_phone_number(row.get("phone")) == normalize_phone_number(query_value):
                return row
    except mysql.connector.Error as error:
        print(f"User lookup error: {error}")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()
    return user


def send_password_reset_email(recipient_email, reset_url):
    smtp_server = app.config.get("MAIL_SERVER")
    if not smtp_server:
        return False, "SMTP is not configured. Add MAIL_SERVER and related SMTP settings to send reset links."

    sender = app.config.get("MAIL_DEFAULT_SENDER") or app.config.get("MAIL_USERNAME") or "no-reply@example.com"
    port = int(app.config.get("MAIL_PORT", 587))
    username = app.config.get("MAIL_USERNAME") or ""
    password = app.config.get("MAIL_PASSWORD") or ""
    use_tls = bool(app.config.get("MAIL_USE_TLS", True))

    message = EmailMessage()
    message["Subject"] = "Reset your Rafiki Mkombozi password"
    message["From"] = sender
    message["To"] = recipient_email
    text_body = (
        "You requested a password reset for your Rafiki Mkombozi account.\n\n"
        f"Reset your password here: {reset_url}\n\n"
        "This link expires in 30 minutes. If you did not request it, you can ignore this email."
    )
    html_body = (
        "<p>You requested a password reset for your Rafiki Mkombozi account.</p>"
        f"<p><a href='{reset_url}'>Reset your password</a></p>"
        "<p>This link expires in 30 minutes. If you did not request it, you can ignore this email.</p>"
    )
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(smtp_server, port) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
        return True, None
    except Exception as error:
        print(f"Password reset email error: {error}")
        return False, str(error)


def create_password_reset_token(user_id):
    ensure_password_reset_table()
    token = secrets.token_urlsafe(32)
    token_hash = generate_password_hash(token)
    expires_at = datetime.now() + timedelta(minutes=30)
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, token_hash, expires_at.strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
    except mysql.connector.Error as error:
        print(f"Password reset token error: {error}")
        token = None
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()
    return token


def validate_password_reset_token(token):
    if not token:
        return None
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM password_reset_tokens
            WHERE expires_at > NOW()
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            token_hash = row.get("token_hash")
            if token_hash and check_password_hash(token_hash, token):
                return row["user_id"]
    except mysql.connector.Error as error:
        print(f"Password reset validation error: {error}")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()
    return None


# ============================================================
# OPENSTREETMAP GEOCODING
# ============================================================

def geocode_location(region, district, ward):
    """
    Convert Region + District + Ward into latitude and longitude
    using OpenStreetMap Nominatim.
    """

    address = (
        f"{ward}, {district}, {region}, Tanzania"
    )

    url = (
        "https://nominatim.openstreetmap.org/search"
    )

    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "countrycodes": "tz"
    }

    headers = {
        "User-Agent": "RAFIKI_MKOMBOZI/1.0"
    }

    try:

        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )

        response.raise_for_status()

        results = response.json()

        if not results:
            return None

        result = results[0]

        return {
            "latitude": float(
                result["lat"]
            ),

            "longitude": float(
                result["lon"]
            ),

            "display_name": result.get(
                "display_name",
                address
            )
        }

    except requests.RequestException as error:

        print(
            f"Geocoding error: {error}"
        )

        return None

    except (
        ValueError,
        KeyError,
        TypeError
    ) as error:

        print(
            f"Geocoding data error: {error}"
        )

        return None


@app.route("/api/location/geocode", methods=["POST"])
def geocode_address():
    """Find coordinates automatically from the customer's entered address."""

    if session.get("role") != "customer":
        return {"error": "Sign in as a customer to look up a location."}, 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "Enter a region, district, and ward."}, 400

    region = str(payload.get("region", "")).strip()
    district = str(payload.get("district", "")).strip()
    ward = str(payload.get("ward", "")).strip()

    if not all((region, district, ward)):
        return {"error": "Enter a region, district, and ward."}, 400

    result = geocode_location(region, district, ward)
    if result is None:
        return {"error": "OpenStreetMap could not find that address. Check the spelling or adjust the location fields."}, 404

    return result


@app.route("/api/location/reverse", methods=["POST"])
def reverse_geocode():
    """Resolve browser-provided coordinates to an OSM address."""

    if session.get("role") != "customer":
        return {"error": "Sign in as a customer to detect your location."}, 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "A latitude and longitude are required."}, 400

    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
    except (TypeError, ValueError):
        return {"error": "The location coordinates are invalid."}, 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return {"error": "The location coordinates are outside valid ranges."}, 400

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 18,
            },
            headers={"User-Agent": "RAFIKI_MKOMKOMBOZI/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        return {"error": "OpenStreetMap could not resolve this location. Please enter it manually."}, 502

    if not isinstance(result, dict):
        return {"error": "OpenStreetMap returned an invalid location result."}, 502

    address = result.get("address", {})
    if not isinstance(address, dict):
        address = {}
    region = address.get("state") or address.get("region") or ""
    district = (
        address.get("county")
        or address.get("municipality")
        or address.get("city_district")
        or address.get("district")
        or ""
    )
    ward = (
        address.get("suburb")
        or address.get("neighbourhood")
        or address.get("quarter")
        or address.get("village")
        or address.get("hamlet")
        or address.get("town")
        or address.get("city")
        or ""
    )

    return {
        "latitude": latitude,
        "longitude": longitude,
        "display_name": result.get("display_name", ""),
        "region": region,
        "district": district,
        "ward": ward,
    }


@app.route("/api/location/climate-preview", methods=["POST"])
def climate_risk_preview():
    """Calculate local climate-risk indicators as soon as coordinates resolve."""

    if session.get("role") != "customer":
        return {"error": "Sign in as a customer to analyze local climate risk."}, 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "A latitude and longitude are required."}, 400

    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
    except (TypeError, ValueError):
        return {"error": "The location coordinates are invalid."}, 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return {"error": "The location coordinates are outside valid ranges."}, 400

    cached_preview = session.get("climate_risk_preview", {})
    same_customer = cached_preview.get("customer_id") == session.get("user_id")
    same_location = (
        abs(cached_preview.get("latitude", 999) - latitude) < 0.000001
        and abs(cached_preview.get("longitude", 999) - longitude) < 0.000001
    )
    if same_customer and same_location and cached_preview.get("scores"):
        return {
            **cached_preview["scores"],
            "latitude": latitude,
            "longitude": longitude,
            "location_address": payload.get("location_address", "")
        }

    climate = get_climate_data(latitude, longitude)
    if not climate:
        return {"error": "Recent climate data is unavailable for this location right now."}, 502

    climate_scores = calculate_climate_scores(climate)
    if not climate_scores:
        return {"error": "There is not enough climate data to estimate risks for this location."}, 422

    overall_score = calculate_risk(
        climate_scores["drought_score"],
        climate_scores["flood_score"],
        climate_scores["rainfall_score"]
    )
    preview_scores = {
        "drought_score": climate_scores["drought_score"],
        "flood_score": climate_scores["flood_score"],
        "rainfall_score": climate_scores["rainfall_score"],
        "pest_pressure_score": climate_scores["pest_pressure_score"],
        "overall_score": overall_score,
        "summary": climate_scores["summary"]
    }
    session["climate_risk_preview"] = {
        "customer_id": session["user_id"],
        "latitude": latitude,
        "longitude": longitude,
        "scores": preview_scores
    }

    return {
        **preview_scores,
        "latitude": latitude,
        "longitude": longitude,
        "location_address": payload.get("location_address", "")
    }


# ============================================================
# OPEN-METEO CLIMATE DATA
# ============================================================

def get_climate_data(latitude, longitude):
    """
    Retrieve historical climate data for a specific
    latitude and longitude using Open-Meteo.
    """

    url = (
        "https://archive-api.open-meteo.com/v1/archive"
    )

    # The archive endpoint publishes data with a short delay. Use the most
    # recent complete 365-day period instead of a hard-coded year.
    end_date = date.today() - timedelta(days=5)
    start_date = end_date - timedelta(days=364)

    params = {

        "latitude": latitude,

        "longitude": longitude,

        # ----------------------------------------------------
        # HISTORICAL PERIOD
        # ----------------------------------------------------

        "start_date": start_date.isoformat(),

        "end_date": end_date.isoformat(),

        # ----------------------------------------------------
        # DAILY CLIMATE VARIABLES
        # ----------------------------------------------------

        "daily": ",".join([
            "temperature_2m_mean",
            "precipitation_sum",
            "rain_sum",
            "et0_fao_evapotranspiration"
        ]),

        "timezone": "Africa/Dar_es_Salaam"
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        return data

    except requests.RequestException as error:

        print(
            f"Climate API error: {error}"
        )

        return None

    except ValueError as error:

        print(
            f"Climate JSON error: {error}"
        )

        return None


# ============================================================
# CLIMATE RISK CALCULATION
# ============================================================

def calculate_climate_scores(climate_data):
    """
    Convert Open-Meteo climate information into
    prototype climate-risk scores.

    Returns:

        drought_score
        flood_score
        rainfall_score
        climate_summary
    """

    if not climate_data:

        return None

    daily = climate_data.get(
        "daily",
        {}
    )

    temperatures = daily.get(
        "temperature_2m_mean",
        []
    )

    precipitation = daily.get(
        "precipitation_sum",
        []
    )

    rain = daily.get(
        "rain_sum",
        []
    )

    evapotranspiration = daily.get(
        "et0_fao_evapotranspiration",
        []
    )


    # ========================================================
    # REMOVE MISSING VALUES
    # ========================================================

    valid_temperatures = []

    for value in temperatures:

        if value is not None:

            try:
                valid_temperatures.append(
                    float(value)
                )

            except (
                ValueError,
                TypeError
            ):
                pass


    valid_precipitation = []

    for value in precipitation:

        if value is not None:

            try:
                valid_precipitation.append(
                    float(value)
                )

            except (
                ValueError,
                TypeError
            ):
                pass


    valid_rain = []

    for value in rain:

        if value is not None:

            try:
                valid_rain.append(
                    float(value)
                )

            except (
                ValueError,
                TypeError
            ):
                pass


    valid_evapotranspiration = []

    for value in evapotranspiration:

        if value is not None:

            try:
                valid_evapotranspiration.append(
                    float(value)
                )

            except (
                ValueError,
                TypeError
            ):
                pass


    # ========================================================
    # MAKE SURE DATA EXISTS
    # ========================================================

    if not valid_precipitation:

        return None


    # ========================================================
    # BASIC CLIMATE INDICATORS
    # ========================================================

    total_precipitation = sum(
        valid_precipitation
    )

    total_rainfall = sum(
        valid_rain
    )


    average_temperature = (

        sum(valid_temperatures)
        /
        len(valid_temperatures)

        if valid_temperatures

        else 0
    )


    total_evapotranspiration = sum(
        valid_evapotranspiration
    )


    total_days = len(
        valid_precipitation
    )


    # ========================================================
    # DRY DAYS
    # ========================================================

    dry_days = sum(

        1

        for value in valid_precipitation

        if value < 1
    )


    dry_day_percentage = (

        (
            dry_days
            /
            total_days
        )
        * 100

        if total_days > 0

        else 0
    )


    # ========================================================
    # HEAVY RAIN DAYS
    # ========================================================

    heavy_rain_days = sum(

        1

        for value in valid_precipitation

        if value >= 10
    )


    # ========================================================
    # DROUGHT SCORE
    # ========================================================
    #
    # Higher dry-day percentage
    # and higher evapotranspiration relative
    # to precipitation increase drought risk.
    #
    # Prototype score: 0 - 100
    # ========================================================

    evapotranspiration_ratio = (

        total_evapotranspiration
        /
        max(
            total_precipitation,
            1
        )
    )


    drought_score = (

        (
            dry_day_percentage
            * 0.70
        )

        +

        (
            evapotranspiration_ratio
            * 30
        )
    )


    drought_score = max(
        0,
        min(
            100,
            drought_score
        )
    )


    # ========================================================
    # FLOOD SCORE
    # ========================================================

    precipitation_factor = min(

        (
            total_precipitation
            /
            1500
        )
        * 70,

        70
    )


    heavy_rain_factor = min(

        heavy_rain_days * 2,

        30
    )


    flood_score = (

        precipitation_factor
        +
        heavy_rain_factor
    )


    flood_score = max(
        0,
        min(
            100,
            flood_score
        )
    )


    # ========================================================
    # EXCESS RAINFALL SCORE
    # ========================================================

    rainfall_score = min(

        (
            total_rainfall
            /
            1800
        )
        * 100,

        100
    )


    rainfall_score = max(
        0,
        min(
            100,
            rainfall_score
        )
    )


    # A climate-only proxy for weather conditions that can favor
    # crop pest and disease pressure. It does not measure pesticide use
    # or chemical exposure and should not be treated as a field diagnosis.
    paired_weather = []
    for temperature, precipitation_value in zip(temperatures, precipitation):
        if temperature is None or precipitation_value is None:
            continue
        try:
            paired_weather.append((float(temperature), float(precipitation_value)))
        except (ValueError, TypeError):
            continue

    warm_wet_days = sum(
        1 for temperature, precipitation_value in paired_weather
        if 18 <= temperature <= 35 and precipitation_value >= 1
    )
    heavy_rain_days_for_pests = sum(
        1 for _, precipitation_value in paired_weather
        if precipitation_value >= 10
    )
    paired_days = len(paired_weather)
    warm_wet_percentage = (
        warm_wet_days / paired_days * 100
        if paired_days else 0
    )
    heavy_rain_percentage = (
        heavy_rain_days_for_pests / paired_days * 100
        if paired_days else 0
    )
    pest_pressure_score = round(
        max(0, min(100, warm_wet_percentage * 0.75 + heavy_rain_percentage * 0.25)),
        2
    )


    # ========================================================
    # ROUND VALUES
    # ========================================================

    drought_score = round(
        drought_score,
        2
    )

    flood_score = round(
        flood_score,
        2
    )

    rainfall_score = round(
        rainfall_score,
        2
    )


    # ========================================================
    # CLIMATE SUMMARY
    # ========================================================

    climate_summary = {

        "average_temperature":
            round(
                average_temperature,
                2
            ),

        "total_precipitation":
            round(
                total_precipitation,
                2
            ),

        "total_rainfall":
            round(
                total_rainfall,
                2
            ),

        "dry_days":
            dry_days,

        "heavy_rain_days":
            heavy_rain_days,

        "total_evapotranspiration":
            round(
                total_evapotranspiration,
                2
            ),

        "days_analyzed":
            total_days
    }


    return {
        "drought_score": drought_score,
        "flood_score": flood_score,
        "rainfall_score": rainfall_score,
        "pest_pressure_score": pest_pressure_score,
        "summary": climate_summary
    }


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db():

    return mysql.connector.connect(

        host=app.config["MYSQL_HOST"],

        port=app.config["MYSQL_PORT"],

        user=app.config["MYSQL_USER"],

        password=app.config["MYSQL_PASSWORD"],

        database=app.config["MYSQL_DATABASE"]
    )


def normalize_ussd_phone(phone_number):
    digits = re.sub(r"\D", "", phone_number or "")

    if digits.startswith("255") and len(digits) == 12:
        return "0" + digits[3:]

    if len(digits) == 9:
        return "0" + digits

    return digits


@app.route("/ussd", methods=["POST"])
def africastalking_ussd():
    """Serve the Africa's Talking USSD callback for registered customers."""
    phone_number = request.form.get("phoneNumber", "")
    menu_text = request.form.get("text", "").strip()

    def ussd_response(message):
        return app.response_class(message, mimetype="text/plain")

    webhook_token = app.config.get("USSD_WEBHOOK_TOKEN", "")
    if not webhook_token or not hmac.compare_digest(
        request.args.get("token", ""), webhook_token
    ):
        return ussd_response("END USSD service is not available.")

    if not menu_text:
        return ussd_response(
            "CON Rafiki Mkombozi\n"
            "1. Overall risk\n"
            "2. My latest farm\n"
            "3. Top recommendation"
        )

    normalized_phone = normalize_ussd_phone(phone_number)
    if not normalized_phone:
        return ussd_response("END We could not identify your phone number.")

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, name, phone
            FROM users
            WHERE role = 'customer' AND phone IS NOT NULL
            """
        )
        matching_customers = [
            user
            for user in cursor.fetchall()
            if normalize_ussd_phone(user["phone"]) == normalized_phone
        ]

        if len(matching_customers) != 1:
            return ussd_response(
                "END No unique customer account is registered to this phone number."
            )
        customer = matching_customers[0]

        if menu_text == "1":
            cursor.execute(
                """
                SELECT overall_score, drought_score, flood_score,
                       rainfall_score, pest_pressure_score
                FROM risk_assessments
                WHERE customer_id = %s
                  ORDER BY id DESC
                LIMIT 1
                """,
                (customer["id"],),
            )
            assessment = cursor.fetchone()
            if assessment is None:
                return ussd_response("END No risk assessment is available yet.")

            return ussd_response(
                "END Overall risk: {overall:.0f}%. "
                "Drought {drought:.0f}, flood {flood:.0f}, "
                "rainfall {rainfall:.0f}, pests {pests:.0f}.".format(
                    overall=assessment["overall_score"] or 0,
                    drought=assessment["drought_score"] or 0,
                    flood=assessment["flood_score"] or 0,
                    rainfall=assessment["rainfall_score"] or 0,
                    pests=assessment["pest_pressure_score"] or 0,
                )
            )

        if menu_text == "2":
            cursor.execute(
                """
                SELECT f.farm_name, f.crop_type, f.ward, f.district,
                       f.region, f.farm_size, ra.overall_score
                FROM farms AS f
                LEFT JOIN risk_assessments AS ra
                  ON ra.farm_id = f.id
                 AND ra.id = (
                     SELECT MAX(ra2.id)
                     FROM risk_assessments AS ra2
                     WHERE ra2.farm_id = f.id
                 )
                WHERE f.user_id = %s AND f.status = 'active'
                ORDER BY f.created_at DESC, f.id DESC
                LIMIT 1
                """,
                (customer["id"],),
            )
            farm = cursor.fetchone()
            if farm is None:
                return ussd_response("END No active farm is registered.")

            location = ", ".join(
                part
                for part in (farm["ward"], farm["district"], farm["region"])
                if part
            )
            details = "{}: {}. Crop: {}. Size: {:g} ac.".format(
                farm["farm_name"],
                location or "location not set",
                farm["crop_type"] or "not set",
                farm["farm_size"] or 0,
            )
            if farm["overall_score"] is not None:
                details += " Risk: {:.0f}%.".format(farm["overall_score"])
            return ussd_response("END " + details)

        if menu_text == "3":
            cursor.execute(
                """
                  SELECT insurance_products.name, insurance_products.premium,
                      recommendations.risk_score, recommendations.relevance
                FROM recommendations
                JOIN insurance_products
                    ON recommendations.policy_id = insurance_products.id
                WHERE recommendations.customer_id = %s
                ORDER BY recommendations.risk_score DESC
                LIMIT 1
                """,
                (customer["id"],),
            )
            recommendation = cursor.fetchone()
            if recommendation is None:
                return ussd_response("END No insurance recommendation is available yet.")

            return ussd_response(
                "END Top recommendation: {}. Relevance: {} ({:.0f}%). "
                "Premium: TZS {}.".format(
                    recommendation["name"],
                    recommendation["relevance"] or "not rated",
                    recommendation["risk_score"] or 0,
                    "{:,.0f}".format(recommendation["premium"] or 0),
                )
            )

        return ussd_response("END Invalid choice. Dial again to start over.")
    except mysql.connector.Error as error:
        print(f"USSD database error: {error}")
        return ussd_response("END Service is temporarily unavailable. Please try again.")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/service-worker.js")
def service_worker():
    response = app.send_static_file("js/service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/")
def index():
    return render_template(
        "portal.html",
        active_tab="home"
    )


@app.route("/about-us")
def about_us():
    return render_template("portal.html", active_tab="about")


@app.route("/help")
def help_page():
    return render_template("portal.html", active_tab="help")


@app.route("/market")
def supplier_market():
    listings = []
    my_listings = []
    trades = []
    trade_insurance = None
    db = None
    cursor = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT listings.*, users.name AS farmer_name
            FROM crop_listings AS listings
            JOIN users ON users.id = listings.farmer_id
            WHERE listings.status = 'available'
              AND listings.quantity_available > 0
            ORDER BY listings.created_at DESC, listings.id DESC
            LIMIT 100
            """
        )
        listings = cursor.fetchall()

        if session.get("role") == "customer":
            user_id = session["user_id"]
            cursor.execute(
                """
                SELECT listings.*
                FROM crop_listings AS listings
                WHERE listings.farmer_id = %s
                ORDER BY listings.created_at DESC, listings.id DESC
                """,
                (user_id,),
            )
            my_listings = cursor.fetchall()
            cursor.execute(
                """
                  SELECT trades.*, listings.crop_name, listings.unit,
                       listings.origin_country, listings.origin_location,
                      buyers.name AS buyer_name, sellers.name AS seller_name,
                      insurance.name AS insurance_product_name
                FROM crop_trades AS trades
                JOIN crop_listings AS listings ON listings.id = trades.listing_id
                JOIN users AS buyers ON buyers.id = trades.buyer_id
                JOIN users AS sellers ON sellers.id = trades.seller_id
                  LEFT JOIN insurance_products AS insurance
                    ON insurance.id = trades.insurance_product_id
                WHERE trades.buyer_id = %s OR trades.seller_id = %s
                ORDER BY trades.updated_at DESC, trades.id DESC
                """,
                (user_id, user_id),
            )
            trades = cursor.fetchall()

        cursor.execute(
            """
            SELECT id, name, coverage, premium_rate_percent
            FROM insurance_products
            WHERE category = 'Agricultural Trade Insurance'
              AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """
        )
        trade_insurance = cursor.fetchone()
    except mysql.connector.Error as error:
        print(f"Crop market database error: {error}")
        flash("The trade market needs its database migration before listings can be loaded.", "warning")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template(
        "portal.html",
        active_tab="market",
        crop_listings=listings,
        my_crop_listings=my_listings,
        crop_trades=trades,
        trade_insurance=trade_insurance,
        african_countries=AFRICAN_COUNTRIES,
        market_currencies=MARKET_CURRENCIES,
    )


def market_decimal(value, field_name):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Enter a valid {field_name}.")
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{field_name.capitalize()} must be greater than zero.")
    return amount


def market_json_error(message, status_code):
    return {"error": message}, status_code


# Prices for the buyer market cards in templates/portal.html (TZS per unit).
CROP_PRICES = {
    "Fresh tomatoes": 24000,
    "Dry maize": 1200,
    "Green beans": 1800,
    "Sweet potatoes": 900,
}
CROP_DELIVERY_FEE = 500  # flat delivery fee in TZS, added to every order


@app.route("/api/market/checkout", methods=["POST"])
def create_crop_checkout():
    """Create a Snippe hosted checkout session for a crop order.

    The buyer's name and phone number are collected on the Snippe payment
    page, so the request only needs the items and the delivery location.
    """
    if not app.config.get("SNIPPE_API_KEY"):
        return market_json_error("Payments are not configured yet. Set SNIPPE_API_KEY.", 503)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return market_json_error("Enter the order details.", 400)

    location = str(payload.get("location", "")).strip()
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return market_json_error("Add at least one crop to the order.", 400)

    items = []
    subtotal = 0
    for raw in raw_items:
        name = str((raw or {}).get("name", "")).strip()
        try:
            quantity = int((raw or {}).get("quantity", 0))
        except (TypeError, ValueError):
            quantity = 0
        if name not in CROP_PRICES or quantity < 1:
            return market_json_error("One of the crops or quantities is not valid.", 400)
        items.append({"name": name, "quantity": quantity, "price": CROP_PRICES[name]})
        subtotal += CROP_PRICES[name] * quantity

    amount = subtotal + CROP_DELIVERY_FEE
    description = ", ".join(f"{item['quantity']} x {item['name']}" for item in items)

    body = {
        "amount": amount,
        "currency": "TZS",
        "description": f"Rafiki crop order: {description} + TZS {CROP_DELIVERY_FEE:,} delivery"[:200],
        "metadata": {
            "items": items,
            "delivery_fee": CROP_DELIVERY_FEE,
            "location": location,
            "user_id": session.get("user_id"),
        },
        "expires_in": 3600,
    }
    # Snippe only accepts HTTPS redirect URLs, so skip it during local HTTP development.
    redirect_url = url_for("supplier_market", view="buyer", payment="success", _external=True)
    if redirect_url.startswith("https://"):
        body["redirect_url"] = redirect_url

    try:
        response = requests.post(
            f"{app.config['SNIPPE_BASE_URL'].rstrip('/')}/api/v1/sessions",
            json=body,
            headers={
                "Authorization": f"Bearer {app.config['SNIPPE_API_KEY']}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        result = response.json()
    except (requests.RequestException, ValueError) as error:
        print(f"Snippe session error: {error}")
        return market_json_error("Could not reach the payment provider. Try again shortly.", 502)

    data = result.get("data") if isinstance(result, dict) else None
    checkout_url = (data or {}).get("payment_link_url") or (data or {}).get("checkout_url")
    if not response.ok or not checkout_url:
        print(f"Snippe session rejected ({response.status_code}): {result}")
        message = (result.get("error") or {}).get("message") if isinstance(result, dict) else None
        return market_json_error(message or "The payment session could not be created.", 502)

    return {
        "checkout_url": checkout_url,
        "reference": data.get("reference"),
        "amount": amount,
    }


@app.route("/api/market/listings", methods=["POST"])
def create_crop_listing():
    if session.get("role") != "customer":
        return market_json_error("Sign in as a farmer to publish a crop listing.", 401)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return market_json_error("Enter the crop listing details.", 400)

    crop_name = str(payload.get("crop_name", "")).strip()
    origin_country = str(payload.get("origin_country", "")).strip()
    origin_location = str(payload.get("origin_location", "")).strip()
    unit = str(payload.get("unit", "")).strip().lower()
    currency = str(payload.get("currency", "")).strip().upper()
    market_scope = str(payload.get("market_scope", "")).strip().lower()

    if not crop_name or len(crop_name) > 100:
        return market_json_error("Crop name is required and must be under 100 characters.", 400)
    if origin_country not in AFRICAN_COUNTRIES or not origin_location or len(origin_location) > 160:
        return market_json_error("Choose an African country and enter the farm or market location.", 400)
    if unit not in {"kg", "ton", "bag", "crate", "bunch"}:
        return market_json_error("Choose a supported crop unit.", 400)
    if currency not in MARKET_CURRENCIES:
        return market_json_error("Choose a supported market currency.", 400)
    if market_scope not in {"tanzania", "africa"}:
        return market_json_error("Choose Tanzania or Africa-wide market reach.", 400)
    if market_scope == "tanzania" and origin_country != "Tanzania":
        return market_json_error("Tanzania-only listings must originate in Tanzania.", 400)

    try:
        quantity = market_decimal(payload.get("quantity"), "quantity")
        price = market_decimal(payload.get("price"), "price")
    except ValueError as error:
        return market_json_error(str(error), 400)

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO crop_listings
                (farmer_id, crop_name, quantity_available, unit,
                 price_per_unit, currency, origin_country, origin_location,
                 market_scope, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'available')
            """,
            (
                session["user_id"], crop_name, quantity, unit, price,
                currency, origin_country, origin_location, market_scope,
            ),
        )
        listing_id = cursor.lastrowid
        db.commit()
        return {"listing_id": listing_id, "message": "Crop listing published."}, 201
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Crop listing insert error: {error}")
        return market_json_error("Could not publish the crop listing. Run the market migration and try again.", 503)
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/market/listings/<int:listing_id>/trades", methods=["POST"])
def request_crop_trade(listing_id):
    if session.get("role") != "customer":
        return market_json_error("Sign in as a customer to request a crop trade.", 401)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return market_json_error("Enter the trade request details.", 400)

    destination_country = str(payload.get("destination_country", "")).strip()
    destination_location = str(payload.get("destination_location", "")).strip()
    if destination_country not in AFRICAN_COUNTRIES:
        return market_json_error("Choose an African destination country.", 400)
    if not destination_location or len(destination_location) > 160:
        return market_json_error("Enter a destination city or delivery location.", 400)
    try:
        quantity = market_decimal(payload.get("quantity"), "quantity")
    except ValueError as error:
        return market_json_error(str(error), 400)

    wants_insurance = payload.get("insured") is True
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, farmer_id, quantity_available, unit, price_per_unit,
                   currency, origin_country, market_scope, status
            FROM crop_listings
            WHERE id = %s
            FOR UPDATE
            """,
            (listing_id,),
        )
        listing = cursor.fetchone()
        if listing is None or listing["status"] != "available":
            return market_json_error("This crop listing is no longer available.", 404)
        if listing["farmer_id"] == session["user_id"]:
            return market_json_error("You cannot request a trade for your own listing.", 400)
        if listing["market_scope"] == "tanzania" and destination_country != listing["origin_country"]:
            return market_json_error("This listing is only available for delivery within Tanzania.", 400)
        if quantity > Decimal(str(listing["quantity_available"])):
            return market_json_error("The requested quantity exceeds the available crop.", 400)

        insurance_product_id = None
        insurance_premium = Decimal("0.00")
        if wants_insurance:
            cursor.execute(
                """
                SELECT id, premium_rate_percent
                FROM insurance_products
                WHERE category = 'Agricultural Trade Insurance'
                  AND status = 'active'
                  AND premium_rate_percent IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """
            )
            product = cursor.fetchone()
            if product is None:
                return market_json_error("Trade insurance is unavailable. Contact an insurer or run the market migration.", 409)
            insurance_product_id = product["id"]
            trade_value = quantity * Decimal(str(listing["price_per_unit"]))
            insurance_premium = (
                trade_value * Decimal(str(product["premium_rate_percent"])) / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        remaining = Decimal(str(listing["quantity_available"])) - quantity
        listing_status = "sold_out" if remaining == 0 else "available"
        cursor.execute(
            """
            INSERT INTO crop_trades
                (listing_id, seller_id, buyer_id, quantity, unit_price, currency,
                 destination_country, destination_location, status,
                 insurance_product_id, insurance_premium)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'requested', %s, %s)
            """,
            (
                listing_id, listing["farmer_id"], session["user_id"], quantity,
                listing["price_per_unit"], listing["currency"],
                destination_country, destination_location,
                insurance_product_id, insurance_premium,
            ),
        )
        trade_id = cursor.lastrowid
        cursor.execute(
            "UPDATE crop_listings SET quantity_available = %s, status = %s WHERE id = %s",
            (remaining, listing_status, listing_id),
        )
        db.commit()
        return {"trade_id": trade_id, "message": "Trade request sent to the farmer."}, 201
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Crop trade request error: {error}")
        return market_json_error("Could not submit the trade. Run the market migration and try again.", 503)
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/market/trades/<int:trade_id>/status", methods=["POST"])
def update_crop_trade_status(trade_id):
    if session.get("role") != "customer":
        return market_json_error("Sign in to update this trade.", 401)

    payload = request.get_json(silent=True)
    new_status = str(payload.get("status", "")).strip().lower() if isinstance(payload, dict) else ""
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, listing_id, seller_id, buyer_id, quantity, status
            FROM crop_trades
            WHERE id = %s
            FOR UPDATE
            """,
            (trade_id,),
        )
        trade = cursor.fetchone()
        if trade is None:
            return market_json_error("Trade not found.", 404)

        user_id = session["user_id"]
        seller_actions = {
            "requested": {"accepted", "rejected"},
            "accepted": {"in_transit"},
            "in_transit": {"delivered"},
        }
        buyer_actions = {
            "requested": {"cancelled"},
            "delivered": {"completed"},
        }
        if trade["seller_id"] == user_id:
            allowed = seller_actions.get(trade["status"], set())
        elif trade["buyer_id"] == user_id:
            allowed = buyer_actions.get(trade["status"], set())
        else:
            return market_json_error("You are not a participant in this trade.", 403)
        if new_status not in allowed:
            return market_json_error("That trade-status change is not allowed.", 409)

        if new_status in {"rejected", "cancelled"}:
            cursor.execute(
                "SELECT quantity_available FROM crop_listings WHERE id = %s FOR UPDATE",
                (trade["listing_id"],),
            )
            listing = cursor.fetchone()
            if listing is not None:
                restored_quantity = Decimal(str(listing["quantity_available"])) + Decimal(str(trade["quantity"]))
                cursor.execute(
                    "UPDATE crop_listings SET quantity_available = %s, status = 'available' WHERE id = %s",
                    (restored_quantity, trade["listing_id"]),
                )

        cursor.execute(
            "UPDATE crop_trades SET status = %s WHERE id = %s",
            (new_status, trade_id),
        )
        db.commit()
        return {"trade_id": trade_id, "status": new_status}, 200
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Crop trade status error: {error}")
        return market_json_error("Could not update the trade status. Try again.", 503)
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


# ============================================================
# TEST OPENSTREETMAP
# ============================================================

@app.route("/test-geocode")
def test_geocode():

    result = geocode_location(
        "Morogoro",
        "Kilosa",
        "Magole"
    )


    if result:

        return result


    return {
        "error":
        "Location could not be found"
    }, 404


# ============================================================
# TEST OPEN-METEO
# ============================================================

@app.route("/test-climate")
def test_climate():

    latitude = -6.3738745

    longitude = 37.3742612


    climate = get_climate_data(
        latitude,
        longitude
    )


    if climate:

        return climate


    return {
        "error":
        "Unable to retrieve climate data"
    }, 500


# ============================================================
# TEST CLIMATE RISK CALCULATION
# ============================================================

@app.route("/test-risk")
def test_risk():

    latitude = -6.3738745

    longitude = 37.3742612


    climate = get_climate_data(
        latitude,
        longitude
    )


    if not climate:

        return {
            "error":
            "Unable to retrieve climate data"
        }, 500


    scores = calculate_climate_scores(
        climate
    )


    if not scores:

        return {
            "error":
            "Unable to calculate climate scores"
        }, 500


    overall = calculate_risk(

        scores["drought_score"],

        scores["flood_score"],

        scores["rainfall_score"]
    )


    return {

        "drought_score":
            scores["drought_score"],

        "flood_score":
            scores["flood_score"],

        "rainfall_score":
            scores["rainfall_score"],

        "overall_score":
            overall,

        "climate_summary":
            scores["summary"]
    }


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        phone = request.form.get(
            "phone",
            ""
        ).strip()


        password = request.form.get(
            "password",
            ""
        )


        role = request.form.get(
            "role"
        )


        if not name or not email or not password:

            flash(
                "Please complete all required fields.",
                "danger"
            )

            return redirect(
                url_for("register")
            )


        allowed_roles = [

            "customer",

            "bank",

            "insurer"
        ]


        if role not in allowed_roles:

            flash(
                "Invalid account type selected.",
                "danger"
            )

            return redirect(
                url_for("register")
            )


        password_hash = generate_password_hash(
            password
        )


        db = None
        cursor = None


        try:

            db = get_db()

            cursor = db.cursor()


            cursor.execute("""
                SELECT id
                FROM users
                WHERE email = %s
                LIMIT 1
            """, (
                email,
            ))


            existing_user = cursor.fetchone()


            if existing_user:

                flash(
                    "This email is already registered.",
                    "danger"
                )

                return redirect(
                    url_for("register")
                )


            cursor.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    phone,
                    password,
                    role
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                name,
                email,
                phone,
                password_hash,
                role
            ))


            db.commit()


            flash(
                "Registration successful. Please login.",
                "success"
            )


            return redirect(
                url_for("login")
            )


        except mysql.connector.Error as error:

            if db is not None:
                db.rollback()


            print(
                f"Registration error: {error}"
            )


            flash(
                "Registration could not be completed. "
                "Please try again.",
                "danger"
            )


        finally:

            if cursor is not None:
                cursor.close()

            if db is not None:
                db.close()


    return render_template(
        "register.html"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        identifier = request.form.get(
            "identifier",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        if not identifier or not password:

            flash(
                "Please enter your email or phone number and password.",
                "danger"
            )

            return redirect(
                url_for("login")
            )


        db = None
        cursor = None
        user = None


        try:

            db = get_db()

            cursor = db.cursor(
                dictionary=True
            )

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE email = %s OR phone = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (identifier.lower(), identifier),
            )

            user = cursor.fetchone()

            if user is None:
                normalized_phone = normalize_phone_number(identifier)
                if normalized_phone:
                    cursor.execute(
                        """
                        SELECT *
                        FROM users
                        WHERE phone IS NOT NULL
                        ORDER BY id DESC
                        """
                    )
                    rows = cursor.fetchall()
                    for row in rows:
                        if normalize_phone_number(row.get("phone")) == normalized_phone:
                            user = row
                            break


        except mysql.connector.Error as error:

            print(
                f"Login database error: {error}"
            )


            flash(
                "Unable to connect to the database.",
                "danger"
            )


            return redirect(
                url_for("login")
            )


        finally:

            if cursor is not None:
                cursor.close()

            if db is not None:
                db.close()


        if user and check_password_hash(

            user["password"],

            password
        ):

            session.clear()


            session["user_id"] = user["id"]

            session["name"] = user["name"]

            session["role"] = user["role"]


            if user["role"] == "customer":

                return redirect(
                    url_for("dashboard")
                )


            elif user["role"] == "bank":

                return redirect(
                    url_for("bank_dashboard")
                )


            elif user["role"] == "insurer":

                return redirect(
                    url_for("insurer_dashboard")
                )


            else:

                session.clear()


                flash(
                    "Your account role is not recognized.",
                    "danger"
                )


                return redirect(
                    url_for("login")
                )


        flash(
            "Invalid email, phone number, or password.",
            "danger"
        )


    return render_template(
        "login.html"
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        if not identifier:
            flash("Enter your email address or phone number.", "danger")
            return redirect(url_for("forgot_password"))

        user = find_user_by_identifier(identifier)
        if user and user.get("email"):
            ensure_password_reset_table()
            token = create_password_reset_token(user["id"])
            if token:
                reset_url = url_for("reset_password", token=token, _external=True)
                sent, info = send_password_reset_email(user["email"], reset_url)
                if sent:
                    flash("If that account exists, a password reset link has been sent to the registered email.", "success")
                    return redirect(url_for("login"))
                flash(f"A reset link was generated, but email delivery is not configured: {info}", "warning")
                return render_template("forgot_password.html", reset_link=reset_url)

        flash("If that email or phone is registered, a reset link will be sent.", "info")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user_id = validate_password_reset_token(token)
    if request.method == "POST":
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not user_id:
            flash("This password reset link is invalid or expired.", "danger")
            return redirect(url_for("forgot_password"))

        if len(new_password) < 6:
            flash("Your password must contain at least 6 characters.", "danger")
            return render_template("reset_password.html", token=token, valid=True)

        if new_password != confirm_password:
            flash("The password confirmation does not match.", "danger")
            return render_template("reset_password.html", token=token, valid=True)

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "UPDATE users SET password = %s WHERE id = %s",
                (generate_password_hash(new_password), user_id),
            )
            cursor.execute(
                "DELETE FROM password_reset_tokens WHERE user_id = %s",
                (user_id,),
            )
            db.commit()
            flash("Your password has been reset successfully. Please sign in.", "success")
            return redirect(url_for("login"))
        except mysql.connector.Error as error:
            print(f"Password reset database error: {error}")
            flash("Unable to update your password right now.", "danger")
            return render_template("reset_password.html", token=token, valid=True)
        finally:
            if cursor is not None:
                cursor.close()
            if db is not None:
                db.close()

    if not user_id:
        return render_template("reset_password.html", token=token, valid=False)
    return render_template("reset_password.html", token=token, valid=True)


@app.route("/api/mobile/session")
def mobile_session():
    if not session.get("user_id") or session.get("role") not in {
        "customer",
        "bank",
        "insurer",
    }:
        return {"error": "Sign in to continue."}, 401

    return {
        "user": {
            "id": session["user_id"],
            "name": session.get("name", ""),
            "role": session["role"],
        }
    }


@app.route("/api/mobile/login", methods=["POST"])
def mobile_login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "Enter your email and password."}, 400

    identifier = str(payload.get("identifier", payload.get("email", ""))).strip()
    password = payload.get("password", "")
    if not identifier or not isinstance(password, str) or not password:
        return {"error": "Enter your email or phone number and password."}, 400

    db = None
    cursor = None
    user = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, name, email, phone, password, role
            FROM users
            WHERE email = %s OR phone = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (identifier.lower(), identifier),
        )
        user = cursor.fetchone()
        if user is None:
            normalized_phone = normalize_phone_number(identifier)
            if normalized_phone:
                cursor.execute(
                    """
                    SELECT id, name, email, phone, password, role
                    FROM users
                    WHERE phone IS NOT NULL
                    ORDER BY id DESC
                    """
                )
                rows = cursor.fetchall()
                for row in rows:
                    if normalize_phone_number(row.get("phone")) == normalized_phone:
                        user = row
                        break
    except mysql.connector.Error as error:
        print(f"Mobile login database error: {error}")
        return {"error": "Unable to sign in right now."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    if not user or not check_password_hash(user["password"], password):
        return {"error": "Invalid email, phone number, or password."}, 401

    if user["role"] not in {"customer", "bank", "insurer"}:
        return {"error": "This account type is not supported in the mobile app."}, 403

    session.clear()
    session["user_id"] = user["id"]
    session["name"] = user["name"]
    session["role"] = user["role"]

    return {
        "user": {
            "id": user["id"],
            "name": user["name"],
            "role": user["role"],
        }
    }


@app.route("/api/mobile/logout", methods=["POST"])
def mobile_logout():
    session.clear()
    return {"ok": True}


@app.route("/api/mobile/dashboard")
def mobile_dashboard():
    user_id = session.get("user_id")
    role = session.get("role")
    if not user_id or role not in {"customer", "bank", "insurer"}:
        return {"error": "Sign in to continue."}, 401

    db = None
    cursor = None
    metrics = []
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        if role == "customer":
            cursor.execute(
                """
                SELECT overall_score
                FROM risk_assessments
                WHERE customer_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            risk = cursor.fetchone()
            risk_score = risk.get("overall_score") if risk else None
            metrics.append({
                "label": "Latest climate risk",
                "value": f"{float(risk_score):.0f}%" if risk_score is not None else "Not assessed",
            })

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending
                FROM loan_applications
                WHERE customer_id = %s
                """,
                (user_id,),
            )
            applications = cursor.fetchone() or {}
            metrics.extend([
                {"label": "Loan applications", "value": str(applications.get("total") or 0)},
                {"label": "Awaiting review", "value": str(applications.get("pending") or 0)},
            ])

            cursor.execute(
                "SELECT COUNT(*) AS total FROM loans WHERE customer_id = %s AND status = 'active'",
                (user_id,),
            )
            metrics.append({"label": "Active loans", "value": str((cursor.fetchone() or {}).get("total") or 0)})

            cursor.execute(
                "SELECT COUNT(*) AS total FROM customer_policies WHERE customer_id = %s AND status = 'active'",
                (user_id,),
            )
            metrics.append({"label": "Active policies", "value": str((cursor.fetchone() or {}).get("total") or 0)})

        elif role == "bank":
            cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'customer'")
            metrics.append({"label": "Customers", "value": str((cursor.fetchone() or {}).get("total") or 0)})

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM loan_applications
                WHERE status IN ('pending', 'under_review')
                """
            )
            metrics.append({"label": "Applications to review", "value": str((cursor.fetchone() or {}).get("total") or 0)})

            cursor.execute("SELECT COUNT(*) AS total FROM loan_applications WHERE status = 'approved'")
            metrics.append({"label": "Approved applications", "value": str((cursor.fetchone() or {}).get("total") or 0)})

            cursor.execute("SELECT COUNT(*) AS total FROM loans WHERE status = 'active'")
            metrics.append({"label": "Active loans", "value": str((cursor.fetchone() or {}).get("total") or 0)})

        else:
            cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'customer'")
            metrics.append({"label": "Customers", "value": str((cursor.fetchone() or {}).get("total") or 0)})

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM risk_assessments AS assessment
                INNER JOIN (
                    SELECT customer_id, MAX(id) AS latest_id
                    FROM risk_assessments
                    GROUP BY customer_id
                ) AS latest ON latest.latest_id = assessment.id
                WHERE assessment.overall_score >= 70
                """
            )
            metrics.append({"label": "High-risk customers", "value": str((cursor.fetchone() or {}).get("total") or 0)})

            cursor.execute("SELECT COUNT(*) AS total FROM customer_profiles")
            metrics.append({"label": "Risk profiles", "value": str((cursor.fetchone() or {}).get("total") or 0)})

            cursor.execute("SELECT COUNT(*) AS total FROM customer_policies WHERE status = 'active'")
            metrics.append({"label": "Active policies", "value": str((cursor.fetchone() or {}).get("total") or 0)})

            cursor.execute("SELECT COUNT(*) AS total FROM customer_policies WHERE status = 'pending'")
            metrics.append({"label": "Pending applications", "value": str((cursor.fetchone() or {}).get("total") or 0)})

    except mysql.connector.Error as error:
        print(f"Mobile dashboard database error: {error}")
        return {"error": "Unable to load dashboard information."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return {
        "user": {
            "id": user_id,
            "name": session.get("name", ""),
            "role": role,
        },
        "metrics": metrics,
    }


@app.route("/api/mobile/loans", methods=["GET", "POST"])
def mobile_customer_loans():
    if session.get("role") != "customer":
        return {"error": "Customer sign-in required."}, 403

    if request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return {"error": "Provide the loan amount, purpose, and duration."}, 400

        try:
            amount = float(payload.get("amount", 0))
            duration_months = int(payload.get("duration_months", 0))
        except (TypeError, ValueError):
            return {"error": "Enter a valid amount and repayment duration."}, 400

        purpose = str(payload.get("purpose", "")).strip()
        if (
            not math.isfinite(amount)
            or amount < 1000
            or duration_months not in {3, 6, 9, 12, 18, 24}
            or not purpose
        ):
            return {"error": "Provide a valid amount, purpose, and duration."}, 400

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                """
                INSERT INTO loan_applications
                    (customer_id, amount, purpose, duration_months, status)
                VALUES (%s, %s, %s, %s, 'pending')
                """,
                (session["user_id"], amount, purpose, duration_months),
            )
            db.commit()
            return {"ok": True, "application_id": cursor.lastrowid}, 201
        except mysql.connector.Error as error:
            if db is not None:
                db.rollback()
            print(f"Mobile loan application error: {error}")
            return {"error": "The loan application could not be submitted."}, 503
        finally:
            if cursor is not None:
                cursor.close()
            if db is not None:
                db.close()

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, amount, purpose, duration_months, status, application_date
            FROM loan_applications
            WHERE customer_id = %s
            ORDER BY application_date DESC, id DESC
            """,
            (session["user_id"],),
        )
        applications = [
            {
                "id": row["id"],
                "amount": f"{float(row['amount'] or 0):,.0f}",
                "purpose": row["purpose"],
                "duration_months": row["duration_months"],
                "status": row["status"],
                "application_date": str(row.get("application_date") or ""),
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT id, amount, interest_rate, duration_months, status, disbursement_date
            FROM loans
            WHERE customer_id = %s
            ORDER BY id DESC
            """,
            (session["user_id"],),
        )
        loans = [
            {
                "id": row["id"],
                "amount": f"{float(row['amount'] or 0):,.0f}",
                "interest_rate": str(row.get("interest_rate") or 0),
                "duration_months": row["duration_months"],
                "status": row["status"],
                "disbursement_date": str(row.get("disbursement_date") or ""),
            }
            for row in cursor.fetchall()
        ]
        return {"applications": applications, "loans": loans}
    except mysql.connector.Error as error:
        print(f"Mobile customer loans error: {error}")
        return {"error": "Unable to load loan information."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/insurance/products", methods=["GET"])
def mobile_insurance_products():
    if session.get("role") != "customer":
        return {"error": "Customer sign-in required."}, 403

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, name, category, coverage, premium, duration
            FROM insurance_products
            WHERE status = 'active'
            ORDER BY id DESC
            """
        )
        products = cursor.fetchall()
        cursor.execute(
            """
            SELECT policy_id, status
            FROM customer_policies
            WHERE customer_id = %s
              AND status IN ('pending', 'active')
            """,
            (session["user_id"],),
        )
        policy_status = {
            row["policy_id"]: row["status"]
            for row in cursor.fetchall()
        }
        return {
            "products": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "category": row["category"],
                    "coverage": row["coverage"],
                    "premium": f"{float(row['premium'] or 0):,.0f}",
                    "duration": row["duration"],
                    "application_status": policy_status.get(row["id"]),
                }
                for row in products
            ]
        }
    except mysql.connector.Error as error:
        print(f"Mobile insurance products error: {error}")
        return {"error": "Unable to load insurance products."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/insurance/products/<int:policy_id>/apply", methods=["POST"])
def mobile_apply_for_policy(policy_id):
    if session.get("role") != "customer":
        return {"error": "Customer sign-in required."}, 403

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id FROM insurance_products WHERE id = %s AND status = 'active'",
            (policy_id,),
        )
        if cursor.fetchone() is None:
            return {"error": "That insurance product is unavailable."}, 404

        cursor.execute(
            """
            SELECT id
            FROM customer_policies
            WHERE customer_id = %s AND policy_id = %s
              AND status IN ('pending', 'active')
            LIMIT 1
            """,
            (session["user_id"], policy_id),
        )
        if cursor.fetchone() is not None:
            return {"error": "You already have an application or policy for this product."}, 409

        cursor.execute(
            """
            INSERT INTO customer_policies (customer_id, policy_id, status)
            VALUES (%s, %s, 'pending')
            """,
            (session["user_id"], policy_id),
        )
        db.commit()
        return {"ok": True, "application_id": cursor.lastrowid}, 201
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Mobile insurance application error: {error}")
        return {"error": "The insurance application could not be submitted."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/bank/loan-applications", methods=["GET"])
def mobile_bank_loan_applications():
    if session.get("role") != "bank":
        return {"error": "Bank sign-in required."}, 403

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT la.id, la.amount, la.purpose, la.duration_months, la.status,
                   la.application_date, u.name AS customer_name
            FROM loan_applications AS la
            INNER JOIN users AS u ON u.id = la.customer_id
            WHERE la.status IN ('pending', 'under_review', 'approved')
            ORDER BY la.application_date DESC, la.id DESC
            """
        )
        applications = [
            {
                "id": row["id"],
                "amount": f"{float(row['amount'] or 0):,.0f}",
                "purpose": row["purpose"],
                "duration_months": row["duration_months"],
                "status": row["status"],
                "application_date": str(row.get("application_date") or ""),
                "customer_name": row["customer_name"],
            }
            for row in cursor.fetchall()
        ]
        return {"applications": applications}
    except mysql.connector.Error as error:
        print(f"Mobile bank applications error: {error}")
        return {"error": "Unable to load loan applications."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/bank/loan-applications/<int:application_id>/decision", methods=["POST"])
def mobile_bank_loan_decision(application_id):
    if session.get("role") != "bank":
        return {"error": "Bank sign-in required."}, 403

    payload = request.get_json(silent=True)
    action = payload.get("action", "") if isinstance(payload, dict) else ""
    statuses = {"review": "under_review", "approve": "approved", "reject": "rejected"}
    status = statuses.get(action)
    if status is None:
        return {"error": "Choose a valid application decision."}, 400

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE loan_applications
            SET status = %s
            WHERE id = %s AND status IN ('pending', 'under_review')
            """,
            (status, application_id),
        )
        if cursor.rowcount == 0:
            db.rollback()
            return {"error": "Application not found or already finalized."}, 409
        db.commit()
        return {"ok": True, "status": status}
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Mobile bank loan decision error: {error}")
        return {"error": "The application decision could not be saved."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/bank/loan-applications/<int:application_id>/disburse", methods=["POST"])
def mobile_bank_disburse_loan(application_id):
    if session.get("role") != "bank":
        return {"error": "Bank sign-in required."}, 403

    payload = request.get_json(silent=True)
    try:
        interest_rate = float(payload.get("interest_rate", "")) if isinstance(payload, dict) else float("nan")
    except (TypeError, ValueError):
        interest_rate = float("nan")
    if not math.isfinite(interest_rate) or not 0 <= interest_rate <= 100:
        return {"error": "Interest rate must be between 0 and 100."}, 400

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT customer_id, amount, duration_months, status
            FROM loan_applications
            WHERE id = %s
            """,
            (application_id,),
        )
        application = cursor.fetchone()
        if application is None or application["status"] != "approved":
            return {"error": "Only approved applications can be disbursed."}, 409

        cursor.execute("SELECT id FROM loans WHERE application_id = %s", (application_id,))
        if cursor.fetchone() is not None:
            return {"error": "This application has already been disbursed."}, 409

        cursor.execute(
            """
            INSERT INTO loans
                (application_id, customer_id, bank_id, amount, interest_rate,
                 duration_months, disbursement_date)
            VALUES (%s, %s, %s, %s, %s, %s, CURDATE())
            """,
            (
                application_id,
                application["customer_id"],
                session["user_id"],
                application["amount"],
                interest_rate,
                application["duration_months"],
            ),
        )
        db.commit()
        return {"ok": True, "loan_id": cursor.lastrowid}, 201
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Mobile loan disbursement error: {error}")
        return {"error": "The loan could not be disbursed."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/insurer/policy-applications", methods=["GET"])
def mobile_insurer_policy_applications():
    if session.get("role") != "insurer":
        return {"error": "Insurer sign-in required."}, 403

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT cp.id, cp.created_at, cp.status,
                   u.name AS customer_name, ip.name AS policy_name,
                   ip.category, ip.premium, ip.duration
            FROM customer_policies AS cp
            INNER JOIN users AS u ON u.id = cp.customer_id
            INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id
            WHERE cp.status = 'pending'
            ORDER BY cp.created_at ASC
            """
        )
        applications = [
            {
                "id": row["id"],
                "customer_name": row["customer_name"],
                "policy_name": row["policy_name"],
                "category": row["category"],
                "premium": f"{float(row['premium'] or 0):,.0f}",
                "duration": row["duration"],
                "created_at": str(row.get("created_at") or ""),
            }
            for row in cursor.fetchall()
        ]
        return {"applications": applications}
    except mysql.connector.Error as error:
        print(f"Mobile insurer policy queue error: {error}")
        return {"error": "Unable to load insurance applications."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/insurer/policy-applications/<int:application_id>/decision", methods=["POST"])
def mobile_insurer_policy_decision(application_id):
    if session.get("role") != "insurer":
        return {"error": "Insurer sign-in required."}, 403

    payload = request.get_json(silent=True)
    decision = payload.get("decision", "") if isinstance(payload, dict) else ""
    if decision not in {"approve", "reject"}:
        return {"error": "Select approve or reject."}, 400

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT cp.id, cp.status, ip.duration
            FROM customer_policies AS cp
            INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id
            WHERE cp.id = %s
            """,
            (application_id,),
        )
        application = cursor.fetchone()
        if application is None or application["status"] != "pending":
            return {"error": "This application is no longer pending."}, 409

        if decision == "reject":
            cursor.execute(
                "UPDATE customer_policies SET status = 'rejected' WHERE id = %s AND status = 'pending'",
                (application_id,),
            )
            resulting_status = "rejected"
        else:
            duration_match = re.search(r"(\d+)\s*(month|year)", str(application.get("duration") or ""), re.IGNORECASE)
            months = int(duration_match.group(1)) if duration_match else None
            if months and duration_match.group(2).lower().startswith("year"):
                months *= 12
            if months:
                cursor.execute(
                    """
                    UPDATE customer_policies
                    SET status = 'active', start_date = CURDATE(),
                        end_date = DATE_ADD(CURDATE(), INTERVAL %s MONTH)
                    WHERE id = %s AND status = 'pending'
                    """,
                    (months, application_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE customer_policies
                    SET status = 'active', start_date = CURDATE(), end_date = NULL
                    WHERE id = %s AND status = 'pending'
                    """,
                    (application_id,),
                )
            resulting_status = "active"

        if cursor.rowcount == 0:
            db.rollback()
            return {"error": "This application is no longer pending."}, 409
        db.commit()
        return {"ok": True, "status": resulting_status}
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Mobile insurer policy decision error: {error}")
        return {"error": "The policy decision could not be saved."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/insurer/claims", methods=["GET"])
def mobile_insurer_claims():
    if session.get("role") != "insurer":
        return {"error": "Insurer sign-in required."}, 403

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT c.id, c.description, c.claim_amount, c.status, c.created_at,
                   u.name AS customer_name, ip.name AS policy_name
            FROM claims AS c
            INNER JOIN users AS u ON u.id = c.customer_id
            INNER JOIN customer_policies AS cp ON cp.id = c.customer_policy_id
            INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id
            ORDER BY c.created_at DESC, c.id DESC
            """
        )
        claims = [
            {
                "id": row["id"],
                "description": row["description"],
                "claim_amount": f"{float(row['claim_amount'] or 0):,.0f}",
                "status": row["status"],
                "created_at": str(row.get("created_at") or ""),
                "customer_name": row["customer_name"],
                "policy_name": row["policy_name"],
            }
            for row in cursor.fetchall()
        ]
        return {"claims": claims}
    except mysql.connector.Error as error:
        print(f"Mobile insurer claims error: {error}")
        return {"error": "Unable to load claims."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/api/mobile/insurer/claims/<int:claim_id>/status", methods=["POST"])
def mobile_insurer_claim_status(claim_id):
    if session.get("role") != "insurer":
        return {"error": "Insurer sign-in required."}, 403

    payload = request.get_json(silent=True)
    status = payload.get("status", "") if isinstance(payload, dict) else ""
    if status not in {"submitted", "under_review", "approved", "rejected", "paid"}:
        return {"error": "Choose a valid claim status."}, 400

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE claims SET status = %s WHERE id = %s", (status, claim_id))
        if cursor.rowcount == 0:
            return {"error": "Claim not found or unchanged."}, 404
        db.commit()
        return {"ok": True, "status": status}
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Mobile insurer claim update error: {error}")
        return {"error": "The claim status could not be saved."}, 503
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()


    flash(
        "You have been logged out.",
        "success"
    )


    return redirect(
        url_for("index")
    )


# ============================================================
# CUSTOMER DASHBOARD
# ============================================================

@app.route("/farms", methods=["GET", "POST"])
def farms():

    if session.get("role") != "customer":
        return redirect(url_for("login"))

    db = None
    cursor = None

    if request.method == "POST":
        farm_name = request.form.get("farm_name", "").strip()
        region = request.form.get("region", "").strip()
        district = request.form.get("district", "").strip()
        ward = request.form.get("ward", "").strip()
        crop_type = request.form.get("crop_type", "").strip()

        try:
            farm_size = float(request.form.get("farm_size", "0") or 0)
        except ValueError:
            farm_size = -1

        if not all((farm_name, region, district, ward)):
            flash("Farm name, region, district, and ward are required.", "danger")
            return redirect(url_for("farms"))

        if farm_size < 0:
            flash("Farm size cannot be negative.", "danger")
            return redirect(url_for("farms"))

        location_result = geocode_location(region, district, ward)
        if not location_result:
            flash("We could not locate this farm. Check the region, district, and ward.", "danger")
            return redirect(url_for("farms"))

        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                """
                INSERT INTO farms
                (user_id, farm_name, region, district, ward, crop_type,
                 farm_size, latitude, longitude, location_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session["user_id"],
                    farm_name,
                    region,
                    district,
                    ward,
                    crop_type,
                    farm_size,
                    location_result["latitude"],
                    location_result["longitude"],
                    location_result["display_name"],
                ),
            )
            db.commit()
            flash(f"{farm_name} was added to your farm workspace.", "success")
        except mysql.connector.Error as error:
            if db is not None:
                db.rollback()
            print(f"Farm registration database error: {error}")
            flash("The farm could not be saved. Run the customer farms migration first.", "danger")
        finally:
            if cursor is not None:
                cursor.close()
            if db is not None:
                db.close()

        return redirect(url_for("farms"))

    farm_rows = []
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT f.*,
                     ra.overall_score
            FROM farms AS f
            LEFT JOIN risk_assessments AS ra
              ON ra.farm_id = f.id
             AND ra.id = (
                 SELECT MAX(ra2.id)
                 FROM risk_assessments AS ra2
                 WHERE ra2.farm_id = f.id
             )
            WHERE f.user_id = %s
              AND f.status = 'active'
            ORDER BY f.created_at DESC, f.id DESC
            """,
            (session["user_id"],),
        )
        farm_rows = cursor.fetchall()
    except mysql.connector.Error as error:
        print(f"Farm workspace database error: {error}")
        flash("Unable to load your farms. Run the customer farms migration first.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template("farms.html", farms=farm_rows)

@app.route("/dashboard")
def dashboard():

    if session.get("role") != "customer":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None


    risk = None


    total_applications = 0

    pending_applications = 0

    approved_applications = 0

    rejected_applications = 0

    active_loans = 0


    recent_applications = []

    farms = []


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT *
            FROM risk_assessments
            WHERE customer_id = %s
            ORDER BY id DESC
            LIMIT 1
        """, (
            session["user_id"],
        ))


        risk = cursor.fetchone()


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loan_applications
            WHERE customer_id = %s
        """, (
            session["user_id"],
        ))


        total_applications = (
            cursor.fetchone()["total"] or 0
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loan_applications
            WHERE customer_id = %s
            AND status = 'pending'
        """, (
            session["user_id"],
        ))


        pending_applications = (
            cursor.fetchone()["total"] or 0
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loan_applications
            WHERE customer_id = %s
            AND status = 'approved'
        """, (
            session["user_id"],
        ))


        approved_applications = (
            cursor.fetchone()["total"] or 0
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loan_applications
            WHERE customer_id = %s
            AND status = 'rejected'
        """, (
            session["user_id"],
        ))


        rejected_applications = (
            cursor.fetchone()["total"] or 0
        )


        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loans
            WHERE customer_id = %s
            AND status = 'active'
        """, (
            session["user_id"],
        ))


        active_loans = (
            cursor.fetchone()["total"] or 0
        )


        cursor.execute("""
            SELECT
                id,
                amount,
                purpose,
                duration_months,
                status,
                application_date
            FROM loan_applications
            WHERE customer_id = %s
            ORDER BY application_date DESC, id DESC
            LIMIT 10
        """, (
            session["user_id"],
        ))


        recent_applications = (
            cursor.fetchall()
        )

        cursor.execute("""
            SELECT f.*,
                     ra.overall_score
            FROM farms AS f
            LEFT JOIN risk_assessments AS ra
              ON ra.farm_id = f.id
             AND ra.id = (
                 SELECT MAX(ra2.id)
                 FROM risk_assessments AS ra2
                 WHERE ra2.farm_id = f.id
             )
            WHERE f.user_id = %s
              AND f.status = 'active'
            ORDER BY f.created_at DESC, f.id DESC
            LIMIT 6
        """, (
            session["user_id"],
        ))

        farms = cursor.fetchall()


    except mysql.connector.Error as error:

        print(
            f"Customer dashboard database error: {error}"
        )


        flash(
            "Unable to load your dashboard information.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "dashboard.html",

        risk=risk,

        total_applications=
            total_applications,

        pending_applications=
            pending_applications,

        approved_applications=
            approved_applications,

        rejected_applications=
            rejected_applications,

        active_loans=
            active_loans,

        recent_applications=
            recent_applications,

        farms=farms
    )


# ============================================================
# CUSTOMER LOAN APPLICATION
# ============================================================

@app.route(
    "/loans/apply",
    methods=["GET", "POST"]
)
def loan_apply():

    if session.get("role") != "customer":

        return redirect(
            url_for("login")
        )


    if request.method == "POST":

        try:

            amount = float(
                request.form.get(
                    "amount",
                    "0"
                )
            )


            duration_months = int(
                request.form.get(
                    "duration_months",
                    "0"
                )
            )


        except ValueError:

            flash(
                "Enter a valid loan amount and repayment duration.",
                "danger"
            )


            return redirect(
                url_for("loan_apply")
            )


        purpose = request.form.get(
            "purpose",
            ""
        ).strip()


        if (

            amount < 1000

            or duration_months not in {
                3,
                6,
                9,
                12,
                18,
                24
            }

            or not purpose
        ):

            flash(
                "Provide a valid amount, purpose, and repayment duration.",
                "danger"
            )


            return redirect(
                url_for("loan_apply")
            )


        db = None
        cursor = None


        try:

            db = get_db()

            cursor = db.cursor()


            cursor.execute("""
                INSERT INTO loan_applications
                (
                    customer_id,
                    amount,
                    purpose,
                    duration_months,
                    status
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                session["user_id"],
                amount,
                purpose,
                duration_months,
                "pending"
            ))


            db.commit()


            flash(
                "Your loan application has been submitted "
                "and is now pending bank review.",
                "success"
            )


            return redirect(
                url_for("my_loans")
            )


        except mysql.connector.Error as error:

            if db is not None:
                db.rollback()


            print(
                f"Loan application database error: {error}"
            )


            flash(
                "Your application could not be submitted. "
                "Please try again.",
                "danger"
            )


        finally:

            if cursor is not None:
                cursor.close()

            if db is not None:
                db.close()


    return render_template(
        "loan_apply.html"
    )


# ============================================================
# CUSTOMER MY LOANS
# ============================================================

@app.route("/my-loans")
def my_loans():

    if session.get("role") != "customer":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None


    applications = []

    loans = []


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT *
            FROM loan_applications
            WHERE customer_id = %s
            ORDER BY application_date DESC, id DESC
        """, (
            session["user_id"],
        ))


        applications = cursor.fetchall()


        cursor.execute("""
            SELECT
                loans.*,
                users.name AS bank_name
            FROM loans
            LEFT JOIN users
                ON loans.bank_id = users.id
            WHERE loans.customer_id = %s
            ORDER BY loans.id DESC
        """, (
            session["user_id"],
        ))


        loans = cursor.fetchall()


    except mysql.connector.Error as error:

        print(
            f"My loans database error: {error}"
        )


        flash(
            "Unable to load your loan information.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "my_loans.html",

        applications=applications,

        loans=loans
    )


# ============================================================
# CUSTOMER RISK ASSESSMENT
# ============================================================

@app.route(
    "/assessment",
    methods=["GET", "POST"]
)
def assessment():

    if session.get("role") != "customer":

        return redirect(
            url_for("login")
        )


    if request.method == "POST":

        db = None
        cursor = None

        farm_id = request.form.get("farm_id", "").strip()
        farm_id = int(farm_id) if farm_id else None


        try:

            # ==================================================
            # CUSTOMER PROFILE
            # ==================================================

            customer_type = request.form.get(
                "customer_type",
                ""
            ).strip()


            region = request.form.get(
                "region",
                ""
            ).strip()


            district = request.form.get(
                "district",
                ""
            ).strip()


            ward = request.form.get(
                "ward",
                ""
            ).strip()


            crop_type = request.form.get(
                "crop_type",
                ""
            ).strip()


            business_type = request.form.get(
                "business_type",
                ""
            ).strip()


            # ==================================================
            # NUMERICAL PROFILE VALUES
            # ==================================================

            farm_size = float(
                request.form.get(
                    "farm_size",
                    0
                ) or 0
            )


            stock_value = float(
                request.form.get(
                    "stock_value",
                    0
                ) or 0
            )


            # ==================================================
            # VALIDATE CUSTOMER TYPE
            # ==================================================

            if customer_type not in {
                "farmer",
                "informal_business"
            }:

                flash(
                    "Please select a valid customer type.",
                    "danger"
                )


                return redirect(
                    url_for("assessment")
                )


            # ==================================================
            # VALIDATE LOCATION
            # ==================================================

            if not region:

                flash(
                    "Please enter your Region.",
                    "danger"
                )


                return redirect(
                    url_for("assessment")
                )


            if not district:

                flash(
                    "Please enter your District.",
                    "danger"
                )


                return redirect(
                    url_for("assessment")
                )


            if not ward:

                flash(
                    "Please enter your Ward.",
                    "danger"
                )


                return redirect(
                    url_for("assessment")
                )


            # ==================================================
            # VALIDATE NUMBERS
            # ==================================================

            if farm_size < 0:

                flash(
                    "Farm size cannot be negative.",
                    "danger"
                )


                return redirect(
                    url_for("assessment")
                )


            if stock_value < 0:

                flash(
                    "Stock value cannot be negative.",
                    "danger"
                )


                return redirect(
                    url_for("assessment")
                )


            # ==================================================
            # LOCATION COORDINATES
            # ==================================================

            print(
                "========================================"
            )

            print(
                "GEOCODING CUSTOMER LOCATION"
            )

            print(
                "========================================"
            )


            gps_latitude = request.form.get(
                "gps_latitude",
                ""
            ).strip()

            gps_longitude = request.form.get(
                "gps_longitude",
                ""
            ).strip()

            if gps_latitude or gps_longitude:

                if not gps_latitude or not gps_longitude:
                    flash(
                        "Location detection was incomplete. Please detect again or enter your location manually.",
                        "danger"
                    )
                    return redirect(url_for("assessment"))

                try:
                    latitude = float(gps_latitude)
                    longitude = float(gps_longitude)
                except ValueError:
                    flash(
                        "The detected location coordinates are invalid. Please detect your location again.",
                        "danger"
                    )
                    return redirect(url_for("assessment"))

                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    flash(
                        "The detected location coordinates are outside valid ranges.",
                        "danger"
                    )
                    return redirect(url_for("assessment"))

                location_result = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "display_name": request.form.get(
                        "osm_display_name",
                        ""
                    ).strip() or f"{ward}, {district}, {region}, Tanzania"
                }
            else:
                location_result = geocode_location(
                    region,
                    district,
                    ward
                )


            if not location_result:

                flash(
                    "We could not identify your location. "
                    "Please check the Region, District and Ward.",
                    "danger"
                )


                return redirect(
                    url_for("assessment")
                )


            latitude = (
                location_result["latitude"]
            )


            longitude = (
                location_result["longitude"]
            )


            location_address = (
                location_result["display_name"]
            )


            print(
                f"Location: {location_address}"
            )

            print(
                f"Latitude: {latitude}"
            )

            print(
                f"Longitude: {longitude}"
            )


            # ==================================================
            # OPEN-METEO
            # ==================================================

            print(
                "========================================"
            )

            print(
                "GETTING CLIMATE DATA"
            )

            print(
                "========================================"
            )


            cached_preview = session.get("climate_risk_preview", {})
            preview_matches_location = (
                cached_preview.get("customer_id") == session.get("user_id")
                and abs(cached_preview.get("latitude", 999) - latitude) < 0.000001
                and abs(cached_preview.get("longitude", 999) - longitude) < 0.000001
                and cached_preview.get("scores")
            )

            if preview_matches_location:
                climate_scores = cached_preview["scores"]
                session.pop("climate_risk_preview", None)
            else:
                session.pop("climate_risk_preview", None)
                climate = get_climate_data(latitude, longitude)

                if not climate:
                    flash(
                        "Climate information could not be retrieved "
                        "for this location. Please try again.",
                        "danger"
                    )
                    return redirect(url_for("assessment"))

                # Calculate local climate indicators for the resolved coordinates.
                climate_scores = calculate_climate_scores(climate)


            if not climate_scores:

                flash(
                    "There was not enough climate information "
                    "to calculate your risk.",
                    "danger"
                )


                return redirect(
                    url_for("assessment")
                )


            drought = (
                climate_scores["drought_score"]
            )


            flood = (
                climate_scores["flood_score"]
            )


            rainfall = (
                climate_scores["rainfall_score"]
            )

            pest_pressure = climate_scores["pest_pressure_score"]


            climate_summary = (
                climate_scores["summary"]
            )


            print(
                "========================================"
            )

            print(
                "CLIMATE RISK RESULTS"
            )

            print(
                f"Drought Risk: {drought}%"
            )

            print(
                f"Flood Risk: {flood}%"
            )

            print(
                f"Rainfall Risk: {rainfall}%"
            )

            print(
                f"Average Temperature: "
                f"{climate_summary['average_temperature']} C"
            )

            print(
                f"Total Precipitation: "
                f"{climate_summary['total_precipitation']} mm"
            )

            print(
                f"Dry Days: "
                f"{climate_summary['dry_days']}"
            )

            print(
                f"Heavy Rain Days: "
                f"{climate_summary['heavy_rain_days']}"
            )

            print(
                "========================================"
            )


            # ==================================================
            # OVERALL RISK
            # ==================================================

            overall = calculate_risk(

                drought,

                flood,

                rainfall
            )


            # ==================================================
            # DATABASE
            # ==================================================

            db = get_db()

            cursor = db.cursor()

            if farm_id is not None:
                cursor.execute("""
                    SELECT id
                    FROM farms
                                        WHERE id = %s
                                            AND user_id = %s
                      AND status = 'active'
                    LIMIT 1
                """, (
                    farm_id,
                    session["user_id"],
                ))

                if cursor.fetchone() is None:
                    flash("That farm is not available in your workspace.", "danger")
                    return redirect(url_for("farms"))


            # ==================================================
            # SAVE CUSTOMER PROFILE
            # ==================================================

            cursor.execute("""
                INSERT INTO customer_profiles
                (
                    user_id,
                    customer_type,
                    location,
                    crop_type,
                    farm_size,
                    business_type,
                    stock_value,
                    latitude,
                    longitude,
                    location_address
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (

                session["user_id"],

                customer_type,

                f"{ward}, {district}, {region}",

                crop_type,

                farm_size,

                business_type,

                stock_value,

                latitude,

                longitude,

                location_address
            ))


            # ==================================================
            # SAVE RISK ASSESSMENT
            # ==================================================

            cursor.execute("""
                INSERT INTO risk_assessments
                (
                    customer_id,
                    farm_id,
                    drought_score,
                    flood_score,
                    rainfall_score,
                    pest_pressure_score,
                    overall_score
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (

                session["user_id"],

                farm_id,

                drought,

                flood,

                rainfall,

                pest_pressure,

                overall
            ))


            # ==================================================
            # GENERATE AI RECOMMENDATIONS
            # ==================================================

            recommendations = (
                generate_recommendations(

                    drought,

                    flood,

                    rainfall,

                    customer_type,

                    pest_pressure
                )
            )


            # ==================================================
            # SAVE RECOMMENDATIONS
            # ==================================================

            for recommendation in recommendations:

                cursor.execute("""
                    SELECT id
                    FROM insurance_products
                    WHERE name = %s
                    AND status = 'active'
                    LIMIT 1
                """, (
                    recommendation["policy"],
                ))


                policy = cursor.fetchone()


                if policy:

                    cursor.execute("""
                        INSERT INTO recommendations
                        (
                            customer_id,
                            policy_id,
                            risk_score,
                            relevance,
                            reason
                        )
                        VALUES
                        (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                    """, (

                        session["user_id"],

                        policy[0],

                        recommendation["score"],

                        recommendation["relevance"],

                        recommendation["reason"]
                    ))


            # Commit the profile, assessment, and recommendations together.
            # A recommendation write failure must not leave a partial save.
            db.commit()


            # ==================================================
            # SAVE CLIMATE INFORMATION IN SESSION
            # ==================================================
            #
            # This allows the recommendations/dashboard page
            # to access the latest calculated climate information
            # without adding new database columns.
            # ==================================================

            session["latest_climate"] = {

                "latitude": latitude,

                "longitude": longitude,

                "location_address":
                    location_address,

                "drought_score":
                    drought,

                "flood_score":
                    flood,

                "rainfall_score":
                    rainfall,

                "pest_pressure_score":
                    pest_pressure,

                "overall_score":
                    overall,

                "average_temperature":
                    climate_summary[
                        "average_temperature"
                    ],

                "total_precipitation":
                    climate_summary[
                        "total_precipitation"
                    ],

                "dry_days":
                    climate_summary[
                        "dry_days"
                    ],

                "heavy_rain_days":
                    climate_summary[
                        "heavy_rain_days"
                    ]
            }


            flash(
                "Risk assessment completed successfully. "
                "Your climate risk was calculated automatically "
                "from your location.",
                "success"
            )


            return redirect(
                url_for("recommendations")
            )


        except ValueError as error:

            if db is not None:
                db.rollback()


            print(
                f"Assessment value error: {error}"
            )


            flash(
                "Please enter valid numerical information.",
                "danger"
            )


            return redirect(
                url_for("assessment")
            )


        except mysql.connector.Error as error:

            if db is not None:
                db.rollback()


            print(
                f"Assessment database error: {error}"
            )


            flash(
                "Assessment could not be saved. "
                "Confirm assessment migrations 002, 003, and 004 are applied; "
                "the server console contains the database error detail.",
                "danger"
            )


            return redirect(
                url_for("assessment")
            )


        except requests.RequestException as error:

            if db is not None:
                db.rollback()


            print(
                f"External API error: {error}"
            )


            flash(
                "Unable to retrieve location or climate information.",
                "danger"
            )


            return redirect(
                url_for("assessment")
            )


        except Exception as error:

            if db is not None:
                db.rollback()


            print(
                f"Assessment error: {error}"
            )


            flash(
                "An unexpected error occurred during "
                "your risk assessment.",
                "danger"
            )


            return redirect(
                url_for("assessment")
            )


        finally:

            if cursor is not None:
                cursor.close()


            if db is not None:
                db.close()


    selected_farm = None
    selected_farm_id = request.args.get("farm_id", "").strip()

    if selected_farm_id:
        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            cursor.execute("""
                SELECT *
                FROM farms
                                WHERE id = %s
                                    AND user_id = %s
                  AND status = 'active'
                LIMIT 1
            """, (
                int(selected_farm_id),
                session["user_id"],
            ))
            selected_farm = cursor.fetchone()
        except (ValueError, mysql.connector.Error) as error:
            print(f"Selected farm lookup error: {error}")
        finally:
            if cursor is not None:
                cursor.close()
            if db is not None:
                db.close()

    return render_template(
        "assessment.html",
        selected_farm=selected_farm
    )


# ============================================================
# CUSTOMER INSURANCE RECOMMENDATIONS
# ============================================================

@app.route("/recommendations")
def recommendations():

    if session.get("role") != "customer":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None


    data = []


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                recommendations.*,
                insurance_products.name,
                insurance_products.id AS product_id,
                insurance_products.category,
                insurance_products.coverage,
                insurance_products.premium,
                insurance_products.duration
            FROM recommendations

            JOIN insurance_products
                ON recommendations.policy_id =
                   insurance_products.id

            WHERE recommendations.customer_id = %s

            ORDER BY recommendations.risk_score DESC
        """, (
            session["user_id"],
        ))


        data = cursor.fetchall()


    except mysql.connector.Error as error:

        print(
            f"Recommendations database error: {error}"
        )


        flash(
            "Unable to load recommendations.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "recommendations.html",

        recommendations=data,
        climate=session.get("latest_climate")
    )


# ============================================================
# INSURANCE POLICIES
# ============================================================

@app.route("/policies")
def policies():

    db = None
    cursor = None

    products = []
    customer_policy_status = {}


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT *
            FROM insurance_products
            WHERE status = 'active'
            ORDER BY id DESC
        """)


        products = cursor.fetchall()

        if session.get("role") == "customer":
            cursor.execute(
                """
                SELECT policy_id, status
                FROM customer_policies
                WHERE customer_id = %s
                  AND status IN ('pending', 'active')
                """,
                (session["user_id"],)
            )
            customer_policy_status = {
                row["policy_id"]: row["status"]
                for row in cursor.fetchall()
            }


    except mysql.connector.Error as error:

        print(
            f"Policies database error: {error}"
        )


        flash(
            "Unable to load insurance policies.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "policies.html",

        products=products,
        customer_policy_status=customer_policy_status
    )


@app.route("/policies/<int:policy_id>/apply", methods=["POST"])
def apply_for_policy(policy_id):

    if session.get("role") != "customer":
        flash("Log in as a customer to apply for insurance.", "warning")
        return redirect(url_for("login"))

    db = None
    cursor = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id
            FROM insurance_products
            WHERE id = %s AND status = 'active'
            """,
            (policy_id,)
        )
        product = cursor.fetchone()

        if product is None:
            flash("That insurance product is not currently available.", "warning")
            return redirect(url_for("policies"))

        cursor.execute(
            """
            SELECT id
            FROM customer_policies
            WHERE customer_id = %s
              AND policy_id = %s
              AND status IN ('pending', 'active')
            LIMIT 1
            """,
            (session["user_id"], policy_id)
        )
        if cursor.fetchone() is not None:
            flash("You already have an active application or policy for this product.", "info")
            return redirect(url_for("my_policies"))

        cursor.execute(
            """
            INSERT INTO customer_policies (customer_id, policy_id, status)
            VALUES (%s, %s, 'pending')
            """,
            (session["user_id"], policy_id)
        )
        db.commit()
        flash("Your insurance application was sent to the insurer for review.", "success")
        return redirect(url_for("my_policies"))

    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Insurance application database error: {error}")
        flash("Your insurance application could not be submitted. Please try again.", "danger")
        return redirect(url_for("policies"))

    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


@app.route("/my-policies")
def my_policies():

    if session.get("role") != "customer":
        return redirect(url_for("login"))

    db = None
    cursor = None
    policies = []

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                cp.id,
                cp.policy_id,
                cp.start_date,
                cp.end_date,
                cp.status,
                cp.created_at,
                ip.name,
                ip.category,
                ip.coverage,
                ip.premium,
                ip.duration
            FROM customer_policies AS cp
            INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id
            WHERE cp.customer_id = %s
            ORDER BY cp.id DESC
            """,
            (session["user_id"],)
        )
        policies = cursor.fetchall()
    except mysql.connector.Error as error:
        print(f"Customer policies database error: {error}")
        flash("Unable to load your insurance policies.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template("my_policies.html", policies=policies)


# ============================================================
# BANK DASHBOARD
# ============================================================

@app.route("/bank/dashboard")
def bank_dashboard():

    if session.get("role") != "bank":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None


    total_customers = 0

    pending_loans = 0

    approved_loans = 0

    active_loans = 0

    recent_applications = []


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT COUNT(*) AS total_customers
            FROM users
            WHERE role = 'customer'
        """)


        total_customers = (
            cursor.fetchone()[
                "total_customers"
            ]
        )


        cursor.execute("""
            SELECT COUNT(*) AS pending_loans
            FROM loan_applications
            WHERE status IN (
                'pending',
                'under_review'
            )
        """)


        pending_loans = (
            cursor.fetchone()[
                "pending_loans"
            ]
        )


        cursor.execute("""
            SELECT COUNT(*) AS approved_loans
            FROM loan_applications
            WHERE status = 'approved'
        """)


        approved_loans = (
            cursor.fetchone()[
                "approved_loans"
            ]
        )


        cursor.execute("""
            SELECT COUNT(*) AS active_loans
            FROM loans
            WHERE status = 'active'
        """)


        active_loans = (
            cursor.fetchone()[
                "active_loans"
            ]
        )


        cursor.execute("""
            SELECT
                loan_applications.id,
                loan_applications.amount,
                loan_applications.purpose,
                loan_applications.duration_months,
                loan_applications.status,
                loan_applications.application_date,
                users.name AS customer_name

            FROM loan_applications

            JOIN users
                ON loan_applications.customer_id =
                   users.id

            ORDER BY loan_applications.id DESC

            LIMIT 10
        """)


        recent_applications = (
            cursor.fetchall()
        )


    except mysql.connector.Error as error:

        print(
            f"Bank dashboard database error: {error}"
        )


        flash(
            "Unable to load bank dashboard data.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "bank/dashboard.html",

        total_customers=
            total_customers,

        pending_loans=
            pending_loans,

        approved_loans=
            approved_loans,

        active_loans=
            active_loans,

        recent_applications=
            recent_applications
    )


# ============================================================
# BANK CUSTOMERS
# ============================================================

@app.route("/bank/customers")
def bank_customers():

    if session.get("role") != "bank":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None

    customers = []


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                u.id,
                u.name,
                u.email,
                cp.location,
                cp.customer_type,
                cp.crop_type,
                cp.business_type,
                risk.overall_score AS overall_risk

            FROM users AS u

            LEFT JOIN customer_profiles AS cp
                ON cp.user_id = u.id

            LEFT JOIN (

                SELECT
                    ra.customer_id,
                    ra.overall_score

                FROM risk_assessments AS ra

                INNER JOIN (

                    SELECT
                        customer_id,
                        MAX(id) AS latest_id

                    FROM risk_assessments

                    GROUP BY customer_id

                ) AS latest

                    ON latest.latest_id = ra.id

            ) AS risk

                ON risk.customer_id = u.id

            WHERE u.role = 'customer'

            ORDER BY u.id DESC
        """)


        customers = cursor.fetchall()


    except mysql.connector.Error as error:

        print(
            f"Bank customers database error: {error}"
        )


        flash(
            "Unable to load customers.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "bank/customers.html",

        customers=customers
    )


# ============================================================
# BANK LOAN APPLICATIONS
# ============================================================

@app.route("/bank/loan-applications")
def bank_loan_applications():

    if session.get("role") != "bank":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None

    applications = []


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                la.*,
                u.name AS customer_name,
                u.email,
                u.phone,
                cp.location,
                cp.customer_type,
                cp.crop_type,
                cp.business_type

            FROM loan_applications AS la

            INNER JOIN users AS u
                ON u.id = la.customer_id

            LEFT JOIN customer_profiles AS cp
                ON cp.user_id = u.id

            ORDER BY la.application_date DESC
        """)


        applications = cursor.fetchall()


    except mysql.connector.Error as error:

        print(
            f"Bank loan applications error: {error}"
        )


        flash(
            "Unable to load loan applications.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "bank/loan_applications.html",

        applications=applications
    )


# ============================================================
# BANK REVIEW LOAN
# ============================================================

@app.route(
    "/bank/loan-applications/<int:application_id>",
    methods=["GET", "POST"]
)
def review_loan(application_id):

    if session.get("role") != "bank":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        if request.method == "POST":

            action = request.form.get(
                "action",
                ""
            )


            statuses = {

                "review":
                    "under_review",

                "approve":
                    "approved",

                "reject":
                    "rejected"
            }


            status = statuses.get(
                action
            )


            if status is None:

                flash(
                    "Choose a valid application decision.",
                    "danger"
                )


            else:

                cursor.execute("""
                    UPDATE loan_applications
                    SET status = %s
                    WHERE id = %s
                    AND status IN (
                        'pending',
                        'under_review'
                    )
                """, (
                    status,
                    application_id
                ))


                db.commit()


                if cursor.rowcount:

                    if status == "approved":

                        flash(
                            "Loan application approved successfully.",
                            "success"
                        )


                    elif status == "rejected":

                        flash(
                            "Loan application rejected.",
                            "warning"
                        )


                    else:

                        flash(
                            "Loan application moved to review.",
                            "info"
                        )


                else:

                    flash(
                        "Application was not found or "
                        "is already finalized.",
                        "warning"
                    )


            return redirect(
                url_for(
                    "review_loan",
                    application_id=application_id
                )
            )


        cursor.execute("""
            SELECT
                la.*,
                u.name AS customer_name,
                u.email,
                u.phone,
                cp.location,
                cp.customer_type,
                cp.crop_type,
                cp.business_type,
                risk.overall_score AS overall_risk,
                risk.drought_score AS drought_risk,
                risk.flood_score AS flood_risk

            FROM loan_applications AS la

            INNER JOIN users AS u
                ON u.id = la.customer_id

            LEFT JOIN customer_profiles AS cp
                ON cp.user_id = u.id

            LEFT JOIN (

                SELECT
                    ra.customer_id,
                    ra.overall_score,
                    ra.drought_score,
                    ra.flood_score

                FROM risk_assessments AS ra

                INNER JOIN (

                    SELECT
                        customer_id,
                        MAX(id) AS latest_id

                    FROM risk_assessments

                    GROUP BY customer_id

                ) AS latest

                    ON latest.latest_id = ra.id

            ) AS risk

                ON risk.customer_id = u.id

            WHERE la.id = %s
        """, (
            application_id,
        ))


        application = cursor.fetchone()


    except mysql.connector.Error as error:

        if db is not None:
            db.rollback()


        print(
            f"Review loan database error: {error}"
        )


        flash(
            "Unable to process the loan application.",
            "danger"
        )


        return redirect(
            url_for("bank_loan_applications")
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    if application is None:

        flash(
            "Loan application not found.",
            "warning"
        )


        return redirect(
            url_for("bank_loan_applications")
        )


    return render_template(

        "bank/review_loan.html",

        application=application
    )


# ============================================================
# BANK LOAN DISBURSEMENT
# ============================================================

@app.route(
    "/bank/loan-applications/<int:application_id>/disburse",
    methods=["POST"]
)
def disburse_loan(application_id):

    if session.get("role") != "bank":

        return redirect(
            url_for("login")
        )


    try:

        interest_rate = float(
            request.form.get(
                "interest_rate",
                ""
            )
        )


    except ValueError:

        flash(
            "Enter a valid interest rate.",
            "danger"
        )


        return redirect(
            url_for(
                "review_loan",
                application_id=application_id
            )
        )


    if not 0 <= interest_rate <= 100:

        flash(
            "Interest rate must be between 0 and 100.",
            "danger"
        )


        return redirect(
            url_for(
                "review_loan",
                application_id=application_id
            )
        )


    db = None
    cursor = None


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                customer_id,
                amount,
                duration_months,
                status

            FROM loan_applications

            WHERE id = %s
        """, (
            application_id,
        ))


        application = cursor.fetchone()


        if (

            application is None

            or application["status"] != "approved"
        ):

            flash(
                "Only approved applications can be disbursed.",
                "warning"
            )


        else:

            cursor.execute("""
                SELECT id
                FROM loans
                WHERE application_id = %s
            """, (
                application_id,
            ))


            existing_loan = (
                cursor.fetchone()
            )


            if existing_loan is not None:

                flash(
                    "This application has already been disbursed.",
                    "warning"
                )


            else:

                cursor.execute("""
                    INSERT INTO loans
                    (
                        application_id,
                        customer_id,
                        bank_id,
                        amount,
                        interest_rate,
                        duration_months,
                        disbursement_date
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        CURDATE()
                    )
                """, (

                    application_id,

                    application["customer_id"],

                    session["user_id"],

                    application["amount"],

                    interest_rate,

                    application["duration_months"]
                ))


                db.commit()


                flash(
                    "Loan disbursed successfully.",
                    "success"
                )


    except mysql.connector.Error as error:

        if db is not None:
            db.rollback()


        print(
            f"Loan disbursement error: {error}"
        )


        flash(
            "Loan could not be disbursed.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return redirect(

        url_for(
            "review_loan",
            application_id=application_id
        )
    )


# ============================================================
# BANK REPAYMENTS
# ============================================================

@app.route("/bank/repayments")
def bank_repayments():

    if session.get("role") != "bank":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None

    repayments = []


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                r.id,
                r.loan_id,
                r.amount,
                r.payment_date,
                r.status,
                l.amount AS loan_amount,
                u.name AS customer_name

            FROM repayments AS r

            INNER JOIN loans AS l
                ON l.id = r.loan_id

            INNER JOIN users AS u
                ON u.id = l.customer_id

            WHERE l.bank_id = %s

            ORDER BY
                r.payment_date DESC,
                r.id DESC
        """, (
            session["user_id"],
        ))


        repayments = cursor.fetchall()


    except mysql.connector.Error as error:

        print(
            f"Bank repayments database error: {error}"
        )


        flash(
            "Unable to load repayment records.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "bank/repayments.html",

        repayments=repayments
    )


# ============================================================
# BANK ADD REPAYMENT
# ============================================================

@app.route(
    "/bank/loan/<int:loan_id>/repayment",
    methods=["POST"]
)
def bank_add_repayment(loan_id):

    if session.get("role") != "bank":

        return redirect(
            url_for("login")
        )


    try:

        amount = float(
            request.form.get(
                "amount",
                "0"
            )
        )


    except ValueError:

        amount = 0


    if loan_id <= 0 or amount <= 0:

        flash(
            "Enter a valid loan ID and repayment amount.",
            "danger"
        )


        return redirect(
            url_for("bank_repayments")
        )


    db = None
    cursor = None


    try:

        db = get_db()

        cursor = db.cursor()


        cursor.execute("""
            SELECT id
            FROM loans
            WHERE id = %s
            AND bank_id = %s
            AND status = 'active'
        """, (

            loan_id,

            session["user_id"]
        ))


        if cursor.fetchone() is None:

            flash(
                "Active loan not found for this bank.",
                "warning"
            )


        else:

            cursor.execute("""
                INSERT INTO repayments
                (
                    loan_id,
                    amount,
                    payment_date
                )
                VALUES
                (
                    %s,
                    %s,
                    CURDATE()
                )
            """, (

                loan_id,

                amount
            ))


            db.commit()


            flash(
                "Repayment recorded successfully.",
                "success"
            )


    except mysql.connector.Error as error:

        if db is not None:
            db.rollback()


        print(
            f"Repayment database error: {error}"
        )


        flash(
            "Repayment could not be recorded.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return redirect(
        url_for("bank_repayments")
    )


# ============================================================
# INSURER DASHBOARD
# ============================================================

@app.route("/insurer/dashboard")
def insurer_dashboard():

    if session.get("role") != "insurer":

        return redirect(
            url_for("login")
        )


    db = None
    cursor = None


    total_customers = 0

    high_risk = 0

    profiles = 0

    active_policies = 0

    pending_policy_applications = 0

    recent_activity = []


    try:

        db = get_db()

        cursor = db.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT COUNT(*) AS total_customers
            FROM users
            WHERE role = 'customer'
        """)


        total_customers = (
            cursor.fetchone()[
                "total_customers"
            ]
        )


        cursor.execute("""
            SELECT COUNT(*) AS high_risk
            FROM risk_assessments
            WHERE overall_score >= 70
        """)


        high_risk = (
            cursor.fetchone()[
                "high_risk"
            ]
        )


        cursor.execute("""
            SELECT COUNT(*) AS total_profiles
            FROM customer_profiles
        """)


        profiles = (
            cursor.fetchone()[
                "total_profiles"
            ]
        )

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM customer_policies
            WHERE status = 'active'
        """)
        active_policies = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM customer_policies
            WHERE status = 'pending'
        """)
        pending_policy_applications = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT activity_type, activity_date, customer_name, detail, status
            FROM (
                SELECT
                    'Policy application' AS activity_type,
                    cp.created_at AS activity_date,
                    u.name AS customer_name,
                    ip.name AS detail,
                    cp.status AS status
                FROM customer_policies AS cp
                INNER JOIN users AS u ON u.id = cp.customer_id
                INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id

                UNION ALL

                SELECT
                    'Insurance claim' AS activity_type,
                    c.created_at AS activity_date,
                    u.name AS customer_name,
                    COALESCE(cp_policy.name, 'Customer policy') AS detail,
                    c.status AS status
                FROM claims AS c
                INNER JOIN users AS u ON u.id = c.customer_id
                LEFT JOIN customer_policies AS cp ON cp.id = c.customer_policy_id
                LEFT JOIN insurance_products AS cp_policy ON cp_policy.id = cp.policy_id

                UNION ALL

                SELECT
                    'Risk assessment' AS activity_type,
                    ra.assessment_date AS activity_date,
                    u.name AS customer_name,
                    CONCAT('Risk score ', ROUND(ra.overall_score), '%') AS detail,
                    CASE
                        WHEN ra.overall_score >= 70 THEN 'high risk'
                        WHEN ra.overall_score >= 40 THEN 'moderate risk'
                        ELSE 'low risk'
                    END AS status
                FROM risk_assessments AS ra
                INNER JOIN users AS u ON u.id = ra.customer_id
            ) AS activity_feed
            ORDER BY activity_date DESC
            LIMIT 12
        """)
        recent_activity = cursor.fetchall()


    except mysql.connector.Error as error:

        print(
            f"Insurer dashboard database error: {error}"
        )


        flash(
            "Unable to load insurer dashboard.",
            "danger"
        )


    finally:

        if cursor is not None:
            cursor.close()

        if db is not None:
            db.close()


    return render_template(

        "insurer/dashboard.html",

        total_customers=
            total_customers,

        high_risk=
            high_risk,

        profiles=
            profiles,

        active_policies=
            active_policies,

        pending_policy_applications=
            pending_policy_applications,

        recent_activity=recent_activity
    )


@app.route("/insurer/policy-applications")
def insurer_policy_applications():

    if session.get("role") != "insurer":
        return redirect(url_for("login"))

    db = None
    cursor = None
    applications = []

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                cp.id,
                cp.created_at,
                cp.status,
                u.name AS customer_name,
                u.email,
                u.phone,
                ip.name AS policy_name,
                ip.category,
                ip.premium,
                ip.duration
            FROM customer_policies AS cp
            INNER JOIN users AS u ON u.id = cp.customer_id
            INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id
            WHERE cp.status = 'pending'
            ORDER BY cp.created_at ASC
            """
        )
        applications = cursor.fetchall()
    except mysql.connector.Error as error:
        print(f"Insurer policy applications database error: {error}")
        flash("Unable to load insurance applications.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template(
        "insurer/policy_applications.html",
        applications=applications
    )


@app.route(
    "/insurer/policy-applications/<int:application_id>/decision",
    methods=["POST"]
)
def insurer_policy_application_decision(application_id):

    if session.get("role") != "insurer":
        return redirect(url_for("login"))

    decision = request.form.get("decision", "")
    if decision not in {"approve", "reject"}:
        flash("Select a valid application decision.", "danger")
        return redirect(url_for("insurer_policy_applications"))

    db = None
    cursor = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT cp.id, cp.status, ip.duration
            FROM customer_policies AS cp
            INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id
            WHERE cp.id = %s
            """,
            (application_id,)
        )
        application = cursor.fetchone()

        if application is None or application["status"] != "pending":
            flash("This insurance application is no longer pending.", "warning")
            return redirect(url_for("insurer_policy_applications"))

        if decision == "approve":
            duration = str(application.get("duration") or "")
            duration_match = re.search(
                r"(\d+)\s*(month|year)",
                duration,
                re.IGNORECASE
            )
            months = None
            if duration_match:
                months = int(duration_match.group(1))
                if duration_match.group(2).lower().startswith("year"):
                    months *= 12

            if months:
                cursor.execute(
                    """
                    UPDATE customer_policies
                    SET status = 'active',
                        start_date = CURDATE(),
                        end_date = DATE_ADD(CURDATE(), INTERVAL %s MONTH)
                    WHERE id = %s AND status = 'pending'
                    """,
                    (months, application_id)
                )
            else:
                cursor.execute(
                    """
                    UPDATE customer_policies
                    SET status = 'active', start_date = CURDATE(), end_date = NULL
                    WHERE id = %s AND status = 'pending'
                    """,
                    (application_id,)
                )
            flash("Insurance application approved and coverage activated.", "success")
        else:
            cursor.execute(
                """
                UPDATE customer_policies
                SET status = 'rejected'
                WHERE id = %s AND status = 'pending'
                """,
                (application_id,)
            )
            flash("Insurance application declined.", "info")

        db.commit()

    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Insurance application decision error: {error}")
        flash("The insurance application could not be updated.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return redirect(url_for("insurer_policy_applications"))


@app.route("/insurer/risk-profiles")
def insurer_risk_profiles():

    if session.get("role") != "insurer":
        return redirect(url_for("login"))

    db = None
    cursor = None
    customers = []

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                u.id,
                u.name,
                u.email,
                u.phone,
                cp.location,
                cp.customer_type,
                cp.crop_type,
                cp.business_type,
                cp.farm_size,
                cp.stock_value,
                ra.overall_score,
                ra.drought_score,
                ra.flood_score,
                ra.rainfall_score,
                ra.pest_pressure_score,
                ra.created_at AS assessment_date
            FROM users AS u
            LEFT JOIN (
                SELECT profile.*
                FROM customer_profiles AS profile
                INNER JOIN (
                    SELECT user_id, MAX(id) AS latest_id
                    FROM customer_profiles
                    GROUP BY user_id
                ) AS latest_profile ON latest_profile.latest_id = profile.id
            ) AS cp ON cp.user_id = u.id
            LEFT JOIN (
                SELECT assessment.*
                FROM risk_assessments AS assessment
                INNER JOIN (
                    SELECT customer_id, MAX(id) AS latest_id
                    FROM risk_assessments
                    GROUP BY customer_id
                ) AS latest_assessment ON latest_assessment.latest_id = assessment.id
            ) AS ra ON ra.customer_id = u.id
            WHERE u.role = 'customer'
            ORDER BY ra.overall_score DESC, u.name ASC
            """
        )
        customers = cursor.fetchall()
    except mysql.connector.Error as error:
        print(f"Insurer risk profiles database error: {error}")
        flash("Unable to load customer risk profiles.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template(
        "insurer/risk_profiles.html",
        customers=customers
    )


@app.route("/insurer/products", methods=["GET", "POST"])
def insurer_products():

    if session.get("role") != "insurer":
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        coverage = request.form.get("coverage", "").strip()
        duration = request.form.get("duration", "").strip()
        status = request.form.get("status", "active")
        product_id = request.form.get("product_id", "").strip()
        premium_rate_input = request.form.get("premium_rate_percent", "").strip()

        try:
            premium = float(request.form.get("premium", ""))
        except ValueError:
            premium = float("nan")

        try:
            premium_rate_percent = float(premium_rate_input) if premium_rate_input else None
        except ValueError:
            premium_rate_percent = float("nan")

        if not name or not category or not coverage or not duration:
            flash("Complete all insurance product fields.", "warning")
            return redirect(url_for("insurer_products"))
        if not math.isfinite(premium) or premium < 0:
            flash("Enter a valid non-negative premium amount.", "warning")
            return redirect(url_for("insurer_products"))
        if premium_rate_percent is not None and (
            not math.isfinite(premium_rate_percent)
            or premium_rate_percent <= 0
            or premium_rate_percent > 100
        ):
            flash("Enter a premium rate greater than 0 and no more than 100 percent.", "warning")
            return redirect(url_for("insurer_products"))
        if category == "Agricultural Trade Insurance" and premium_rate_percent is None:
            flash("Trade insurance products need a premium rate percentage.", "warning")
            return redirect(url_for("insurer_products"))
        if status not in {"active", "inactive"}:
            flash("Choose a valid product status.", "warning")
            return redirect(url_for("insurer_products"))

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            if product_id:
                cursor.execute(
                    "SELECT id FROM insurance_products WHERE id = %s",
                    (product_id,)
                )
                if cursor.fetchone() is None:
                    flash("Insurance product not found.", "warning")
                    return redirect(url_for("insurer_products"))
                cursor.execute(
                    """
                    UPDATE insurance_products
                    SET name = %s, category = %s, coverage = %s,
                        premium = %s, premium_rate_percent = %s,
                        duration = %s, status = %s
                    WHERE id = %s
                    """,
                    (name, category, coverage, premium, premium_rate_percent, duration, status, product_id)
                )
                flash("Insurance product updated.", "success")
            else:
                cursor.execute(
                    """
                    INSERT INTO insurance_products
                        (name, category, coverage, premium, premium_rate_percent, duration, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (name, category, coverage, premium, premium_rate_percent, duration, status)
                )
                flash("Insurance product created.", "success")
            db.commit()
        except mysql.connector.Error as error:
            if db is not None:
                db.rollback()
            print(f"Insurer product management database error: {error}")
            flash("The insurance product could not be saved.", "danger")
        finally:
            if cursor is not None:
                cursor.close()
            if db is not None:
                db.close()

        return redirect(url_for("insurer_products"))

    db = None
    cursor = None
    products = []
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM insurance_products ORDER BY id DESC")
        products = cursor.fetchall()
    except mysql.connector.Error as error:
        print(f"Insurer products database error: {error}")
        flash("Unable to load insurance products.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template("insurer/products.html", products=products)


@app.route("/insurer/claims")
def insurer_claims():

    if session.get("role") != "insurer":
        return redirect(url_for("login"))

    db = None
    cursor = None
    claims = []
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                c.id,
                c.description,
                c.claim_amount,
                c.status,
                c.created_at,
                u.name AS customer_name,
                u.email,
                ip.name AS policy_name
            FROM claims AS c
            INNER JOIN users AS u ON u.id = c.customer_id
            INNER JOIN customer_policies AS cp ON cp.id = c.customer_policy_id
            INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id
            ORDER BY c.created_at DESC, c.id DESC
            """
        )
        claims = cursor.fetchall()
    except mysql.connector.Error as error:
        print(f"Insurer claims database error: {error}")
        flash("Unable to load insurance claims.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template("insurer/claims.html", claims=claims)


@app.route("/insurer/claims/<int:claim_id>/status", methods=["POST"])
def insurer_update_claim(claim_id):

    if session.get("role") != "insurer":
        return redirect(url_for("login"))

    status = request.form.get("status", "")
    allowed_statuses = {"submitted", "under_review", "approved", "rejected", "paid"}
    if status not in allowed_statuses:
        flash("Choose a valid claim status.", "warning")
        return redirect(url_for("insurer_claims"))

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE claims SET status = %s WHERE id = %s",
            (status, claim_id)
        )
        if cursor.rowcount == 0:
            flash("Claim not found or unchanged.", "warning")
        else:
            db.commit()
            flash("Claim status updated.", "success")
    except mysql.connector.Error as error:
        if db is not None:
            db.rollback()
        print(f"Insurer claim update error: {error}")
        flash("Claim status could not be updated.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return redirect(url_for("insurer_claims"))


@app.route("/insurer/premiums", methods=["GET", "POST"])
def insurer_premiums():

    if session.get("role") != "insurer":
        return redirect(url_for("login"))

    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id", "0"))
            premium = float(request.form.get("premium", ""))
        except ValueError:
            product_id = 0
            premium = float("nan")

        if product_id < 1 or not math.isfinite(premium) or premium < 0:
            flash("Enter a valid product and non-negative premium.", "warning")
            return redirect(url_for("insurer_premiums"))

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "UPDATE insurance_products SET premium = %s WHERE id = %s",
                (premium, product_id)
            )
            if cursor.rowcount == 0:
                flash("Product not found or premium unchanged.", "warning")
            else:
                db.commit()
                flash("Premium updated. This changes the quoted premium for future applications.", "success")
        except mysql.connector.Error as error:
            if db is not None:
                db.rollback()
            print(f"Premium update database error: {error}")
            flash("Premium could not be updated.", "danger")
        finally:
            if cursor is not None:
                cursor.close()
            if db is not None:
                db.close()
        return redirect(url_for("insurer_premiums"))

    db = None
    cursor = None
    products = []
    expected_active_premiums = 0
    active_policy_count = 0
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                ip.id,
                ip.name,
                ip.category,
                ip.premium,
                ip.duration,
                ip.status,
                COUNT(CASE WHEN cp.status = 'active' THEN 1 END) AS active_policy_count,
                COALESCE(SUM(CASE WHEN cp.status = 'active' THEN ip.premium ELSE 0 END), 0) AS expected_premium
            FROM insurance_products AS ip
            LEFT JOIN customer_policies AS cp ON cp.policy_id = ip.id
            GROUP BY ip.id
            ORDER BY ip.name ASC
            """
        )
        products = cursor.fetchall()
        active_policy_count = sum(row["active_policy_count"] for row in products)
        expected_active_premiums = sum(float(row["expected_premium"] or 0) for row in products)
    except mysql.connector.Error as error:
        print(f"Premium management database error: {error}")
        flash("Unable to load premium information.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template(
        "insurer/premiums.html",
        products=products,
        active_policy_count=active_policy_count,
        expected_active_premiums=expected_active_premiums
    )


@app.route("/insurer/reports")
def insurer_reports():

    if session.get("role") != "insurer":
        return redirect(url_for("login"))

    db = None
    cursor = None
    report = {
        "customers": 0,
        "high_risk_customers": 0,
        "active_products": 0,
        "active_policies": 0,
        "pending_applications": 0,
        "expected_premiums": 0,
    }
    policies_by_status = []
    claims_by_status = []
    product_summary = []

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'customer'")
        report["customers"] = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM risk_assessments AS ra
            INNER JOIN (
                SELECT customer_id, MAX(id) AS latest_id
                FROM risk_assessments
                GROUP BY customer_id
            ) AS latest ON latest.latest_id = ra.id
            WHERE ra.overall_score >= 70
            """
        )
        report["high_risk_customers"] = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM insurance_products WHERE status = 'active'")
        report["active_products"] = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT
                status,
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_total
            FROM customer_policies
            GROUP BY status
            ORDER BY status
            """
        )
        policies_by_status = cursor.fetchall()
        for row in policies_by_status:
            if row["status"] == "active":
                report["active_policies"] = row["total"]
            elif row["status"] == "pending":
                report["pending_applications"] = row["total"]

        cursor.execute(
            """
            SELECT COALESCE(SUM(ip.premium), 0) AS total
            FROM customer_policies AS cp
            INNER JOIN insurance_products AS ip ON ip.id = cp.policy_id
            WHERE cp.status = 'active'
            """
        )
        report["expected_premiums"] = float(cursor.fetchone()["total"] or 0)

        cursor.execute("SELECT status, COUNT(*) AS total FROM claims GROUP BY status ORDER BY status")
        claims_by_status = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                ip.name,
                COUNT(CASE WHEN cp.status = 'active' THEN 1 END) AS active_policies,
                COALESCE(SUM(CASE WHEN cp.status = 'active' THEN ip.premium ELSE 0 END), 0) AS expected_premium
            FROM insurance_products AS ip
            LEFT JOIN customer_policies AS cp ON cp.policy_id = ip.id
            GROUP BY ip.id
            ORDER BY expected_premium DESC, ip.name ASC
            """
        )
        product_summary = cursor.fetchall()

    except mysql.connector.Error as error:
        print(f"Insurer reports database error: {error}")
        flash("Unable to load insurance reports.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()

    return render_template(
        "insurer/reports.html",
        report=report,
        policies_by_status=policies_by_status,
        claims_by_status=claims_by_status,
        product_summary=product_summary
    )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    app.run(

        debug=True,

        host="0.0.0.0",

        port=int(os.environ.get("PORT", "5000"))
    )
