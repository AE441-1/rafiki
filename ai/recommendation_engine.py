
# ============================================================
# RAFIKI MKOMBOZI
# AI / RISK RECOMMENDATION ENGINE
# ============================================================


# ============================================================
# OVERALL RISK
# ============================================================

def calculate_risk(
    drought,
    flood,
    rainfall,
    pest_pressure=0
):
    """
    Calculate overall climate and agricultural risk.

    All input values should be between 0 and 100.

    Prototype weighting:
        Drought         = 40%
        Flood           = 30%
        Rainfall        = 20%
        Pest Pressure   = 10%

    The weighting is a prototype for the project and should
    later be calibrated using local historical and insurance data.
    """

    drought = float(drought or 0)
    flood = float(flood or 0)
    rainfall = float(rainfall or 0)
    pest_pressure = float(pest_pressure or 0)

    # Keep every score within the expected range.
    drought = max(0, min(100, drought))
    flood = max(0, min(100, flood))
    rainfall = max(0, min(100, rainfall))
    pest_pressure = max(0, min(100, pest_pressure))

    overall = (
        drought * 0.40 +
        flood * 0.30 +
        rainfall * 0.20 +
        pest_pressure * 0.10
    )

    return round(
        max(0, min(100, overall)),
        2
    )


# ============================================================
# RISK RELEVANCE
# ============================================================

def get_relevance(score):

    score = float(score or 0)

    if score >= 70:
        return "HIGH"

    elif score >= 50:
        return "MEDIUM"

    else:
        return "LOW"


# ============================================================
# RECOMMENDATIONS
# ============================================================

def generate_recommendations(
    drought,
    flood,
    rainfall,
    customer_type,
    pest_pressure=None
):
    """
    Generate insurance recommendations based on:

        - Drought
        - Flood
        - Rainfall
        - Pest pressure
        - Customer type
    """

    recommendations = {}

    drought = float(drought or 0)
    flood = float(flood or 0)
    rainfall = float(rainfall or 0)
    pest_pressure = float(pest_pressure or 0)

    # Keep values within 0–100.
    drought = max(0, min(100, drought))
    flood = max(0, min(100, flood))
    rainfall = max(0, min(100, rainfall))
    pest_pressure = max(0, min(100, pest_pressure))


    # ========================================================
    # INTERNAL HELPER
    # ========================================================

    def add_product_recommendation(
        policy,
        score,
        reason
    ):

        score = round(
            max(
                0,
                min(
                    100,
                    float(score or 0)
                )
            ),
            2
        )

        if policy in recommendations:

            existing = recommendations[policy]

            if reason not in existing["reason"]:
                existing["reason"] += " " + reason

            existing["score"] = max(
                existing["score"],
                score
            )

            existing["relevance"] = get_relevance(
                existing["score"]
            )

            return

        recommendations[policy] = {
            "policy": policy,
            "score": score,
            "relevance": get_relevance(score),
            "reason": reason
        }


    # ========================================================
    # FARMER
    # ========================================================

    if customer_type == "farmer":

        crop_score = max(
            drought,
            rainfall,
            pest_pressure
        )


        # ----------------------------------------------------
        # Determine dominant agricultural risk
        # ----------------------------------------------------

        if (
            pest_pressure >= drought
            and pest_pressure >= rainfall
            and pest_pressure >= 40
        ):

            crop_reason = (
                "Recent local climate conditions may favor "
                "crop pest or disease pressure. This is a "
                "climate-based proxy and does not identify a "
                "specific pest or measure pesticide exposure."
            )


        elif (
            drought >= rainfall
            and drought >= pest_pressure
            and drought >= 40
        ):

            crop_reason = (
                "Recent local climate indicators show notable "
                "dry-period or drought pressure that may affect "
                "crop production."
            )


        elif (
            rainfall >= drought
            and rainfall >= pest_pressure
            and rainfall >= 40
        ):

            crop_reason = (
                "Recent local climate indicators show notable "
                "rainfall pressure that may affect crop production."
            )


        else:

            crop_reason = (
                "Current climate indicators are lower; crop "
                "protection can still help manage seasonal "
                "uncertainty. Continue monitoring local conditions."
            )


        # ----------------------------------------------------
        # Crop insurance
        # ----------------------------------------------------

        add_product_recommendation(
            "Crop Protection Insurance",
            crop_score,
            crop_reason
        )


        # ----------------------------------------------------
        # Flood insurance
        # ----------------------------------------------------

        if flood >= 40:

            add_product_recommendation(
                "Flood Protection Insurance",
                flood,
                (
                    "Recent local climate indicators show "
                    "increased flood or heavy-rain exposure."
                )
            )


        # ----------------------------------------------------
        # Pest-specific recommendation
        # ----------------------------------------------------

        if pest_pressure >= 50:

            add_product_recommendation(
                "Crop Protection Insurance",
                pest_pressure,
                (
                    "The climate-based pest pressure indicator "
                    "is elevated. Crop protection cover may help "
                    "manage potential production losses."
                )
            )


        # ----------------------------------------------------
        # Drought-specific recommendation
        # ----------------------------------------------------

        if drought >= 60:

            add_product_recommendation(
                "Crop Protection Insurance",
                drought,
                (
                    "The drought indicator is elevated and may "
                    "increase the risk of crop production losses "
                    "during dry conditions."
                )
            )


    # ========================================================
    # INFORMAL BUSINESS
    # ========================================================

    elif customer_type == "informal_business":

        business_score = max(
            flood,
            rainfall
        )


        # ----------------------------------------------------
        # Business risk explanation
        # ----------------------------------------------------

        if (
            flood >= rainfall
            and flood >= 40
        ):

            business_reason = (
                "Recent local climate indicators show "
                "flood-related risks that may disrupt a business "
                "or damage stock."
            )


        elif rainfall >= 40:

            business_reason = (
                "Recent local climate indicators show "
                "rainfall-related risks that may affect business "
                "stock or operations."
            )


        else:

            business_reason = (
                "Current climate indicators are lower; business "
                "cover can still help manage unexpected disruption. "
                "Review the policy terms."
            )


        # ----------------------------------------------------
        # Business insurance
        # ----------------------------------------------------

        add_product_recommendation(
            "Business Protection Insurance",
            business_score,
            business_reason
        )


        # ----------------------------------------------------
        # Flood insurance
        # ----------------------------------------------------

        if flood >= 40:

            add_product_recommendation(
                "Flood Protection Insurance",
                flood,
                (
                    "Flood indicators are elevated for the "
                    "selected location."
                )
            )


    # ========================================================
    # RETURN
    # ========================================================

    return list(
        recommendations.values()
    )

