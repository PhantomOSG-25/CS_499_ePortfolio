#
# ThermostatServer-Simulator.py - This Python code simulates a
# thermostat server. It reads the data that the thermostat sends
# over the serial port and prints it to the screen.
#
# This script loops until the user interrupts the program by
# pressing CTRL-C.
#
# ------------------------------------------------------------------
# Change History
# ------------------------------------------------------------------
# Version   |   Description
# ------------------------------------------------------------------
#    1      |   Initial Development
#    2      |   Refactored serial setup and read logic
# ------------------------------------------------------------------

import serial

DEBUG = True


def debug_log(message):
    """
    Print debug messages only when DEBUG is enabled.
    """
    if DEBUG:
        print(message)


def create_serial_connection():
    """
    Create and return the serial connection used to receive
    thermostat data from the Raspberry Pi.
    """
    return serial.Serial(
        port='/dev/ttyUSB0',
        baudrate=115200,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=1
    )


def read_serial_line(connection):
    """
    Read one line of data from the serial connection,
    decode it, and convert it to lowercase text.
    """
    try:
        return connection.readline().decode("utf-8").lower()
    except Exception as e:
        debug_log(f"Serial read error: {e}")
        return ""


# Create the serial connection.
ser = create_serial_connection()

# Main loop flag.
repeat = True

# Continuously read data until interrupted.
while repeat:
    try:
        dataline = read_serial_line(ser)

        if len(dataline) > 1:
            print(dataline)

    except KeyboardInterrupt:
        debug_log("Stopping thermostat server simulator...")
        repeat = False

# Close the serial connection cleanly.
try:
    ser.close()
except Exception:
    pass