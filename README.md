# Raspberry Pi Trilobot

This script assigns functions such as remote control, camera control and facial recognition to the Pimoroni Trilobot via its four buttons and can be automatically started at boot. The bot is controlled with an 8BitDo Lite gamepad. 

In parallel, the camera can be activated and streamed on a webclient using PiCamera and HTTPserver modules. Separately, Trilobot can also recognise faces using OpenCV and Flask and send email notifications if someone familiar is detected.

This code is based on the Pimoroni Trilobot library and a Tom's Hardware tutorial.

Further instructions at https://blog.piandpython.net/adding-facial-recognition-to-trilobot/.
