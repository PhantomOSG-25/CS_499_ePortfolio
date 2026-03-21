#
# Thermostat - Final Project (CS-350)
#
# Requirements implemented:
# 1) Default setpoint is 72°F
# 2) Read AHT20 temp via I2C
# 3) LEDs indicate heating/cooling
#    - HEAT: temp < setpoint => red pulse, else red solid
#    - COOL: temp > setpoint => blue pulse, else blue solid
#    - OFF : both off
# 4) Buttons:
#    - GPIO 24 cycles mode (off->heat->cool->off)
#    - GPIO 25 increases setpoint
#    - GPIO 12 decreases setpoint
# 5) LCD:
#    - Line 1: date/time always (kept within 16 chars)
#    - Line 2 alternates between temp and mode+setpoint
# 6) UART output every 30 seconds:
#    state,current_temp_f,setpoint_f
#

from time import sleep
from datetime import datetime
from math import floor
from threading import Thread

from statemachine import StateMachine, State

import board
import adafruit_ahtx0

import digitalio
import adafruit_character_lcd.character_lcd as characterlcd

import serial
from gpiozero import Button, PWMLED

DEBUG = True


def debug_log(message):
    """
    Print debug messages only when DEBUG is enabled.
    """
    if DEBUG:
        print(message)


# -----------------------------
# Sensor / I2C
# -----------------------------
i2c = board.I2C()
thSensor = adafruit_ahtx0.AHTx0(i2c)

# -----------------------------
# UART (Serial)
# -----------------------------
ser = serial.Serial(
    port="/dev/ttyS0",
    baudrate=115200,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

# -----------------------------
# LEDs (PWM)
# -----------------------------
# Matches MultiButtonTest.py
redLight = PWMLED(18)
blueLight = PWMLED(23)


def set_off():
    """
    Turn both LEDs off.
    """
    redLight.off()
    blueLight.off()


def set_heat(temp, setPoint):
    """
    Set LED behavior for heating mode.
    """
    blueLight.off()
    if temp < setPoint:
        redLight.pulse()
    else:
        redLight.on()


def set_cool(temp, setPoint):
    """
    Set LED behavior for cooling mode.
    """
    redLight.off()
    if temp > setPoint:
        blueLight.pulse()
    else:
        blueLight.on()


# -----------------------------
# LCD Manager
# -----------------------------
class ManagedDisplay:
    """
    Manages a 16x2 HD44780 LCD using Adafruit character LCD library.

    Important implementation notes:
    - Keep each line exactly 16 chars to avoid overflow/garbage characters.
    - On your installed library version, cursor_position is a METHOD:
        lcd.cursor_position(col, row)
      (do NOT assign a tuple)
    """

    def __init__(self):
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D27)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)

        self.lcd = characterlcd.Character_LCD_Mono(
            self.lcd_rs, self.lcd_en,
            self.lcd_d4, self.lcd_d5, self.lcd_d6, self.lcd_d7,
            16, 2
        )

        self.lcd.clear()

    def update(self, line1: str, line2: str):
        """
        Update the LCD display with two formatted lines.
        """
        l1 = (line1 or "").ljust(16)[:16]
        l2 = (line2 or "").ljust(16)[:16]

        self.lcd.clear()
        self.lcd.cursor_position(0, 0)
        self.lcd.message = l1 + "\n" + l2

    def cleanup(self):
        """
        Clear the LCD and release hardware resources.
        """
        self.lcd.clear()
        self.lcd_rs.deinit()
        self.lcd_en.deinit()
        self.lcd_d4.deinit()
        self.lcd_d5.deinit()
        self.lcd_d6.deinit()
        self.lcd_d7.deinit()


screen = ManagedDisplay()

# -----------------------------
# Thermostat State Machine
# -----------------------------
class TemperatureMachine(StateMachine):
    """
    Thermostat operating state machine.
    States: off, heat, cool
    """

    off = State(initial=True)
    heat = State()
    cool = State()

    setPoint = 72

    cycle = off.to(heat) | heat.to(cool) | cool.to(off)

    endDisplay = False

    # ----- State transitions -----
    def on_enter_off(self):
        set_off()
        debug_log("* Changing state to off")

    def on_enter_heat(self):
        self.updateLights()
        debug_log("* Changing state to heat")

    def on_exit_heat(self):
        redLight.off()

    def on_enter_cool(self):
        self.updateLights()
        debug_log("* Changing state to cool")

    def on_exit_cool(self):
        blueLight.off()

    # ----- Buttons -----
    def processTempStateButton(self):
        debug_log("Cycling Temperature State")
        self.cycle()

    def processTempIncButton(self):
        debug_log("Increasing Set Point")
        self.setPoint += 1
        self.updateLights()

    def processTempDecButton(self):
        debug_log("Decreasing Set Point")
        self.setPoint -= 1
        self.updateLights()

    # ----- Temperature -----
    def getFahrenheit(self) -> float:
        """
        Read the temperature from the sensor and convert it to Fahrenheit.
        If the sensor read fails, return the current setpoint to avoid
        crashing the application.
        """
        try:
            c = thSensor.temperature
            return (c * 9 / 5) + 32
        except Exception as e:
            debug_log(f"Temperature read error: {e}")
            return self.setPoint

    # ----- LED Logic -----
    def updateLights(self):
        temp = floor(self.getFahrenheit())

        debug_log(f"State: {self.current_state.id}")
        debug_log(f"SetPoint: {self.setPoint}")
        debug_log(f"Temp: {temp}")

        if self.current_state.id == "off":
            set_off()
        elif self.current_state.id == "heat":
            set_heat(temp, self.setPoint)
        elif self.current_state.id == "cool":
            set_cool(temp, self.setPoint)

    # ----- UART output -----
    def setupSerialOutput(self) -> str:
        temp = floor(self.getFahrenheit())
        return f"{self.current_state.id},{temp},{self.setPoint}"

    # ----- Display thread -----
    def run(self):
        t = Thread(target=self.manageMyDisplay, daemon=True)
        t.start()

    def manageMyDisplay(self):
        counter = 1
        altCounter = 1

        while not self.endDisplay:
            debug_log("Processing Display Info...")

            now = datetime.now()
            line1 = now.strftime("%m/%d %H:%M:%S")

            if altCounter < 6:
                line2 = f"Temp:{floor(self.getFahrenheit())}F"
                altCounter += 1
            else:
                line2 = f"{self.current_state.id.upper()} SP:{self.setPoint}F"
                altCounter += 1
                if altCounter >= 11:
                    self.updateLights()
                    altCounter = 1

            screen.update(line1, line2)

            debug_log(f"Counter: {counter}")
            if (counter % 30) == 0:
                ser.write((self.setupSerialOutput() + "\n").encode())
                counter = 1
            else:
                counter += 1

            sleep(1)

        screen.cleanup()


# -----------------------------
# Main
# -----------------------------
tsm = TemperatureMachine()
tsm.run()

# Buttons (matches MultiButtonTest.py)
greenButton = Button(24)
greenButton.when_pressed = tsm.processTempStateButton

redButton = Button(25)
redButton.when_pressed = tsm.processTempIncButton

blueButton = Button(12)
blueButton.when_pressed = tsm.processTempDecButton

repeat = True
while repeat:
    try:
        sleep(30)
    except KeyboardInterrupt:
        print("Cleaning up. Exiting...")
        repeat = False
        tsm.endDisplay = True
        sleep(1)
        set_off()
        try:
            ser.close()
        except Exception:
            pass