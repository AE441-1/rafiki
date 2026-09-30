package tz.co.rafiki.mkombozi

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

data class MobileUser(
    val id: Int,
    val name: String,
    val role: String,
)

data class DashboardMetric(
    val label: String,
    val value: String,
)

data class MobileDashboard(
    val user: MobileUser,
    val metrics: List<DashboardMetric>,
)

data class CustomerLoans(
    val applications: List<LoanApplicationItem>,
    val loans: List<LoanItem>,
)

data class LoanApplicationItem(
    val id: Int,
    val amount: String,
    val purpose: String,
    val durationMonths: Int,
    val status: String,
    val applicationDate: String,
)

data class LoanItem(
    val id: Int,
    val amount: String,
    val interestRate: String,
    val durationMonths: Int,
    val status: String,
    val disbursementDate: String,
)

data class InsuranceProduct(
    val id: Int,
    val name: String,
    val category: String,
    val coverage: String,
    val premium: String,
    val duration: String,
    val applicationStatus: String?,
)

data class BankLoanApplication(
    val id: Int,
    val customerName: String,
    val amount: String,
    val purpose: String,
    val durationMonths: Int,
    val status: String,
    val applicationDate: String,
)

data class PolicyApplication(
    val id: Int,
    val customerName: String,
    val policyName: String,
    val category: String,
    val premium: String,
    val duration: String,
)

data class InsuranceClaim(
    val id: Int,
    val customerName: String,
    val policyName: String,
    val description: String,
    val amount: String,
    val status: String,
)

class MobileApi(context: Context) {
    private val cookieJar = PersistentCookieJar(context.applicationContext)
    private val client = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .build()
    private val baseUrl = BuildConfig.API_BASE_URL.trimEnd('/')

    suspend fun signIn(email: String, password: String): MobileUser {
        val response = request(
            path = "login",
            method = "POST",
            body = JSONObject()
                .put("email", email.trim())
                .put("password", password)
                .toString(),
        )
        return response.getJSONObject("user").toMobileUser()
    }

    suspend fun currentSession(): MobileUser {
        return request("session").getJSONObject("user").toMobileUser()
    }

    suspend fun dashboard(): MobileDashboard {
        val response = request("dashboard")
        val user = response.getJSONObject("user").toMobileUser()
        val jsonMetrics = response.getJSONArray("metrics")
        val metrics = (0 until jsonMetrics.length()).map { index ->
            val metric = jsonMetrics.getJSONObject(index)
            DashboardMetric(
                label = metric.getString("label"),
                value = metric.getString("value"),
            )
        }
        return MobileDashboard(user, metrics)
    }

    suspend fun customerLoans(): CustomerLoans {
        val response = request("loans")
        val applications = response.getJSONArray("applications").mapObjects { item ->
            LoanApplicationItem(
                id = item.getInt("id"),
                amount = item.getString("amount"),
                purpose = item.getString("purpose"),
                durationMonths = item.getInt("duration_months"),
                status = item.getString("status"),
                applicationDate = item.optString("application_date"),
            )
        }
        val loans = response.getJSONArray("loans").mapObjects { item ->
            LoanItem(
                id = item.getInt("id"),
                amount = item.getString("amount"),
                interestRate = item.getString("interest_rate"),
                durationMonths = item.getInt("duration_months"),
                status = item.getString("status"),
                disbursementDate = item.optString("disbursement_date"),
            )
        }
        return CustomerLoans(applications, loans)
    }

    suspend fun applyForLoan(amount: String, purpose: String, durationMonths: Int) {
        post(
            "loans",
            JSONObject()
                .put("amount", amount)
                .put("purpose", purpose)
                .put("duration_months", durationMonths),
        )
    }

    suspend fun insuranceProducts(): List<InsuranceProduct> {
        return request("insurance/products").getJSONArray("products").mapObjects { item ->
            InsuranceProduct(
                id = item.getInt("id"),
                name = item.getString("name"),
                category = item.optString("category"),
                coverage = item.optString("coverage"),
                premium = item.getString("premium"),
                duration = item.optString("duration"),
                applicationStatus = if (item.isNull("application_status")) null else item.getString("application_status"),
            )
        }
    }

    suspend fun applyForInsurance(productId: Int) {
        post("insurance/products/$productId/apply", JSONObject())
    }

    suspend fun bankLoanApplications(): List<BankLoanApplication> {
        return request("bank/loan-applications").getJSONArray("applications").mapObjects { item ->
            BankLoanApplication(
                id = item.getInt("id"),
                customerName = item.getString("customer_name"),
                amount = item.getString("amount"),
                purpose = item.getString("purpose"),
                durationMonths = item.getInt("duration_months"),
                status = item.getString("status"),
                applicationDate = item.optString("application_date"),
            )
        }
    }

    suspend fun decideLoan(applicationId: Int, action: String) {
        post("bank/loan-applications/$applicationId/decision", JSONObject().put("action", action))
    }

    suspend fun disburseLoan(applicationId: Int, interestRate: String) {
        post(
            "bank/loan-applications/$applicationId/disburse",
            JSONObject().put("interest_rate", interestRate),
        )
    }

    suspend fun insurerPolicyApplications(): List<PolicyApplication> {
        return request("insurer/policy-applications").getJSONArray("applications").mapObjects { item ->
            PolicyApplication(
                id = item.getInt("id"),
                customerName = item.getString("customer_name"),
                policyName = item.getString("policy_name"),
                category = item.optString("category"),
                premium = item.getString("premium"),
                duration = item.optString("duration"),
            )
        }
    }

    suspend fun decidePolicy(applicationId: Int, decision: String) {
        post("insurer/policy-applications/$applicationId/decision", JSONObject().put("decision", decision))
    }

    suspend fun insurerClaims(): List<InsuranceClaim> {
        return request("insurer/claims").getJSONArray("claims").mapObjects { item ->
            InsuranceClaim(
                id = item.getInt("id"),
                customerName = item.getString("customer_name"),
                policyName = item.getString("policy_name"),
                description = item.getString("description"),
                amount = item.getString("claim_amount"),
                status = item.getString("status"),
            )
        }
    }

    suspend fun updateClaimStatus(claimId: Int, status: String) {
        post("insurer/claims/$claimId/status", JSONObject().put("status", status))
    }

    suspend fun signOut() {
        try {
            request("logout", method = "POST", body = "{}")
        } finally {
            cookieJar.clear()
        }
    }

    private suspend fun request(
        path: String,
        method: String = "GET",
        body: String? = null,
    ): JSONObject = withContext(Dispatchers.IO) {
        val requestBuilder = Request.Builder()
            .url("$baseUrl/api/mobile/$path")
            .header("Accept", "application/json")

        if (method == "POST") {
            val requestBody = (body ?: "{}").toRequestBody(JSON_MEDIA_TYPE)
            requestBuilder.post(requestBody)
        } else {
            requestBuilder.get()
        }

        client.newCall(requestBuilder.build()).execute().use { response ->
            val responseText = response.body?.string().orEmpty()
            val json = runCatching { JSONObject(responseText) }
                .getOrElse { JSONObject() }
            if (!response.isSuccessful) {
                throw ApiException(
                    message = json.optString("error", "The request could not be completed."),
                    statusCode = response.code,
                )
            }
            json
        }
    }

    private suspend fun post(path: String, body: JSONObject) {
        request(path, method = "POST", body = body.toString())
    }

    private fun <T> JSONArray.mapObjects(transform: (JSONObject) -> T): List<T> {
        return (0 until length()).map { index -> transform(getJSONObject(index)) }
    }

    private fun JSONObject.toMobileUser(): MobileUser {
        return MobileUser(
            id = getInt("id"),
            name = getString("name"),
            role = getString("role"),
        )
    }

    private class PersistentCookieJar(context: Context) : CookieJar {
        private val preferences = context.getSharedPreferences(COOKIE_PREFS, Context.MODE_PRIVATE)

        @Synchronized
        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            val stored = preferences.getStringSet(url.host, emptySet())
                ?.toMutableSet()
                ?: mutableSetOf()

            cookies.forEach { cookie ->
                stored.removeAll { serialized ->
                    Cookie.parse(url, serialized)?.let { previous ->
                        previous.name == cookie.name &&
                            previous.domain == cookie.domain &&
                            previous.path == cookie.path
                    } ?: false
                }
                if (!cookie.persistent || cookie.expiresAt > System.currentTimeMillis()) {
                    stored.add(cookie.toString())
                }
            }

            preferences.edit().putStringSet(url.host, stored).apply()
        }

        @Synchronized
        override fun loadForRequest(url: HttpUrl): List<Cookie> {
            val stored = preferences.getStringSet(url.host, emptySet()).orEmpty()
            val cookies = stored.mapNotNull { Cookie.parse(url, it) }
            val valid = cookies.filter { !it.persistent || it.expiresAt > System.currentTimeMillis() }

            if (valid.size != stored.size) {
                preferences.edit()
                    .putStringSet(url.host, valid.mapTo(mutableSetOf()) { it.toString() })
                    .apply()
            }
            return valid
        }

        fun clear() {
            preferences.edit().clear().apply()
        }

        private companion object {
            const val COOKIE_PREFS = "rafiki_session_cookies"
        }
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}

class ApiException(
    override val message: String,
    val statusCode: Int,
) : Exception(message)