#
# MultiButtonTest.py - This is the Python code used to demonstrate
# the functionality of multiple buttons and PWMLED controls from the
# gpiozero library by displaying a Red or Blue LED fading in and out.
#
# This code works with the test circuit that was built for module 7.
#
# The first button (green) will light both LEDs solid.
# The second button (Red) will turn off the Blue LED and fade the
# Red LED.
# The third button (Blue) will turn off the Red LED and fade the
# Blue LED.
#
#------------------------------------------------------------------
# Change History
#------------------------------------------------------------------
# Version   |   Description
#------------------------------------------------------------------
#    1          Initial Development
#    2          Refactored debug output and LED reset logic
#------------------------------------------------------------------

##
## Imports required to handle our Button, and our PWMLED devices
##
from gpiozero import Button, PWMLED

##
## Import required to allow us to pause for a specified length of time
##
from time import sleep

##
## DEBUG flag - boolean value to indicate whether or not to print
## status messages on the console of the program
##
DEBUG = True

##
## Our two LEDs, utilizing GPIO 18, and GPIO 23
##
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
    """
    red.off()
    blue.off()


def bothOn():
    """
    Turn both LEDs on.
    """
    debug_log('* Both LEDs on')
    reset_leds()
    red.on()
    blue.on()


def redFade():
    """
    Turn off the blue LED and fade the red LED.
    """
    debug_log('* Fading Red')
    reset_leds()
    red.pulse()


def blueFade():
    """
    Turn off the red LED and fade the blue LED.
    """
    debug_log('* Fading Blue')
    reset_leds()
    blue.pulse()


##
## Configure our green button to use GPIO 24 and to execute
## the bothOn method when pressed.
##
greenButton = Button(24)
greenButton.when_pressed = bothOn

##
## Configure our Red button to use GPIO 25 and to execute
## the redFade method when pressed.
##
redButton = Button(25)
redButton.when_pressed = redFade

##
## Configure our Blue button to use GPIO 12 and to execute
## the blueFade method when pressed.
##
blueButton = Button(12)
blueButton.when_pressed = blueFade

##
## Setup our loop control flag
##
repeat = True

##
## Dummy loop to run over time.
##
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