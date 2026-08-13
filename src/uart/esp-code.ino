// car_no_ota.ino
// Derived from existing car.ino but with WiFi and ArduinoOTA removed.
// Purpose: communicate with Raspberry Pi over Serial2 (UART) and
// provide ultrasonic sensors, MQ2 analog read, servo, and motor controls.

#include <ESP32Servo.h>
#include <HardwareSerial.h> // For Serial2

// We will use Serial2 to talk to the Raspberry Pi
HardwareSerial PiSerial(2); // Use UART Port 2 (Pins 16 RX, 17 TX)

// --- Global Objects ---
Servo myServo;

// ===================================
// === PIN DEFINITIONS             ===
// ===================================

// --- Sensor 1 Pins ---
#define TRIG1_PIN 4
#define ECHO1_PIN 5
// --- Sensor 2 Pins ---
#define TRIG2_PIN 18
#define ECHO2_PIN 19
// --- Sensor 3 Pins ---
#define TRIG3_PIN 21
#define ECHO3_PIN 22

// --- New Sensor Pins ---
// The fitted sensor is an MQ-3 (alcohol), not an MQ2 (smoke/LPG). The names
// below and the "MQ2:" token in the DATA line are kept only because they are a
// wire contract with the Pi-side parser; renaming either without reflashing
// both ends breaks telemetry. The raw ADC count is reported and never
// interpreted, so the mislabel is cosmetic here -- but any threshold written
// against an MQ2 response curve would be meaningless.
#define MQ2_PIN 34     // Analog pin for the gas sensor (Pin 34 is ADC1_CH6)
#define SERVO_PIN 23   // Pin for Servo motor

// --- Motor PINS (Digital for now) ---
#define IN1 25  // Left motor forward
#define IN2 26  // Left motor backward
#define IN3 27  // Right motor forward
#define IN4 14  // Right motor backward

// --- UART Pins (defined by PiSerial object) ---
#define RXD2 16
#define TXD2 17

// ===================================
// === CONSTANTS AND GLOBALS       ===
// ===================================

// Servo limits
#define SERVO_MIN_ANGLE 0
#define SERVO_MAX_ANGLE 180
#define SERVO_DEFAULT_ANGLE 90

// === COLLISION AVOIDANCE CONSTANTS ===
#define STOP_DISTANCE_CM 10       // Emergency stop distance
#define WARNING_DISTANCE_CM 20    // Warning zone - block forward
#define SCAN_ROTATE_TIME_MS 200   // Time to rotate during scan
#define SCAN_PAUSE_MS 100         // Pause after rotation to let sensors settle

// Command buffer
#define CMD_BUFFER_SIZE 128
char cmdBuffer[CMD_BUFFER_SIZE];
int cmdIndex = 0;

// Current states
int currentServoAngle = SERVO_DEFAULT_ANGLE;
int leftMotorSpeed = 0;
int rightMotorSpeed = 0;

// === COLLISION AVOIDANCE STATE ===
bool motorsEnabled = true;           // Can we drive forward?
bool obstacleDetected = false;       // Is there an obstacle in stop zone?
bool inWarningZone = false;          // Is there an obstacle in warning zone?
long lastSensorDistances[3] = {-1, -1, -1};  // S1, S2, S3 cached
unsigned long lastCollisionCheck = 0;
#define COLLISION_CHECK_INTERVAL_MS 20  // Check every 20ms (50Hz)

// ===================================
// === FUNCTION PROTOTYPES         ===
// ===================================
void moveMotors(int leftDirection, int rightDirection);
void moveForward(int speed);
void moveBackward(int speed);
void turnLeft(int speed);
void turnRight(int speed);
void stopMotors();
long readDistance(int trigPin, int echoPin);
void handleCommand(String command, String source);
void sendAck(String cmd, String status);
void sendStatus();
int parseIntParam(String cmd, int defaultVal);

// === COLLISION AVOIDANCE FUNCTIONS ===
void checkCollision();
void emergencyStop();
void sendCollisionAlert(const char* reason);
void performScan();

// ===================================
// === SETUP                       ===
// ===================================

void setup() {
  // Serial for USB debugging
  Serial.begin(115200);
  delay(10);
  // Start Serial2 on pins 16 (RX) and 17 (TX)
  PiSerial.begin(115200, SERIAL_8N1, RXD2, TXD2);

  Serial.println("\n--- ESP32 Robot (no OTA) starting ---");
  PiSerial.println("ESP32 Ready (no OTA).");

  // --- Motor Setup (Digital for now) ---
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  stopMotors(); // Start with motors stopped
  Serial.println("Motor driver (Digital) ready.");

  // --- Ultrasonic Sensor Setup ---
  pinMode(TRIG1_PIN, OUTPUT);
  pinMode(ECHO1_PIN, INPUT);
  pinMode(TRIG2_PIN, OUTPUT);
  pinMode(ECHO2_PIN, INPUT);
  pinMode(TRIG3_PIN, OUTPUT);
  pinMode(ECHO3_PIN, INPUT);
  Serial.println("Ultrasonic sensors ready.");

  // --- New Sensor Setup ---
  pinMode(MQ2_PIN, INPUT); // Set MQ2 pin as input
  myServo.attach(SERVO_PIN);
  myServo.write(SERVO_DEFAULT_ANGLE); // Center the servo
  Serial.println("MQ2 sensor and Servo ready.");

  Serial.println("--- Autonomous Robot Controller Ready (no OTA) ---");
  Serial.println("Protocol: CMD or CMD:PARAM (sent over Serial2/USB)");
}

// ===================================
// === MAIN LOOP                   ===
// ===================================

void loop() {
  // === 1. READ ALL SENSORS ===
  long dist1 = readDistance(TRIG1_PIN, ECHO1_PIN);
  long dist2 = readDistance(TRIG2_PIN, ECHO2_PIN);
  long dist3 = readDistance(TRIG3_PIN, ECHO3_PIN);
  int mq2_value = analogRead(MQ2_PIN); // Read analog value (0-4095)

  // Cache sensor readings for collision check
  lastSensorDistances[0] = dist1;
  lastSensorDistances[1] = dist2;
  lastSensorDistances[2] = dist3;

  // === 2. COLLISION AVOIDANCE - HIGHEST PRIORITY ===
  checkCollision();

  // === 3. SEND DATA TO RASPBERRY PI ===
  // Send data as a single, comma-separated line ending with '\n'
  PiSerial.print("DATA:S1:"); PiSerial.print(dist1);
  PiSerial.print(",S2:"); PiSerial.print(dist2);
  PiSerial.print(",S3:"); PiSerial.print(dist3);
  PiSerial.print(",MQ2:"); PiSerial.print(mq2_value);
  PiSerial.print(",SERVO:"); PiSerial.print(currentServoAngle);
  PiSerial.print(",LMOTOR:"); PiSerial.print(leftMotorSpeed);
  PiSerial.print(",RMOTOR:"); PiSerial.print(rightMotorSpeed);
  PiSerial.print(",OBSTACLE:"); PiSerial.print(obstacleDetected ? 1 : 0);
  PiSerial.print(",WARNING:"); PiSerial.print(inWarningZone ? 1 : 0);
  PiSerial.println(); // Send newline

  // === 4. CHECK FOR COMMANDS ===
  // Read from USB Serial Monitor
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdIndex > 0) {
        cmdBuffer[cmdIndex] = '\0';
        handleCommand(String(cmdBuffer), "USB");
        cmdIndex = 0;
      }
    } else if (cmdIndex < CMD_BUFFER_SIZE - 1) {
      cmdBuffer[cmdIndex++] = c;
    }
  }

  // Read from Raspberry Pi over UART (Serial2)
  while (PiSerial.available() > 0) {
    char c = PiSerial.read();
    if (c == '\n' || c == '\r') {
      if (cmdIndex > 0) {
        cmdBuffer[cmdIndex] = '\0';
        handleCommand(String(cmdBuffer), "Pi");
        cmdIndex = 0;
      }
    } else if (cmdIndex < CMD_BUFFER_SIZE - 1) {
      cmdBuffer[cmdIndex++] = c;
    }
  }

  // === 5. PRINT TO SERIAL MONITOR (for debugging) ===
  Serial.print("S1: "); Serial.print(dist1);
  Serial.print(" cm | S2: "); Serial.print(dist2);
  Serial.print(" cm | S3: "); Serial.print(dist3);
  Serial.print(" cm | MQ2: "); Serial.print(mq2_value);
  Serial.print(" | OBS: "); Serial.print(obstacleDetected ? "Y" : "N");
  Serial.print(" | WARN: "); Serial.print(inWarningZone ? "Y" : "N");
  Serial.print(" | MotorOK: "); Serial.println(motorsEnabled ? "Y" : "N");

  // --- DELAY ---
  delay(50); // Send ~20 Hz updates
}

// ===================================
// === COMMAND HANDLER             ===
// ===================================

void handleCommand(String command, String source) {
  Serial.print("Command '");
  Serial.print(command);
  Serial.print("' from ");
  Serial.println(source);

  command.trim();
  // Accept mixed case; normalize command token only
  String cmdu = command;
  cmdu.toUpperCase();

  if (cmdu.startsWith("SERVO:")) {
    int angle = parseIntParam(command, SERVO_DEFAULT_ANGLE);
    angle = constrain(angle, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE);
    myServo.write(angle);
    currentServoAngle = angle;
    sendAck("SERVO", "OK:" + String(angle));
  } else if (cmdu.startsWith("FORWARD")) {
    // === COLLISION CHECK: Block forward if obstacle in warning zone ===
    if (!motorsEnabled || obstacleDetected) {
      sendAck("FORWARD", "BLOCKED:OBSTACLE");
      Serial.println("FORWARD BLOCKED - Obstacle detected!");
      return;
    }
    if (inWarningZone) {
      sendAck("FORWARD", "BLOCKED:WARNING_ZONE");
      Serial.println("FORWARD BLOCKED - In warning zone!");
      return;
    }
    moveForward(255);  // Digital full speed
    sendAck("FORWARD", "OK");
  } else if (cmdu.startsWith("BACKWARD")) {
    // Backward is always allowed (escape maneuver)
    moveBackward(255);
    sendAck("BACKWARD", "OK");
  } else if (cmdu.startsWith("LEFT")) {
    turnLeft(255);
    sendAck("LEFT", "OK");
  } else if (cmdu.startsWith("RIGHT")) {
    turnRight(255);
    sendAck("RIGHT", "OK");
  } else if (cmdu == "STOP") {
    stopMotors();
    sendAck("STOP", "OK");
  } else if (cmdu == "STATUS") {
    sendStatus();
  } else if (cmdu == "RESET") {
    myServo.write(SERVO_DEFAULT_ANGLE);
    currentServoAngle = SERVO_DEFAULT_ANGLE;
    stopMotors();
    motorsEnabled = true;
    obstacleDetected = false;
    inWarningZone = false;
    sendAck("RESET", "OK");
  } else if (cmdu == "SCAN") {
    // Initiate 360-degree scan by rotating robot
    performScan();
    sendAck("SCAN", "OK");
  } else if (cmdu == "CLEARBLOCK") {
    // Manual override to clear obstacle block (use with caution!)
    motorsEnabled = true;
    obstacleDetected = false;
    sendAck("CLEARBLOCK", "OK");
  } else {
    sendAck(command, "UNKNOWN");
  }
}

// ===================================
// === MOTOR FUNCTIONS (Digital)   ===
// ===================================

void moveMotors(int leftDirection, int rightDirection) {
  if (leftDirection > 0)     { digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW); }
  else if (leftDirection < 0) { digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH); }
  else                        { digitalWrite(IN1, LOW);  digitalWrite(IN2, LOW); }

  if (rightDirection > 0)     { digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW); }
  else if (rightDirection < 0){ digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH); }
  else                        { digitalWrite(IN3, LOW);  digitalWrite(IN4, LOW); }
}

void moveForward(int speed) { moveMotors(1, 1); }
void moveBackward(int speed) { moveMotors(-1, -1); }
void turnLeft(int speed) { moveMotors(1, -1); }
void turnRight(int speed) { moveMotors(-1, 1); }
void stopMotors() { moveMotors(0, 0); }

// ===================================
// === ULTRASONIC SENSOR FUNCTION  ===
// ===================================

long readDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000);
  if (duration == 0) return -1; // Timeout
  long distance = duration * 0.01715; // microseconds to cm
  return distance;
}

// ===================================
// === UTILITIES                   ===
// ===================================

void sendAck(String cmd, String status) {
  PiSerial.print("ACK:");
  PiSerial.print(cmd);
  PiSerial.print(":");
  PiSerial.println(status);
}

void sendStatus() {
  PiSerial.print("STATUS:SERVO:");
  PiSerial.print(currentServoAngle);
  PiSerial.print(",LMOTOR:");
  PiSerial.print(leftMotorSpeed);
  PiSerial.print(",RMOTOR:");
  PiSerial.println(rightMotorSpeed);
}

int parseIntParam(String cmd, int defaultVal) {
  int colonIndex = cmd.indexOf(':');
  if (colonIndex != -1) {
    String param = cmd.substring(colonIndex + 1);
    param.trim();
    return param.toInt();
  }
  return defaultVal;
}

// ===================================
// === COLLISION AVOIDANCE         ===
// ===================================

void checkCollision() {
  // Get minimum distance from all front-facing sensors
  long minDist = 9999;
  int closestSensor = -1;
  
  for (int i = 0; i < 3; i++) {
    long d = lastSensorDistances[i];
    // Ignore invalid readings (-1 = timeout)
    if (d > 0 && d < minDist) {
      minDist = d;
      closestSensor = i + 1;  // S1, S2, S3
    }
  }
  
  // Previous states for change detection
  bool wasObstacle = obstacleDetected;
  bool wasWarning = inWarningZone;
  
  // === EMERGENCY STOP ZONE (<10cm) ===
  if (minDist <= STOP_DISTANCE_CM) {
    if (!obstacleDetected) {
      emergencyStop();
      sendCollisionAlert("EMERGENCY_STOP");
    }
    obstacleDetected = true;
    motorsEnabled = false;
    inWarningZone = true;
  }
  // === WARNING ZONE (10-20cm) ===
  else if (minDist <= WARNING_DISTANCE_CM) {
    obstacleDetected = false;
    inWarningZone = true;
    motorsEnabled = true;  // Can still turn/backup, but forward blocked in handleCommand
    if (!wasWarning) {
      sendCollisionAlert("WARNING_ZONE");
    }
  }
  // === CLEAR ZONE (>20cm) ===
  else {
    obstacleDetected = false;
    inWarningZone = false;
    motorsEnabled = true;
    // Only notify once when clearing
    if (wasObstacle || wasWarning) {
      sendCollisionAlert("CLEAR");
    }
  }
}

void emergencyStop() {
  // Immediately stop all motors
  stopMotors();
  Serial.println("!!! EMERGENCY STOP - OBSTACLE TOO CLOSE !!!");
}

void sendCollisionAlert(const char* reason) {
  // Send alert to Pi over UART
  PiSerial.print("ALERT:COLLISION:");
  PiSerial.print(reason);
  PiSerial.print(",S1:");
  PiSerial.print(lastSensorDistances[0]);
  PiSerial.print(",S2:");
  PiSerial.print(lastSensorDistances[1]);
  PiSerial.print(",S3:");
  PiSerial.println(lastSensorDistances[2]);
}

void performScan() {
  // Perform a 360-degree scan by rotating the robot
  // Since no servo scanning, robot rotates and reads sensors
  Serial.println("Starting 360 scan...");
  PiSerial.println("SCAN:START");
  
  // We'll do 8 positions (every 45 degrees = ~200ms rotation each)
  int scanResults[8][3];  // 8 positions, 3 sensors each
  
  for (int pos = 0; pos < 8; pos++) {
    // Read current distances
    scanResults[pos][0] = readDistance(TRIG1_PIN, ECHO1_PIN);
    scanResults[pos][1] = readDistance(TRIG2_PIN, ECHO2_PIN);
    scanResults[pos][2] = readDistance(TRIG3_PIN, ECHO3_PIN);
    
    // Send scan data for this position
    PiSerial.print("SCAN:POS:");
    PiSerial.print(pos * 45);  // Approximate angle
    PiSerial.print(",S1:");
    PiSerial.print(scanResults[pos][0]);
    PiSerial.print(",S2:");
    PiSerial.print(scanResults[pos][1]);
    PiSerial.print(",S3:");
    PiSerial.println(scanResults[pos][2]);
    
    // Don't rotate on last position
    if (pos < 7) {
      // Rotate right for ~45 degrees
      turnRight(255);
      delay(SCAN_ROTATE_TIME_MS);
      stopMotors();
      delay(SCAN_PAUSE_MS);  // Let sensors settle
    }
  }
  
  // Find safest direction (position with max average distance)
  int bestPos = 0;
  long bestAvg = 0;
  
  for (int pos = 0; pos < 8; pos++) {
    long avg = 0;
    int validCount = 0;
    for (int s = 0; s < 3; s++) {
      if (scanResults[pos][s] > 0) {
        avg += scanResults[pos][s];
        validCount++;
      }
    }
    if (validCount > 0) {
      avg /= validCount;
      if (avg > bestAvg) {
        bestAvg = avg;
        bestPos = pos;
      }
    }
  }
  
  // Report best direction
  PiSerial.print("SCAN:BEST:");
  PiSerial.print(bestPos * 45);
  PiSerial.print(",DIST:");
  PiSerial.println(bestAvg);
  
  PiSerial.println("SCAN:COMPLETE");
  Serial.print("Scan complete. Best direction: ");
  Serial.print(bestPos * 45);
  Serial.print(" deg, avg dist: ");
  Serial.println(bestAvg);
}
