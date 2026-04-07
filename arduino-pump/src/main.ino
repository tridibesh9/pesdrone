#ifdef ARDUINO
// Arduino toolchain injects core headers for .ino files.
#else
#include <stddef.h>
#include <stdint.h>

#define HIGH 1
#define LOW 0
#define OUTPUT 1

struct SerialStub {
  void begin(unsigned long) {}
  int available() { return 0; }
  int read() { return 0; }
  size_t write(uint8_t) { return 1; }
};

static SerialStub Serial;

inline void pinMode(uint8_t, uint8_t) {}
inline void analogWrite(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t, uint8_t) {}
inline uint32_t millis() {
  static uint32_t t = 0;
  t += 10;
  return t;
}
#endif

static const uint8_t START_BYTE = 0xAA;
static const uint8_t CMD_SET_PUMP_PWM = 0x01;
static const uint8_t CMD_PULSE_SPRAY_MS = 0x02;
static const uint8_t CMD_VALVE_ON_OFF = 0x03;
static const uint8_t CMD_HEARTBEAT_REQUEST = 0x04;
static const uint8_t CMD_EMERGENCY_STOP = 0x05;

static const uint8_t STATUS_HEARTBEAT = 0x81;
static const uint8_t STATUS_ACK = 0x82;
static const uint8_t STATUS_NACK = 0x83;

static const uint8_t ERROR_BAD_LENGTH = 0x01;
static const uint8_t ERROR_UNKNOWN_COMMAND = 0x02;
static const uint8_t ERROR_BAD_CHECKSUM = 0x03;

static const uint8_t PUMP_PIN = 9;
static const uint8_t VALVE_PIN = 8;

static const uint32_t HEARTBEAT_EMIT_MS = 200;
static const uint32_t COMMAND_TIMEOUT_MS = 1000;

enum PumpState : uint8_t {
  STATE_IDLE = 0,
  STATE_ARMED = 1,
  STATE_SPRAYING = 2,
  STATE_FAULT = 3,
  STATE_ESTOP = 4
};

PumpState g_state = STATE_IDLE;
uint8_t g_faultCode = 0;
uint8_t g_currentPwm = 0;
bool g_valveOn = false;

uint32_t g_lastCommandMs = 0;
uint32_t g_lastHeartbeatMs = 0;
uint32_t g_pulseEndMs = 0;

enum ParseState : uint8_t {
  WAIT_START,
  READ_CMD,
  READ_LEN,
  READ_PAYLOAD,
  READ_CHECKSUM
};

ParseState g_parseState = WAIT_START;
uint8_t g_cmd = 0;
uint8_t g_len = 0;
uint8_t g_payload[255];
uint8_t g_payloadIndex = 0;

uint8_t checksum(uint8_t cmd, uint8_t len, const uint8_t* payload) {
  uint8_t value = cmd ^ len;
  for (uint8_t i = 0; i < len; i++) {
    value ^= payload[i];
  }
  return value;
}

void writeFrame(uint8_t cmd, const uint8_t* payload, uint8_t len) {
  uint8_t cs = checksum(cmd, len, payload);
  Serial.write(START_BYTE);
  Serial.write(cmd);
  Serial.write(len);
  for (uint8_t i = 0; i < len; i++) {
    Serial.write(payload[i]);
  }
  Serial.write(cs);
}

void sendAck(uint8_t ackCmd) {
  uint8_t payload[1] = {ackCmd};
  writeFrame(STATUS_ACK, payload, 1);
}

void sendNack(uint8_t nackCmd, uint8_t errorCode) {
  uint8_t payload[2] = {nackCmd, errorCode};
  writeFrame(STATUS_NACK, payload, 2);
}

void sendHeartbeat() {
  uint8_t payload[3] = {static_cast<uint8_t>(g_state), g_faultCode, g_currentPwm};
  writeFrame(STATUS_HEARTBEAT, payload, 3);
}

void setPumpPwm(uint8_t pwm) {
  g_currentPwm = pwm;
  analogWrite(PUMP_PIN, pwm);
}

void setValve(bool on) {
  g_valveOn = on;
  digitalWrite(VALVE_PIN, on ? HIGH : LOW);
}

void forcePumpOff() {
  setPumpPwm(0);
  setValve(false);
}

void emergencyStop() {
  g_state = STATE_ESTOP;
  g_faultCode = 0;
  forcePumpOff();
}

void handleCommand(uint8_t cmd, const uint8_t* payload, uint8_t len) {
  g_lastCommandMs = millis();

  switch (cmd) {
    case CMD_SET_PUMP_PWM:
      if (len != 1) {
        sendNack(cmd, ERROR_BAD_LENGTH);
        return;
      }
      if (g_state == STATE_ESTOP) {
        sendNack(cmd, ERROR_UNKNOWN_COMMAND);
        return;
      }
      g_state = STATE_ARMED;
      setPumpPwm(payload[0]);
      sendAck(cmd);
      break;

    case CMD_PULSE_SPRAY_MS:
      if (len != 2) {
        sendNack(cmd, ERROR_BAD_LENGTH);
        return;
      }
      if (g_state == STATE_ESTOP) {
        sendNack(cmd, ERROR_UNKNOWN_COMMAND);
        return;
      }
      {
        uint16_t duration = (static_cast<uint16_t>(payload[0]) << 8) | payload[1];
        g_state = STATE_SPRAYING;
        setValve(true);
        setPumpPwm(g_currentPwm == 0 ? 200 : g_currentPwm);
        g_pulseEndMs = millis() + duration;
        sendAck(cmd);
      }
      break;

    case CMD_VALVE_ON_OFF:
      if (len != 1) {
        sendNack(cmd, ERROR_BAD_LENGTH);
        return;
      }
      if (g_state == STATE_ESTOP) {
        sendNack(cmd, ERROR_UNKNOWN_COMMAND);
        return;
      }
      setValve(payload[0] != 0);
      if (!g_valveOn && g_state == STATE_SPRAYING) {
        g_state = STATE_ARMED;
      }
      sendAck(cmd);
      break;

    case CMD_HEARTBEAT_REQUEST:
      if (len != 0) {
        sendNack(cmd, ERROR_BAD_LENGTH);
        return;
      }
      sendAck(cmd);
      sendHeartbeat();
      break;

    case CMD_EMERGENCY_STOP:
      if (len != 0) {
        sendNack(cmd, ERROR_BAD_LENGTH);
        return;
      }
      emergencyStop();
      sendAck(cmd);
      break;

    default:
      sendNack(cmd, ERROR_UNKNOWN_COMMAND);
      break;
  }
}

void consumeByte(uint8_t byteValue) {
  switch (g_parseState) {
    case WAIT_START:
      if (byteValue == START_BYTE) {
        g_parseState = READ_CMD;
      }
      break;

    case READ_CMD:
      g_cmd = byteValue;
      g_parseState = READ_LEN;
      break;

    case READ_LEN:
      g_len = byteValue;
      g_payloadIndex = 0;
      g_parseState = (g_len == 0) ? READ_CHECKSUM : READ_PAYLOAD;
      break;

    case READ_PAYLOAD:
      g_payload[g_payloadIndex++] = byteValue;
      if (g_payloadIndex >= g_len) {
        g_parseState = READ_CHECKSUM;
      }
      break;

    case READ_CHECKSUM:
      if (checksum(g_cmd, g_len, g_payload) != byteValue) {
        g_faultCode = ERROR_BAD_CHECKSUM;
        g_state = STATE_FAULT;
        forcePumpOff();
        sendNack(g_cmd, ERROR_BAD_CHECKSUM);
      } else {
        handleCommand(g_cmd, g_payload, g_len);
      }
      g_parseState = WAIT_START;
      break;
  }
}

void setup() {
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(VALVE_PIN, OUTPUT);
  forcePumpOff();

  Serial.begin(115200);
  g_lastCommandMs = millis();
  g_lastHeartbeatMs = millis();
}

void loop() {
  while (Serial.available() > 0) {
    consumeByte(static_cast<uint8_t>(Serial.read()));
  }

  uint32_t now = millis();

  if (g_state == STATE_SPRAYING && now >= g_pulseEndMs) {
    setValve(false);
    setPumpPwm(0);
    g_state = STATE_ARMED;
  }

  if (now - g_lastCommandMs > COMMAND_TIMEOUT_MS && g_state != STATE_ESTOP) {
    g_state = STATE_FAULT;
    g_faultCode = 0x10;
    forcePumpOff();
  }

  if (now - g_lastHeartbeatMs >= HEARTBEAT_EMIT_MS) {
    sendHeartbeat();
    g_lastHeartbeatMs = now;
  }
}
