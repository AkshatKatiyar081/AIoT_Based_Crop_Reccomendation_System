#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#define BLYNK_TEMPLATE_ID "TMPL37HvTvGPR"
#define BLYNK_TEMPLATE_NAME "Kisan Mitra"
#define BLYNK_AUTH_TOKEN "REDACTED"
#include <BlynkSimpleEsp32.h>

// ── WiFi (Wokwi simulated WiFi) ─────────────────────────────────────────
#define WIFI_SSID     "Wokwi-GUEST"
#define WIFI_PASSWORD ""

// ── HiveMQ Cloud ─────────────────────────────────────────────────────────
#define MQTT_HOST     "REDACTED"
#define MQTT_PORT     8883
#define MQTT_USER     "REDACTED"
#define MQTT_PASS     "REDACTED"
#define MQTT_PUB      "farm/sensor/data"
#define MQTT_CMD      "farm/sensor/command"
#define CLIENT_ID     "wokwi-esp32-sensor"

// ── Sensor pins ──────────────────────────────────────────────────────────
#define DHT_PIN    4
#define DHT_TYPE   DHT22
#define PIN_N      34    // Potentiometer → Nitrogen
#define PIN_P      35    // Potentiometer → Phosphorus
#define PIN_K      32    // Potentiometer → Potassium
#define PIN_PH     33    // Potentiometer → pH
#define PIN_RAIN   25    // Potentiometer → Rainfall

// ── Sensor value ranges (matching Crop_recommendation.csv) ───────────────
#define N_MIN    0.0f    // mg/kg
#define N_MAX    140.0f
#define P_MIN    5.0f
#define P_MAX    145.0f
#define K_MIN    5.0f
#define K_MAX    205.0f
#define PH_MIN   3.5f
#define PH_MAX   10.0f
#define RAIN_MIN 20.0f
#define RAIN_MAX 300.0f

DHT dht(DHT_PIN, DHT_TYPE);
WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

unsigned long lastPublish = 0;
const long PUBLISH_INTERVAL = 800;  // ms — same as original simulator

// ── Map ADC reading (0-4095) to a float range ────────────────────────────
float mapFloat(int raw, float outMin, float outMax) {
  return outMin + ((float)raw / 4095.0f) * (outMax - outMin);
}

void onMqttMessage(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<128> doc;
  deserializeJson(doc, payload, len);
  // If backend sends a "refresh" command, we can reinitialise something
  // For Wokwi simulation this is informational only
  Serial.println("[CMD] Refresh command received");
}

void connectWiFi() {
  Serial.print("[WiFi] Connecting to ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\n[WiFi] Connected. IP: " + WiFi.localIP().toString());
}

void connectMQTT() {
  espClient.setInsecure();  // For Wokwi simulation; in production use proper cert
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(onMqttMessage);
  mqttClient.setBufferSize(512);

  int attempts = 0;
  while (!mqttClient.connected() && attempts < 5) {
    attempts++;
    Serial.print("[MQTT] Connecting...");
    if (mqttClient.connect(CLIENT_ID, MQTT_USER, MQTT_PASS)) {
      Serial.println(" Connected!");
      mqttClient.subscribe(MQTT_CMD);
    } else {
      Serial.print(" Failed (rc=");
      Serial.print(mqttClient.state());
      Serial.println("). Retry in 3s.");
      delay(3000);
    }
  }
}

void connectBlynk() {
  Blynk.config(BLYNK_AUTH_TOKEN);
  Serial.print("[Blynk] Connecting...");
  if (Blynk.connect(10000)) {
    Serial.println(" Connected!");
  } else {
    Serial.println(" Failed.");
  }
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);  // 12-bit ADC → 0-4095
  dht.begin();
  connectWiFi();
  connectBlynk();
  connectMQTT();
  Serial.println("[Wokwi] Kisan Mitra Sensor Node Ready");
}

void loop() {
  if (!Blynk.connected()) connectBlynk();
  Blynk.run();

  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastPublish >= PUBLISH_INTERVAL) {
    lastPublish = now;

    // ── Read DHT22 ────────────────────────────────────────────────────
    float temperature = dht.readTemperature();
    float humidity    = dht.readHumidity();
    if (isnan(temperature) || isnan(humidity)) {
      Serial.println("[DHT] Read failed, skipping.");
      return;
    }

    // ── Read potentiometers and map to crop dataset ranges ────────────
    float N        = mapFloat(analogRead(PIN_N),    N_MIN,    N_MAX);
    float P        = mapFloat(analogRead(PIN_P),    P_MIN,    P_MAX);
    float K        = mapFloat(analogRead(PIN_K),    K_MIN,    K_MAX);
    float ph       = mapFloat(analogRead(PIN_PH),   PH_MIN,   PH_MAX);
    float rainfall = mapFloat(analogRead(PIN_RAIN), RAIN_MIN, RAIN_MAX);

    // ── Build JSON payload ────────────────────────────────────────────
    StaticJsonDocument<256> doc;
    doc["N"]           = round(N  * 10.0f) / 10.0f;
    doc["P"]           = round(P  * 10.0f) / 10.0f;
    doc["K"]           = round(K  * 10.0f) / 10.0f;
    doc["temperature"] = round(temperature * 100.0f) / 100.0f;
    doc["humidity"]    = round(humidity    * 100.0f) / 100.0f;
    doc["ph"]          = round(ph          * 100.0f) / 100.0f;
    doc["rainfall"]    = round(rainfall    * 10.0f)  / 10.0f;
    doc["source"]      = "wokwi-esp32";

    Blynk.virtualWrite(V0, doc["N"].as<float>());
    Blynk.virtualWrite(V1, doc["P"].as<float>());
    Blynk.virtualWrite(V2, doc["K"].as<float>());
    Blynk.virtualWrite(V3, doc["temperature"].as<float>());
    Blynk.virtualWrite(V4, doc["humidity"].as<float>());
    Blynk.virtualWrite(V5, doc["ph"].as<float>());
    Blynk.virtualWrite(V6, doc["rainfall"].as<float>());

    char buffer[256];
    serializeJson(doc, buffer);

    mqttClient.publish(MQTT_PUB, buffer, false);

    // ── Serial monitor log ────────────────────────────────────────────
    Serial.printf(
      "[Publish] N=%.1f P=%.1f K=%.1f T=%.2f°C H=%.2f%% pH=%.2f Rain=%.1fmm\n",
      N, P, K, temperature, humidity, ph, rainfall
    );
  }
}