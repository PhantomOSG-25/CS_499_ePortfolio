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
        # Force exactly 16 chars per line
        l1 = (line1 or "").ljust(16)[:16]
        l2 = (line2 or "").ljust(16)[:16]

        # Clear + write from home position
        self.lcd.clear()
        self.lcd.cursor_position(0, 0)
        self.lcd.message = l1 + "\n" + l2

    def cleanup(self):
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
    States: off, heat, cool
    """

    off = State(initial=True)
    heat = State()
    cool = State()

    setPoint = 72  # requirement

    cycle = off.to(heat) | heat.to(cool) | cool.to(off)

    endDisplay = False

    # ----- State transitions -----
    def on_enter_off(self):
        redLight.off()
        blueLight.off()
        if DEBUG:
            print("* Changing state to off")

    def on_enter_heat(self):
        self.updateLights()
        if DEBUG:
            print("* Changing state to heat")

    def on_exit_heat(self):
        redLight.off()

    def on_enter_cool(self):
        self.updateLights()
        if DEBUG:
            print("* Changing state to cool")

    def on_exit_cool(self):
        blueLight.off()

    # ----- Buttons -----
    def processTempStateButton(self):
        if DEBUG:
            print("Cycling Temperature State")
        self.cycle()

    def processTempIncButton(self):
        if DEBUG:
            print("Increasing Set Point")
        self.setPoint += 1
        self.updateLights()

    def processTempDecButton(self):
        if DEBUG:
            print("Decreasing Set Point")
        self.setPoint -= 1
        self.updateLights()

    # ----- Temperature -----
    def getFahrenheit(self) -> float:
        c = thSensor.temperature
        return (c * 9 / 5) + 32

    # ----- LED Logic (rubric) -----
    def updateLights(self):
        temp = floor(self.getFahrenheit())

        if DEBUG:
            print(f"State: {self.current_state.id}")
            print(f"SetPoint: {self.setPoint}")
            print(f"Temp: {temp}")

        if self.current_state.id == "off":
            redLight.off()
            blueLight.off()
            return

        if self.current_state.id == "heat":
            blueLight.off()
            if temp < self.setPoint:
                redLight.pulse()
            else:
                redLight.on()
            return

        if self.current_state.id == "cool":
            redLight.off()
            if temp > self.setPoint:
                blueLight.pulse()
            else:
                blueLight.on()
            return

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
            if DEBUG:
                print("Processing Display Info...")

            now = datetime.now()

            # Line 1: keep within 16 chars
            # "MM/DD HH:MM:SS" = 14 chars
            line1 = now.strftime("%m/%d %H:%M:%S")

            # Line 2 alternates (5 seconds temp, 5 seconds mode/setpoint)
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

            # UART every 30 seconds
            if DEBUG:
                print(f"Counter: {counter}")
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
        redLight.off()
        blueLight.off()
        try:
            ser.close()
        except Exception:
            pass