package tz.co.rafiki.mkombozi

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
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
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.Image
import kotlinx.coroutines.launch

private val AppBackground = Color(0xFFF3F7F4)
private val Forest = Color(0xFF0F766E)
private val ForestDeep = Color(0xFF123F3B)
private val Ink = Color(0xFF172B27)
private val Muted = Color(0xFF6B7F79)
private val Accent = Color(0xFFD98A5B)
private val CardSurface = Color(0xFFFFFFFF)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(
                colorScheme = lightColorScheme(
                    primary = Forest,
                    onPrimary = Color.White,
                    background = AppBackground,
                    onBackground = Ink,
                    surface = CardSurface,
                    onSurface = Ink,
                    error = Color(0xFFB83C35),
                ),
            ) {
                RafikiMobileApp()
            }
        }
    }
}

@Composable
private fun RafikiMobileApp() {
    val context = LocalContext.current
    val api = remember { MobileApi(context.applicationContext) }
    val scope = rememberCoroutineScope()
    var user by remember { mutableStateOf<MobileUser?>(null) }
    var dashboard by remember { mutableStateOf<MobileDashboard?>(null) }
    var showTasks by remember { mutableStateOf(false) }
    var isRestoring by remember { mutableStateOf(true) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(api) {
        try {
            user = api.currentSession()
            dashboard = api.dashboard()
        } catch (error: Exception) {
            if (error !is ApiException || error.statusCode != 401) {
                errorMessage = error.message ?: "Could not connect to Rafiki."
            }
        } finally {
            isRestoring = false
        }
    }

    Surface(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .navigationBarsPadding(),
        color = AppBackground,
    ) {
        when {
            isRestoring -> LoadingScreen()
            user == null -> LoginScreen(
                errorMessage = errorMessage,
                isLoading = isLoading,
                onSignIn = { email, password ->
                    scope.launch {
                        isLoading = true
                        errorMessage = null
                        try {
                            user = api.signIn(email, password)
                            dashboard = api.dashboard()
                        } catch (error: Exception) {
                            user = null
                            errorMessage = error.message ?: "Sign in failed. Try again."
                        } finally {
                            isLoading = false
                        }
                    }
                },
            )
            showTasks -> WorkflowScreen(
                api = api,
                user = user!!,
                onBack = { showTasks = false },
            )
            else -> DashboardScreen(
                user = user!!,
                dashboard = dashboard,
                errorMessage = errorMessage,
                isLoading = isLoading,
                onOpenTasks = { showTasks = true },
                onRefresh = {
                    scope.launch {
                        isLoading = true
                        errorMessage = null
                        try {
                            dashboard = api.dashboard()
                        } catch (error: Exception) {
                            errorMessage = error.message ?: "Dashboard refresh failed."
                        } finally {
                            isLoading = false
                        }
                    }
                },
                onSignOut = {
                    scope.launch {
                        runCatching { api.signOut() }
                        user = null
                        dashboard = null
                        showTasks = false
                        errorMessage = null
                    }
                },
            )
        }
    }
}

@Composable
private fun LoginScreen(
    errorMessage: String?,
    isLoading: Boolean,
    onSignIn: (String, String) -> Unit,
) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 28.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        BrandMark(size = 58)
        Spacer(Modifier.height(28.dp))
        Text(
            text = "RAFIKI MKOMBOZI",
            color = Forest,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 1.2.sp,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Welcome back",
            color = Ink,
            fontSize = 30.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = "Sign in to your Rafiki account.",
            color = Muted,
            fontSize = 15.sp,
        )
        Spacer(Modifier.height(28.dp))

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Email address") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            shape = RoundedCornerShape(12.dp),
        )
        Spacer(Modifier.height(14.dp))
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Password") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            shape = RoundedCornerShape(12.dp),
        )

        if (errorMessage != null) {
            Spacer(Modifier.height(12.dp))
            Text(errorMessage, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
        }

        Spacer(Modifier.height(22.dp))
        Button(
            onClick = { onSignIn(email, password) },
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
            enabled = !isLoading && email.isNotBlank() && password.isNotBlank(),
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Forest),
        ) {
            if (isLoading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(20.dp),
                    color = Color.White,
                    strokeWidth = 2.dp,
                )
            } else {
                Text("Sign in", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun DashboardScreen(
    user: MobileUser,
    dashboard: MobileDashboard?,
    errorMessage: String?,
    isLoading: Boolean,
    onOpenTasks: () -> Unit,
    onRefresh: () -> Unit,
    onSignOut: () -> Unit,
) {
    val metrics = dashboard?.metrics.orEmpty()
    val roleLabel = when (user.role) {
        "customer" -> "CUSTOMER"
        "bank" -> "BANK"
        "insurer" -> "INSURER"
        else -> user.role.uppercase()
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
            BrandMark(size = 42)
            Spacer(Modifier.width(10.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text("Rafiki Mkombozi", color = Ink, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                Text(roleLabel, color = Forest, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            }
            Button(
                onClick = onRefresh,
                enabled = !isLoading,
                shape = RoundedCornerShape(9.dp),
                colors = ButtonDefaults.buttonColors(containerColor = ForestDeep),
            ) {
                Text(if (isLoading) "Loading" else "Refresh", fontSize = 12.sp)
            }
        }

        Spacer(Modifier.height(28.dp))
        Text("Hello, ${user.name}", color = Ink, fontSize = 26.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        Text("Your account overview", color = Muted, fontSize = 14.sp)
        Spacer(Modifier.height(24.dp))

        if (errorMessage != null) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(10.dp),
                color = Color(0xFFFFF0E9),
            ) {
                Text(
                    text = errorMessage,
                    modifier = Modifier.padding(14.dp),
                    color = Color(0xFF8C3E2C),
                    fontSize = 13.sp,
                )
            }
            Spacer(Modifier.height(16.dp))
        }

        if (dashboard == null && isLoading) {
            Box(modifier = Modifier.fillMaxWidth().height(140.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = Forest)
            }
        } else {
            metrics.chunked(2).forEach { rowMetrics ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    rowMetrics.forEach { metric ->
                        MetricCard(metric, modifier = Modifier.weight(1f))
                    }
                    if (rowMetrics.size == 1) {
                        Spacer(Modifier.weight(1f))
                    }
                }
                Spacer(Modifier.height(12.dp))
            }
        }

        Spacer(Modifier.height(12.dp))
        Button(
            onClick = onOpenTasks,
            modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Forest),
        ) {
            Text("Open tasks", fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(10.dp))
        Button(
            onClick = onSignOut,
            modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Color(0xFFE6EEEA),
                contentColor = ForestDeep,
            ),
        ) {
            Text("Sign out", fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun MetricCard(metric: DashboardMetric, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.height(126.dp),
        color = CardSurface,
        shape = RoundedCornerShape(12.dp),
        shadowElevation = 1.dp,
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.SpaceBetween) {
            Text(
                text = metric.label,
                color = Muted,
                fontSize = 12.sp,
                lineHeight = 16.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = metric.value,
                color = if (metric.label.contains("risk", ignoreCase = true)) Accent else ForestDeep,
                fontSize = 25.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun BrandMark(size: Int) {
    Surface(
        modifier = Modifier.size(size.dp),
        color = Forest,
        shape = RoundedCornerShape((size / 4).dp),
    ) {
        Image(
            painter = painterResource(R.drawable.ic_launcher_foreground),
            contentDescription = null,
            modifier = Modifier.padding((size / 7).dp),
        )
    }
}

@Composable
private fun LoadingScreen() {
    Box(
        modifier = Modifier.fillMaxSize().background(AppBackground),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator(color = Forest)
    }
}