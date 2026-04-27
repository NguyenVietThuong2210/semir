allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}

subprojects {
    project.evaluationDependsOn(":app")
}

subprojects {
    // evaluationDependsOn(":app") causes :app to be evaluated before other subprojects.
    // By the time this subprojects{} block reaches :app, it is already evaluated,
    // so afterEvaluate would throw. Skip :app — it configures itself in its own build.gradle.kts.
    if (project.name == "app") return@subprojects

    // afterEvaluate runs after the plugin's own android{} / kotlinOptions{} block,
    // so our settings override whatever the plugin declared.
    afterEvaluate {
        // sentry_flutter sets languageVersion = "1.6" which Kotlin 2.x no longer supports
        // (minimum supported language version is 1.9 in the Kotlin 2.x compiler).
        // We only override the language version — do NOT touch jvmTarget or Java sourceCompatibility,
        // as each plugin manages Java/Kotlin JVM target consistency on its own.
        tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
            compilerOptions {
                languageVersion.set(org.jetbrains.kotlin.gradle.dsl.KotlinVersion.KOTLIN_2_0)
                apiVersion.set(org.jetbrains.kotlin.gradle.dsl.KotlinVersion.KOTLIN_2_0)
            }
        }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
