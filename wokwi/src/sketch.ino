/*
 * Kisan Mitra field node (ESP32, runs in Wokwi or on real hardware)
 *
 * Reads soil moisture + air temperature/humidity, publishes them over MQTT,
 * and switches the irrigation pump relay when the backend sends a command.
 *
 *   publish   <prefix>/sensor  {"soil_moisture", "temperature", "humidity", "pump", "device"}
 *   subscribe <prefix>/pump    {"pump": "ON" | "OFF", "mode": "auto" | "manual"}
 *
 * In Wokwi the soil moisture probe is a potentiometer (Wokwi has no soil sensor part).
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// ── WiFi (Wokwi simulated WiFi; change for real hardware) ────────────────
#define WIFI_SSID     "Wokwi-GUEST"
#define WIFI_PASSWORD ""

// ── MQTT: free public broker, no account. Prefix must match MQTT_TOPIC_PREFIX in backend/.env
#define MQTT_HOST     "REDACTED"
#define MQTT_PORT     1883
#define TOPIC_PREFIX  "kisanmitra/km-1d41f0"
#define DEVICE_NAME   "wokwi-esp32"

// ── Pins ─────────────────────────────────────────────────────────────────
#define DHT_PIN       4
#define DHT_TYPE      DHT22
#define PIN_MOISTURE  34    // ADC1 pin (ADC2 pins can't be read while WiFi is on)
#define PIN_RELAY     26    // relay IN -> pump

const unsigned long PUBLISH_INTERVAL_MS = 2000;

DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient netClient;
PubSubClient mqtt(netClient);

String topicSensor = String(TOPIC_PREFIX) + "/sensor";
String topicPump   = String(TOPIC_PREFIX) + "/pump";

bool pumpOn = false;
unsigned long lastPublish = 0;

void setPump(bool on) {
  pumpOn = on;
  digitalWrite(PIN_RELAY, on ? HIGH : LOW);
  Serial.printf("[PUMP] %s\r\n", on ? "ON" : "OFF");
}

void onMqttMessage(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<128> doc;
  if (deserializeJson(doc, payload, len)) {
    Serial.println("[MQTT] Bad pump command, ignored");
    return;
  }
  const char* cmd = doc["pump"] | "";
  if (strcmp(cmd, "ON") == 0)  setPump(true);
  if (strcmp(cmd, "OFF") == 0) setPump(false);
}

void connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[WiFi] Connected, IP " + WiFi.localIP().toString());
}

void connectMQTT() {
  while (!mqtt.connected()) {
    String clientId = String(DEVICE_NAME) + "-" + String((uint32_t)esp_random(), HEX);
    Serial.print("[MQTT] Connecting...");
    if (mqtt.connect(clientId.c_str())) {
      Serial.println(" connected");
      mqtt.subscribe(topicPump.c_str());   // retained message gives us the current pump state
    } else {
      Serial.printf(" failed (rc=%d), retrying in 3 s\r\n", mqtt.state());
      delay(3000);
    }
  }
}

// Map the raw ADC reading to 0-100 % soil moisture
float readMoisture() {
  int raw = analogRead(PIN_MOISTURE);  // 0..4095
  return raw * 100.0f / 4095.0f;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  pinMode(PIN_RELAY, OUTPUT);
  setPump(false);
  dht.begin();

  connectWiFi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  connectMQTT();
  Serial.println("[Kisan Mitra] Field node ready, topics under " + String(TOPIC_PREFIX));
}

void loop() {
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();

  unsigned long now = millis();
  if (now - lastPublish < PUBLISH_INTERVAL_MS) return;
  lastPublish = now;

  float temperature = dht.readTemperature();
  float humidity    = dht.readHumidity();
  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("[DHT] Read failed, skipping");
    return;
  }
  float moisture = readMoisture();

  StaticJsonDocument<192> doc;
  doc["soil_moisture"] = round(moisture * 10) / 10.0;
  doc["temperature"]   = round(temperature * 10) / 10.0;
  doc["humidity"]      = round(humidity * 10) / 10.0;
  doc["pump"]          = pumpOn ? "ON" : "OFF";
  doc["device"]        = DEVICE_NAME;

  char buffer[192];
  serializeJson(doc, buffer);
  mqtt.publish(topicSensor.c_str(), buffer);
  Serial.printf("[Publish] moisture=%.1f%% T=%.1fC H=%.1f%% pump=%s\r\n",
                moisture, temperature, humidity, pumpOn ? "ON" : "OFF");
}
