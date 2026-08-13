#
# Thermostat - Final Project (CS-350)
#
# This program simulates a thermostat system running on a Raspberry Pi.
# It reads temperature data from an AHT20 sensor, allows the user to
# change the system mode and setpoint using buttons, displays system
# information on an LCD screen, controls LEDs for heating and cooling,
# sends status over serial communication, and stores readings in a
# SQLite database.
#
# Requirements implemented:
# 1) Default setpoint is 72°F
# 2) Read AHT20 temperature via I2C
# 3) LEDs indicate heating/cooling
#    - HEAT: temp below lower bound => red pulse, else red solid
#    - COOL: temp above upper bound => blue pulse, else blue solid
#    - OFF : both off
# 4) Buttons:
#    - GPIO 24 cycles mode (off -> heat -> cool -> off)
#    - GPIO 25 increases setpoint
#    - GPIO 12 decreases setpoint
# 5) LCD:
#    - Line 1: date/time always (kept within 16 chars)
#    - Line 2 alternates between temp and mode + setpoint
# 6) UART output every 30 seconds:
#    state,current_temp_f,setpoint_f
# 7) SQLite database logging every 30 seconds:
#    timestamp,state,temperature,setpoint
#

from time import sleep
from datetime import datetime
from math import floor
from threading import Thread
import sqlite3

from statemachine import StateMachine, State

import board
import adafruit_ahtx0

import digitalio
import adafruit_character_lcd.character_lcd as characterlcd

import serial
from gpiozero import Button, PWMLED

# Global debug flag.
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
# Create the I2C connection and initialize the temperature sensor.
i2c = board.I2C()
thSensor = adafruit_ahtx0.AHTx0(i2c)

# -----------------------------
# UART (Serial)
# -----------------------------
# Create the serial connection used for sending thermostat data.
ser = serial.Serial(
    port="/dev/ttyS0",
    baudrate=115200,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

# -----------------------------
# Database (SQLite)
# -----------------------------
DATABASE_PATH = "thermostat.db"


def initialize_database() -> sqlite3.Connection:
    """
    Create the SQLite connection in the thread that will use it and
    ensure the temperature log table exists.
    """
    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS temperature_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            state TEXT NOT NULL,
            temperature INTEGER NOT NULL,
            setpoint INTEGER NOT NULL
        )
    """)
    connection.commit()
    return connection

# -----------------------------
# LEDs (PWM)
# -----------------------------
# Create LED objects used to represent heating and cooling.
redLight = PWMLED(18)
blueLight = PWMLED(23)


def set_off():
    """
    Turn both LEDs off.
    """
    redLight.off()
    blueLight.off()


def set_heat_active():
    """
    Heating is actively needed.
    Use a pulsing red LED to show active heating.
    """
    blueLight.off()
    redLight.pulse()


def set_heat_idle():
    """
    Heat mode is selected, but the temperature is within the buffer range.
    Use a solid red LED to show the mode without active heating.
    """
    blueLight.off()
    redLight.on()


def set_cool_active():
    """
    Cooling is actively needed.
    Use a pulsing blue LED to show active cooling.
    """
    redLight.off()
    blueLight.pulse()


def set_cool_idle():
    """
    Cool mode is selected, but the temperature is within the buffer range.
    Use a solid blue LED to show the mode without active cooling.
    """
    redLight.off()
    blueLight.on()


# -----------------------------
# LCD Manager
# -----------------------------
class ManagedDisplay:
    """
    Manage a 16x2 HD44780 LCD using the Adafruit character LCD library.
    """

    def __init__(self):
        # Create GPIO objects for the LCD pins.
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D27)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)

        # Initialize the 16x2 LCD display.
        self.lcd = characterlcd.Character_LCD_Mono(
            self.lcd_rs,
            self.lcd_en,
            self.lcd_d4,
            self.lcd_d5,
            self.lcd_d6,
            self.lcd_d7,
            16,
            2
        )

        self.lcd.clear()

    def update(self, line1: str, line2: str):
        """
        Update the LCD display with two formatted lines.
        Each line is forced to fit within 16 characters.
        """
        l1 = (line1 or "").ljust(16)[:16]
        l2 = (line2 or "").ljust(16)[:16]

        self.lcd.clear()
        self.lcd.cursor_position(0, 0)
        self.lcd.message = l1 + "\n" + l2

    def cleanup(self):
        """
        Clear the LCD and release the LCD GPIO resources.
        """
        self.lcd.clear()
        self.lcd_rs.deinit()
        self.lcd_en.deinit()
        self.lcd_d4.deinit()
        self.lcd_d5.deinit()
        self.lcd_d6.deinit()
        self.lcd_d7.deinit()


# Create the LCD manager object.
screen = ManagedDisplay()

# -----------------------------
# Thermostat State Machine
# -----------------------------
class TemperatureMachine(StateMachine):
    """
    Thermostat operating state machine.
    States: off, heat, cool
    """

    # Define thermostat states.
    off = State(initial=True)
    heat = State()
    cool = State()

    # Default setpoint and temperature buffer.
    setPoint = 72
    buffer = 2

    # State transition sequence.
    cycle = off.to(heat) | heat.to(cool) | cool.to(off)

    # Display thread control flag.
    endDisplay = False

    # ----- State transitions -----
    def on_enter_off(self):
        """
        Handle entry into the off state.
        """
        set_off()
        debug_log("* Changing state to off")

    def on_enter_heat(self):
        """
        Handle entry into the heat state.
        """
        self.updateLights()
        debug_log("* Changing state to heat")

    def on_exit_heat(self):
        """
        Clean up heating LED state when leaving heat mode.
        """
        redLight.off()

    def on_enter_cool(self):
        """
        Handle entry into the cool state.
        """
        self.updateLights()
        debug_log("* Changing state to cool")

    def on_exit_cool(self):
        """
        Clean up cooling LED state when leaving cool mode.
        """
        blueLight.off()

    # ----- Buttons -----
    def processTempStateButton(self):
        """
        Cycle the thermostat mode.
        """
        debug_log("Cycling Temperature State")
        self.cycle()

    def processTempIncButton(self):
        """
        Increase the thermostat setpoint by 1 degree.
        """
        debug_log("Increasing Set Point")
        self.setPoint += 1
        self.updateLights()

    def processTempDecButton(self):
        """
        Decrease the thermostat setpoint by 1 degree.
        """
        debug_log("Decreasing Set Point")
        self.setPoint -= 1
        self.updateLights()

    # ----- Temperature -----
    def getFahrenheit(self) -> float:
        """
        Read temperature from the sensor and convert it to Fahrenheit.
        If the sensor fails, return the current setpoint to avoid a crash.
        """
        try:
            celsius = thSensor.temperature
            return (celsius * 9 / 5) + 32
        except Exception as e:
            debug_log(f"Temperature read error: {e}")
            return self.setPoint

    def getLowerBound(self) -> int:
        """
        Return the lower bound of the thermostat buffer range.
        """
        return self.setPoint - self.buffer

    def getUpperBound(self) -> int:
        """
        Return the upper bound of the thermostat buffer range.
        """
        return self.setPoint + self.buffer

    # ----- LED / control logic -----
    def updateLights(self):
        """
        Update LED behavior based on current state and temperature.
        A temperature buffer is used to reduce rapid state changes.
        """
        temp = floor(self.getFahrenheit())
        lower_bound = self.getLowerBound()
        upper_bound = self.getUpperBound()

        debug_log(f"State: {self.current_state.id}")
        debug_log(f"SetPoint: {self.setPoint}")
        debug_log(f"Buffer: +/- {self.buffer}")
        debug_log(f"Temp: {temp}")
        debug_log(f"Lower Bound: {lower_bound}")
        debug_log(f"Upper Bound: {upper_bound}")

        if self.current_state.id == "off":
            set_off()
            return

        if self.current_state.id == "heat":
            if temp <= lower_bound:
                set_heat_active()
            else:
                set_heat_idle()
            return

        if self.current_state.id == "cool":
            if temp >= upper_bound:
                set_cool_active()
            else:
                set_cool_idle()
            return

    # ----- UART output -----
    def setupSerialOutput(self) -> str:
        """
        Build the serial output string in the required format.
        """
        temp = floor(self.getFahrenheit())
        return f"{self.current_state.id},{temp},{self.setPoint}"

    # ----- Database logging -----
    def log_to_database(self, connection: sqlite3.Connection):
        """
        Store the current thermostat reading in the database.
        """
        try:
            temp = floor(self.getFahrenheit())
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            connection.execute("""
                INSERT INTO temperature_log (timestamp, state, temperature, setpoint)
                VALUES (?, ?, ?, ?)
            """, (timestamp, self.current_state.id, temp, self.setPoint))

            connection.commit()
            debug_log("Database log saved")

        except Exception as e:
            debug_log(f"Database error: {e}")

    # ----- Display thread -----
    def run(self):
        """
        Start the display management thread.
        """
        display_thread = Thread(target=self.manageMyDisplay, daemon=True)
        display_thread.start()

    def manageMyDisplay(self):
        """
        Manage LCD output, serial logging, and database logging over time.
        """
        counter = 1
        altCounter = 1
        connection = initialize_database()

        try:
            while not self.endDisplay:
                debug_log("Processing Display Info...")

                now = datetime.now()
                line1 = now.strftime("%m/%d %H:%M:%S")

                # Alternate line 2 between temperature and state/setpoint.
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

                # Every 30 seconds, send serial output and log to database.
                debug_log(f"Counter: {counter}")
                if (counter % 30) == 0:
                    ser.write((self.setupSerialOutput() + "\n").encode())
                    self.log_to_database(connection)
                    counter = 1
                else:
                    counter += 1

                sleep(1)
        finally:
            connection.close()
            screen.cleanup()


# -----------------------------
# Main
# -----------------------------
# Create the thermostat state machine and start the display thread.
tsm = TemperatureMachine()
tsm.run()

# Configure buttons and map them to thermostat actions.
greenButton = Button(24)
greenButton.when_pressed = tsm.processTempStateButton

redButton = Button(25)
redButton.when_pressed = tsm.processTempIncButton

blueButton = Button(12)
blueButton.when_pressed = tsm.processTempDecButton

# Main loop keeps the program alive until interrupted.
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

        # Close the serial connection safely.
        try:
            ser.close()
        except Exception:
            pass
