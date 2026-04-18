#
# MultiButtonTest.py - This Python program demonstrates the
# functionality of multiple buttons and PWMLED controls from the
# gpiozero library by displaying a red or blue LED fading in and out.
#
# This code works with the test circuit that was built for module 7.
#
# Button behavior:
# - The first button (green) lights both LEDs solid.
# - The second button (red) turns off the blue LED and fades the red LED.
# - The third button (blue) turns off the red LED and fades the blue LED.
#
# ------------------------------------------------------------------
# Change History
# ------------------------------------------------------------------
# Version   |   Description
# ------------------------------------------------------------------
#    1      |   Initial Development
#    2      |   Refactored debug output and LED reset logic
# ------------------------------------------------------------------

# Import the Button and PWMLED classes used to control the hardware.
from gpiozero import Button, PWMLED

# Import sleep so the program can pause while looping.
from time import sleep

# Debug flag used to control whether or not messages print to the console.
DEBUG = True

# Create LED objects and map them to their GPIO pins.
red = PWMLED(18)
blue = PWMLED(23)


def debug_log(message):
    """
    Print debug messages only when DEBUG is enabled.
    """
    if DEBUG:
        print(message)


def reset_leds():
    """
    Turn both LEDs off before applying a new LED state.
    This keeps LED state changes consistent.
    """
    red.off()
    blue.off()


def bothOn():
    """
    Turn both LEDs on.
    """
    debug_log("* Both LEDs on")
    reset_leds()
    red.on()
    blue.on()


def redFade():
    """
    Turn off the blue LED and fade the red LED.
    """
    debug_log("* Fading Red")
    reset_leds()
    red.pulse()


def blueFade():
    """
    Turn off the red LED and fade the blue LED.
    """
    debug_log("* Fading Blue")
    reset_leds()
    blue.pulse()


# Configure each button and connect it to the correct function.
greenButton = Button(24)
greenButton.when_pressed = bothOn

redButton = Button(25)
redButton.when_pressed = redFade

blueButton = Button(12)
blueButton.when_pressed = blueFade

# Main loop flag.
repeat = True

# Keep the test program running until the user interrupts it.
while repeat:
    try:
        if greenButton.is_pressed:
            debug_log("Green Button Pressed")

        if redButton.is_pressed:
            debug_log("Red Button Pressed")

        if blueButton.is_pressed:
            debug_log("Blue Button Pressed")

        sleep(1)

    except KeyboardInterrupt:
        print("Cleaning up. Exiting...")
        repeat = False
        reset_leds()
        sleep(1)