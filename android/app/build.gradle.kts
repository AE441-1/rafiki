plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val debugApiBaseUrl = providers.gradleProperty("rafikiApiBaseUrl")
    .orElse("http://10.0.2.2:5000/")
    .get()
val releaseApiBaseUrl = providers.gradleProperty("rafikiReleaseApiBaseUrl")
    .orElse("https://YOUR-FLASK-HOST/")
    .get()

android {
    namespace = "tz.co.rafiki.mkombozi"
    compileSdk = 35

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    defaultConfig {
        applicationId = "tz.co.rafiki.mkombozi"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
    }

    buildTypes {
        debug {
            buildConfigField("String", "API_BASE_URL", "\"$debugApiBaseUrl\"")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiBaseUrl\"")
        }
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
}