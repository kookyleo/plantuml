plugins {
    java
}

repositories {
    mavenLocal()
    mavenCentral()
}

val plantumlJars = fileTree("../build/libs") {
    include("*.jar")
    exclude("*-sources.jar", "*-javadoc.jar", "*-pdf.jar")
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation(plantumlJars)
}

val verifyPlantumlJar by tasks.registering {
    doLast {
        val jars = plantumlJars.files.sortedBy { it.name }
        if (jars.isEmpty()) {
            throw GradleException("No PlantUML runtime jar found under ../build/libs. Run the root jar task first.")
        }
        println("Using PlantUML jar: ${jars.joinToString { it.name }}")
    }
}

tasks.compileTestJava {
    dependsOn(verifyPlantumlJar)
    options.encoding = "UTF-8"
}

tasks.test {
    useJUnit()
    testLogging.showStandardStreams = true
    jvmArgs(
        "-ea",
        "--add-opens=java.desktop/java.awt=ALL-UNNAMED",
        "--add-opens=java.base/java.net=ALL-UNNAMED",
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=java.base/java.io=ALL-UNNAMED",
        "--add-opens=java.base/java.util=ALL-UNNAMED"
    )
}
