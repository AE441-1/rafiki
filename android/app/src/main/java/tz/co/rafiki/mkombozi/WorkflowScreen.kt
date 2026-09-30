package tz.co.rafiki.mkombozi

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

private val TaskInk = Color(0xFF172B27)
private val TaskMuted = Color(0xFF6B7F79)
private val TaskForest = Color(0xFF0F766E)
private val TaskSurface = Color.White
private val TaskLine = Color(0xFFDCE7E1)
private val TaskWarn = Color(0xFFB45436)

@Composable
internal fun WorkflowScreen(
    api: MobileApi,
    user: MobileUser,
    onBack: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var customerLoans by remember { mutableStateOf<CustomerLoans?>(null) }
    var insuranceProducts by remember { mutableStateOf<List<InsuranceProduct>>(emptyList()) }
    var bankApplications by remember { mutableStateOf<List<BankLoanApplication>>(emptyList()) }
    var policyApplications by remember { mutableStateOf<List<PolicyApplication>>(emptyList()) }
    var claims by remember { mutableStateOf<List<InsuranceClaim>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var successMessage by remember { mutableStateOf<String?>(null) }

    suspend fun refreshTasks() {
        isLoading = true
        errorMessage = null
        try {
            when (user.role) {
                "customer" -> {
                    customerLoans = api.customerLoans()
                    insuranceProducts = api.insuranceProducts()
                }
                "bank" -> bankApplications = api.bankLoanApplications()
                "insurer" -> {
                    policyApplications = api.insurerPolicyApplications()
                    claims = api.insurerClaims()
                }
            }
        } catch (error: Exception) {
            errorMessage = error.message ?: "Unable to load tasks."
        } finally {
            isLoading = false
        }
    }

    fun perform(action: suspend () -> Unit) {
        scope.launch {
            errorMessage = null
            successMessage = null
            isLoading = true
            try {
                action()
                successMessage = "Update saved."
                refreshTasks()
            } catch (error: Exception) {
                errorMessage = error.message ?: "The update could not be saved."
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(user.role) {
        refreshTasks()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text("WORKSPACE", color = TaskForest, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                Text("Tasks", color = TaskInk, fontSize = 26.sp, fontWeight = FontWeight.Bold)
            }
            Button(
                onClick = { scope.launch { refreshTasks() } },
                enabled = !isLoading,
                shape = RoundedCornerShape(9.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE6EEEA), contentColor = TaskInk),
            ) {
                Text(if (isLoading) "Loading" else "Refresh")
            }
            Spacer(Modifier.width(8.dp))
            Button(
                onClick = onBack,
                shape = RoundedCornerShape(9.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE6EEEA), contentColor = TaskInk),
            ) {
                Text("Home")
            }
        }

        Spacer(Modifier.height(18.dp))
        if (errorMessage != null) {
            Notice(text = errorMessage!!, tone = TaskWarn)
            Spacer(Modifier.height(10.dp))
        }
        if (successMessage != null) {
            Notice(text = successMessage!!, tone = TaskForest)
            Spacer(Modifier.height(10.dp))
        }
        if (isLoading) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 28.dp),
                horizontalArrangement = Arrangement.Center,
            ) {
                CircularProgressIndicator(color = TaskForest)
            }
        } else {
            when (user.role) {
                "customer" -> CustomerTasks(
                    loans = customerLoans,
                    products = insuranceProducts,
                    isBusy = isLoading,
                    onSubmitLoan = { amount, purpose, duration ->
                        perform { api.applyForLoan(amount, purpose, duration) }
                    },
                    onApplyForInsurance = { productId ->
                        perform { api.applyForInsurance(productId) }
                    },
                )
                "bank" -> BankTasks(
                    applications = bankApplications,
                    onDecision = { applicationId, action ->
                        perform { api.decideLoan(applicationId, action) }
                    },
                    onDisburse = { applicationId, rate ->
                        perform { api.disburseLoan(applicationId, rate) }
                    },
                )
                "insurer" -> InsurerTasks(
                    applications = policyApplications,
                    claims = claims,
                    onPolicyDecision = { applicationId, decision ->
                        perform { api.decidePolicy(applicationId, decision) }
                    },
                    onClaimStatus = { claimId, status ->
                        perform { api.updateClaimStatus(claimId, status) }
                    },
                )
            }
        }
    }
}

@Composable
private fun CustomerTasks(
    loans: CustomerLoans?,
    products: List<InsuranceProduct>,
    isBusy: Boolean,
    onSubmitLoan: (String, String, Int) -> Unit,
    onApplyForInsurance: (Int) -> Unit,
) {
    var amount by remember { mutableStateOf("") }
    var purpose by remember { mutableStateOf("") }
    var duration by remember { mutableStateOf("6") }

    TaskSectionTitle("Apply for a loan")
    TaskCard {
        OutlinedTextField(
            value = amount,
            onValueChange = { amount = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Amount in TZS") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            shape = RoundedCornerShape(10.dp),
        )
        OutlinedTextField(
            value = purpose,
            onValueChange = { purpose = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Purpose") },
            singleLine = true,
            shape = RoundedCornerShape(10.dp),
        )
        OutlinedTextField(
            value = duration,
            onValueChange = { duration = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Repayment duration in months (3, 6, 9, 12, 18, 24)") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            shape = RoundedCornerShape(10.dp),
        )
        TaskButton(
            text = "Submit application",
            enabled = !isBusy && amount.isNotBlank() && purpose.isNotBlank() && duration.toIntOrNull() != null,
            onClick = {
                duration.toIntOrNull()?.let { onSubmitLoan(amount, purpose, it) }
            },
        )
    }

    TaskSectionTitle("Your loan applications")
    if (loans?.applications.isNullOrEmpty()) {
        EmptyMessage("No loan applications yet.")
    } else {
        loans!!.applications.forEach { application ->
            TaskCard {
                ItemHeading("TZS ${application.amount}", application.status)
                Text(application.purpose, color = TaskInk, fontSize = 14.sp)
                Text("${application.durationMonths} months", color = TaskMuted, fontSize = 12.sp)
            }
            Spacer(Modifier.height(10.dp))
        }
    }
    loans?.loans.orEmpty().forEach { loan ->
        TaskCard {
            ItemHeading("Active loan · TZS ${loan.amount}", loan.status)
            Text("${loan.durationMonths} months · ${loan.interestRate}% interest", color = TaskMuted, fontSize = 12.sp)
        }
        Spacer(Modifier.height(10.dp))
    }

    TaskSectionTitle("Insurance products")
    if (products.isEmpty()) {
        EmptyMessage("No active insurance products are available.")
    }
    products.forEach { product ->
        TaskCard {
            ItemHeading(product.name, product.applicationStatus ?: product.category)
            Text(product.coverage, color = TaskMuted, fontSize = 13.sp, lineHeight = 18.sp)
            Text("TZS ${product.premium} · ${product.duration}", color = TaskInk, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            TaskButton(
                text = when (product.applicationStatus) {
                    "pending" -> "Application pending"
                    "active" -> "Coverage active"
                    else -> "Apply for cover"
                },
                enabled = product.applicationStatus == null && !isBusy,
                onClick = { onApplyForInsurance(product.id) },
            )
        }
        Spacer(Modifier.height(10.dp))
    }
}

@Composable
private fun BankTasks(
    applications: List<BankLoanApplication>,
    onDecision: (Int, String) -> Unit,
    onDisburse: (Int, String) -> Unit,
) {
    TaskSectionTitle("Loan applications")
    if (applications.isEmpty()) {
        EmptyMessage("No applications are waiting for review.")
    }
    applications.forEach { application ->
        var interestRate by remember(application.id) { mutableStateOf("12") }
        TaskCard {
            ItemHeading("${application.customerName} · TZS ${application.amount}", application.status)
            Text(application.purpose, color = TaskInk, fontSize = 14.sp)
            Text("${application.durationMonths} months · ${application.applicationDate}", color = TaskMuted, fontSize = 12.sp)
            if (application.status == "approved") {
                OutlinedTextField(
                    value = interestRate,
                    onValueChange = { interestRate = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Interest rate (%)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    shape = RoundedCornerShape(10.dp),
                )
                TaskButton(
                    text = "Disburse loan",
                    enabled = interestRate.toDoubleOrNull() != null,
                    onClick = { onDisburse(application.id, interestRate) },
                )
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TaskButton("Review", Modifier.weight(1f)) { onDecision(application.id, "review") }
                    TaskButton("Approve", Modifier.weight(1f)) { onDecision(application.id, "approve") }
                    TaskButton("Reject", Modifier.weight(1f), secondary = true) { onDecision(application.id, "reject") }
                }
            }
        }
        Spacer(Modifier.height(10.dp))
    }
}

@Composable
private fun InsurerTasks(
    applications: List<PolicyApplication>,
    claims: List<InsuranceClaim>,
    onPolicyDecision: (Int, String) -> Unit,
    onClaimStatus: (Int, String) -> Unit,
) {
    TaskSectionTitle("Policy applications")
    if (applications.isEmpty()) {
        EmptyMessage("No insurance applications are waiting for review.")
    }
    applications.forEach { application ->
        TaskCard {
            ItemHeading(application.policyName, application.category)
            Text(application.customerName, color = TaskInk, fontSize = 14.sp)
            Text("TZS ${application.premium} · ${application.duration}", color = TaskMuted, fontSize = 12.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TaskButton("Approve", Modifier.weight(1f)) { onPolicyDecision(application.id, "approve") }
                TaskButton("Decline", Modifier.weight(1f), secondary = true) { onPolicyDecision(application.id, "reject") }
            }
        }
        Spacer(Modifier.height(10.dp))
    }

    TaskSectionTitle("Claims")
    if (claims.isEmpty()) {
        EmptyMessage("No claims have been submitted.")
    }
    claims.forEach { claim ->
        TaskCard {
            ItemHeading(claim.policyName, claim.status)
            Text(claim.customerName, color = TaskInk, fontSize = 14.sp)
            Text(claim.description, color = TaskMuted, fontSize = 13.sp, lineHeight = 18.sp)
            Text("Claim · TZS ${claim.amount}", color = TaskInk, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TaskButton("Review", Modifier.weight(1f), secondary = true) { onClaimStatus(claim.id, "under_review") }
                TaskButton("Approve", Modifier.weight(1f)) { onClaimStatus(claim.id, "approved") }
                TaskButton("Reject", Modifier.weight(1f), secondary = true) { onClaimStatus(claim.id, "rejected") }
            }
            TaskButton("Mark paid", onClick = { onClaimStatus(claim.id, "paid") })
        }
        Spacer(Modifier.height(10.dp))
    }
}

@Composable
private fun TaskSectionTitle(title: String) {
    Text(
        text = title,
        modifier = Modifier.padding(top = 18.dp, bottom = 10.dp),
        color = TaskInk,
        fontSize = 18.sp,
        fontWeight = FontWeight.Bold,
    )
}

@Composable
private fun TaskCard(content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = TaskSurface,
        shape = RoundedCornerShape(12.dp),
        shadowElevation = 1.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, TaskLine),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            content = content,
        )
    }
}

@Composable
private fun ItemHeading(title: String, status: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            text = title,
            modifier = Modifier.weight(1f),
            color = TaskInk,
            fontWeight = FontWeight.Bold,
            fontSize = 14.sp,
            lineHeight = 18.sp,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.width(8.dp))
        Text(status.replace('_', ' '), color = TaskForest, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun TaskButton(
    text: String,
    modifier: Modifier = Modifier.fillMaxWidth(),
    enabled: Boolean = true,
    secondary: Boolean = false,
    onClick: () -> Unit,
) {
    Button(
        onClick = onClick,
        modifier = modifier.height(44.dp),
        enabled = enabled,
        shape = RoundedCornerShape(9.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (secondary) Color(0xFFE6EEEA) else TaskForest,
            contentColor = if (secondary) TaskInk else Color.White,
        ),
    ) {
        Text(text, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun EmptyMessage(text: String) {
    Text(text, modifier = Modifier.padding(vertical = 8.dp), color = TaskMuted, fontSize = 13.sp)
}

@Composable
private fun Notice(text: String, tone: Color) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = tone.copy(alpha = 0.10f),
        shape = RoundedCornerShape(9.dp),
    ) {
        Text(text, modifier = Modifier.padding(12.dp), color = tone, fontSize = 13.sp)
    }
}