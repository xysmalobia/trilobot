#!/usr/bin/env python3

import time
import math
import signal
import activate_camera
import facial_recognition_with_flask
from threading import Thread, Event
from subprocess import call
from trilobot import Trilobot, NUM_UNDERLIGHTS, BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y
from trilobot.simple_controller import SimpleController

"""
This script assigns functions such as remote, camera control and facial recognition to 
the Trilobot buttons and can be automatically started at boot.
"""

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

tbot = Trilobot()


def create_8bitdo_lite_controller():
    """ Create a controller class for the 8BitDo Lite controller.
    """
    controller = SimpleController("8BitDo Lite gamepad")

    # Button and axis registrations for 8BitDo Lite
    controller.register_button("A", 305)
    controller.register_button("B", 304)
    controller.register_button("X", 307)
    controller.register_button("Y", 306)
    controller.register_button("Plus", 311, alt_name="Start")
    controller.register_button("Minus", 310, alt_name="Select")
    controller.register_button("L1", 308, alt_name="LB")
    controller.register_axis_as_button("L2", 2, 0, 1023, alt_name="LT")
    controller.register_button("R1", 309, alt_name="RB")
    controller.register_axis_as_button("R2", 5, 0, 1023, alt_name="RT")
    controller.register_button("Home", 139)
    controller.register_axis_as_button("L_Left", 0, 0, 32768)
    controller.register_axis_as_button("L_Right", 0, 65535, 32768)
    controller.register_axis_as_button("L_Up", 1, 0, 32768)
    controller.register_axis_as_button("L_Down", 1, 65535, 32768)
    controller.register_axis_as_button("R_Left", 3, 0, 32768)
    controller.register_axis_as_button("R_Right", 3, 65535, 32768)
    controller.register_axis_as_button("R_Up", 4, 0, 32768)
    controller.register_axis_as_button("R_Down", 4, 65535, 32768)
    controller.register_axis_as_button("Left", 16, -1, 0)
    controller.register_axis_as_button("Right", 16, 1, 0)
    controller.register_axis_as_button("Up", 17, -1, 0)
    controller.register_axis_as_button("Down", 17, 1, 0)

    controller.register_axis("LX", 0, 0, 65536)
    controller.register_axis("LY", 1, 0, 65536)
    controller.register_axis("RX", 3, 0, 65536)
    controller.register_axis("RY", 4, 0, 65536)

    return controller


def remote_active():
    """Connect the 8BitDo gamepad to Trilobot. Remote needs a paired bluetooth connection.
    """

    # Connect to 8BitDo Lite gamepad
    print("Connecting to 8BitDo Lite gamepad...")
    controller = create_8bitdo_lite_controller()

    # Attempt to connect to the created controller
    controller.connect()

    # Run an animation on the underlights to show a controller has been selected
    for led in range(NUM_UNDERLIGHTS):
        tbot.clear_underlighting(show=False)
        tbot.set_underlight(led, RED)
        time.sleep(0.1)
        tbot.clear_underlighting(show=False)
        tbot.set_underlight(led, GREEN)
        time.sleep(0.1)
        tbot.clear_underlighting(show=False)
        tbot.set_underlight(led, BLUE)
        time.sleep(0.1)

    tbot.clear_underlighting()

    h = 0
    v = 0
    spacing = 1.0 / NUM_UNDERLIGHTS

    tank_steer = False
    while True:
        if stop_event.is_set():
            break

        if not controller.is_connected():
            # Attempt to reconnect to the controller if 10 seconds have passed since the last attempt
            controller.reconnect(10, True)

        try:
            # Get the latest information from the controller. This will throw a RuntimeError if the
            # controller connection is lost
            controller.update()
        except RuntimeError:
            # Lost contact with the controller, so disable the motors to stop Trilobot if it was moving
            tbot.disable_motors()

        if controller.is_connected():

            # Read the controller bumpers to see if the tank steer mode has been enabled or disabled
            try:
                if controller.read_button("L1") and tank_steer:
                    tank_steer = False
                    print("Tank Steering Disabled")
                if controller.read_button("R1") and not tank_steer:
                    tank_steer = True
                    print("Tank Steering Enabled")
            except ValueError:
                # Cannot find 'L1' or 'R1' on this controller
                print("Tank Steering Not Available")

            try:
                if tank_steer:
                    # Have the left stick's Y axis control the left motor, and the right stick's Y axis
                    # control the right motor
                    ly = controller.read_axis("LY")
                    ry = controller.read_axis("RY")
                    tbot.set_left_speed(-ly)
                    tbot.set_right_speed(-ry)
                else:
                    # Have the left stick control both motors
                    lx = controller.read_axis("LX")
                    ly = 0 - controller.read_axis("LY")
                    tbot.set_left_speed(ly + lx)
                    tbot.set_right_speed(ly - lx)
            except ValueError:
                # Cannot find 'LX', 'LY', or 'RY' on this controller
                print("Motors disabled")
                tbot.disable_motors()

            # Run a rotating rainbow effect on the RGB underlights
            for led in range(NUM_UNDERLIGHTS):
                led_h = h + (led * spacing)
                if led_h >= 1.0:
                    led_h -= 1.0

                try:
                    if controller.read_button("A"):
                        tbot.set_underlight_hsv(led, 0.0, 0.0, 0.7, show=False)
                    else:
                        tbot.set_underlight_hsv(led, led_h, show=False)
                except ValueError:
                    # Cannot find 'A' on this controller
                    tbot.set_underlight_hsv(led, led_h, show=False)

            tbot.show_underlighting()

            # Advance the rotating rainbow effect
            h += 0.5 / 360
            if h >= 1.0:
                h -= 1.0

        else:
            # Run a slow red pulsing animation to show there is no controller connected
            val = (math.sin(v) / 2.0) + 0.5
            tbot.fill_underlighting(val * 127, 0, 0)
            v += math.pi / 200

        time.sleep(0.01)


def activate_button():
    """Buttons are hardwired to four specific functions: camera (A), remote (B),
    program exit (X) and facial recognition (Y). This thread keeps reading button
    states until program exit is activated.
    """

    last_state_a = False
    last_state_b = False
    last_state_x = False
    last_state_y = False

    while True:
        if stop_event.is_set():
            break

        # Read the buttons
        button_state_a = tbot.read_button(BUTTON_A)
        button_state_b = tbot.read_button(BUTTON_B)
        button_state_x = tbot.read_button(BUTTON_X)
        button_state_y = tbot.read_button(BUTTON_Y)

        if button_state_a != last_state_a:

            # Button A was pressed
            if button_state_a:
                print("[INFO] Camera is being activated.")

                # Turn the button's neighboring LED on or off
                tbot.set_button_led(BUTTON_A, 0.1)

                # Activate the camera in a separate thread
                t3 = Thread(target=activate_camera.main, daemon=True)

                # Ensure that this thread only starts if no other camera thread is active
                try:
                    if t5.is_alive():
                        print("Another camera thread running. Cannot operate in parallel.")
                        break
                    t3.start()

                except UnboundLocalError:
                    print("No interfering camera thread detected. Launching.")
                    t3.start()

            # Update our record of the button state
            last_state_a = button_state_a

        elif button_state_b != last_state_b:

            # Button B was pressed
            if button_state_b:
                print("[INFO] Remote control is being activated.")

                # Turn the button's neighboring LED on or off
                tbot.set_button_led(BUTTON_B, 0.1)

                # Turn on the remote control in a separate thread
                Thread(target=remote_active, daemon=None).start()

            # Update our record of the button state
            last_state_b = button_state_b

        elif button_state_x != last_state_x:

            # Button X was pressed, stopping all threads
            if button_state_x:
                print("[INFO] Program exit, stop event detected.")

                # Turn the button's neighboring LED on or off
                tbot.set_button_led(BUTTON_X, 0.5)

                # Switch off Trilobot altogether
                # power_down()

                # Stop event set, end all threads
                stop_event.set()

            # Update our record of the button state
            last_state_x = button_state_x

        elif button_state_y != last_state_y:

            # Button Y was pressed
            if button_state_y:
                print("[INFO] Facial recognition is being activated.")

                # Turn the button's neighboring LED on or off
                tbot.set_button_led(BUTTON_Y, 0.1)

                # Activate facial recognition in a separate thread
                t5 = Thread(target=facial_recognition_with_flask.main, daemon=True)

                # Ensure that this thread is only started if no other camera thread is active
                try:
                    if t3.is_alive():
                        print("Another camera thread running. Cannot operate in parallel.")
                        break
                    t5.start()

                except UnboundLocalError:
                    print("No interfering camera thread detected. Launching.")
                    t5.start()

            # Update our record of the button state
            last_state_y = button_state_y


def handle_interrupt(sig, frame):
    stop_event.set()


def power_down():
    """Switch off the lights, button LEDs and exit the programme.
    """
    tbot.clear_underlighting()
    tbot.set_button_led(BUTTON_A, 0)
    tbot.set_button_led(BUTTON_B, 0)
    tbot.set_button_led(BUTTON_X, 0)
    tbot.set_button_led(BUTTON_Y, 0)
    call("sudo shutdown -h now", shell=True)


if __name__ == "__main__":

    # Define a stop event that terminates all threads (SIGINT and Button X)
    stop_event = Event()
    signal.signal(signal.SIGINT, handle_interrupt)

    # Start the first thread to enable button activation
    print("[INFO] System ready. Press a button.")

    t1 = Thread(target=activate_button)
    t1.daemon = None
    t1.start()
    t1.join()

    tbot.clear_underlighting()
    tbot.set_button_led(BUTTON_A, 0)
    tbot.set_button_led(BUTTON_B, 0)
    tbot.set_button_led(BUTTON_X, 0)
    tbot.set_button_led(BUTTON_Y, 0)

    print("[INFO] All threads terminated. Shutdown complete.")
