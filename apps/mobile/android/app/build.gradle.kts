import java.util.Properties

plugins {
    id("com.android.application")
}

// Single source of truth: apps/mobile/version.properties
val versionProps = Properties().apply {
    rootProject.file("../version.properties").inputStream().use { load(it) }
}
val appVersionName: String = versionProps.getProperty("versionName")
    ?: error("versionName missing in apps/mobile/version.properties")
val appVersionCode: Int = versionProps.getProperty("versionCode")?.toIntOrNull()
    ?: error("versionCode missing/invalid in apps/mobile/version.properties")
require(Regex("""\d+\.\d+\.\d+""").matches(appVersionName)) { "versionName must be X.Y.Z" }

fun env(name: String): String? = System.getenv(name)?.takeIf { it.isNotBlank() }
fun quoted(value: String) = "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

// Release signing comes only from the protected CI environment (never from Git).
val releaseKeystore = env("AIWB_KEYSTORE_PATH")

android {
    namespace = "io.github.golshandvr.aiworkbench"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.golshandvr.aiworkbench"
        minSdk = 24
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersionName
        buildConfigField("String", "COMMIT_SHA", quoted(env("AIWB_COMMIT_SHA") ?: "local"))
        buildConfigField("String", "BUILD_REF", quoted(env("AIWB_BUILD_REF") ?: "local"))
        buildConfigField("String", "GITHUB_REPOSITORY", quoted(env("GITHUB_REPOSITORY") ?: "golshandvr-del/workbench"))
        testInstrumentationRunner = "android.test.InstrumentationTestRunner"
    }

    signingConfigs {
        if (releaseKeystore != null) {
            create("release") {
                storeFile = file(releaseKeystore)
                storePassword = env("AIWB_KEYSTORE_PASSWORD")
                keyAlias = env("AIWB_KEY_ALIAS")
                keyPassword = env("AIWB_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField("String", "CHANNEL", quoted("debug"))
        }
        getByName("release") {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            buildConfigField("String", "CHANNEL", quoted(env("AIWB_CHANNEL") ?: "stable"))
            signingConfig = signingConfigs.findByName("release")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkReleaseBuilds = false
        disable += setOf("GradleDependency", "OldTargetApi", "AndroidGradlePluginVersion", "NewerVersionAvailable")
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    // Real org.json on the JVM test classpath (android.jar only ships stubs).
    testImplementation("org.json:json:20260814")
}

// Fail fast if a release build is requested without signing material.
tasks.matching { it.name == "assembleRelease" || it.name == "bundleRelease" }.configureEach {
    doFirst {
        if (releaseKeystore == null) {
            throw GradleException("Release signing is not configured (AIWB_KEYSTORE_PATH etc.). Use assembleDebug for local builds.")
        }
    }
}
