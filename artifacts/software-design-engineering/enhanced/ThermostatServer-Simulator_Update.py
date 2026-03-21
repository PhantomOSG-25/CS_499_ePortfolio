#
# ThermostatServer-Simulator.py - This is the Python code that will be used
# to simulate the Thermostat Server. It will read the data that the
# thermostat is sending to the server over the serial port and print it
# to the screen.
#
# This script will loop until the user interrupts the program by
# pressing CTRL-C
#
#------------------------------------------------------------------
# Change History
#------------------------------------------------------------------
# Version   |   Description
#------------------------------------------------------------------
#    1          Initial Development
#    2          Refactored serial setup and read logic
#------------------------------------------------------------------

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
    Read one line of data from the serial connection, decode it,
    and normalize it to lowercase text.
    """
    try:
        return connection.readline().decode("utf-8").lower()
    except Exception as e:
        debug_log(f"Serial read error: {e}")
        return ""


ser = create_serial_connection()

repeat = True

while repeat:
    try:
        dataline = read_serial_line(ser)

        if len(dataline) > 1:
            print(dataline)

    except KeyboardInterrupt:
        debug_log("Stopping thermostat server simulator...")
        repeat = False

try:
    ser.close()
except Exception:
    pass