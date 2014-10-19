#!/usr/bin/python

# radio.py, version 2.1 (RGB LCD Pi Plate version)
# February 17, 2013
# Written by Sheldon Hartling for Usual Panic
# BSD license, all text above must be included in any redistribution
#

#
# based on code from Kyle Prier (http://wwww.youtube.com/meistervision)
# and AdaFruit Industries (https://www.adafruit.com)
# Kyle Prier - https://www.dropbox.com/s/w2y8xx7t6gkq8yz/radio.py
# AdaFruit   - https://github.com/adafruit/Adafruit-Raspberry-Pi-Python-Code.git, Adafruit_CharLCDPlate
#

#dependancies
from Adafruit_I2C          import Adafruit_I2C
from Adafruit_MCP230xx     import Adafruit_MCP230XX
from Adafruit_CharLCDPlate import Adafruit_CharLCDPlate
from datetime              import datetime
from subprocess            import *
from time                  import sleep, strftime
from Queue                 import Queue
from threading             import Thread

import smbus

import atexit, time


from mpd import MPDClient

client = MPDClient()

# Volume rotary encoder
LEFT_SWITCH = 14
RIGHT_SWITCH = 15
MUTE_SWITCH = 4
# Tuner rotary encoder
UP_SWITCH = 17
DOWN_SWITCH = 18
MENU_SWITCH = 25




# initialize the LCD plate
#   use busnum = 0 for raspi version 1 (256MB) 
#   and busnum = 1 for raspi version 2 (512MB)
LCD = Adafruit_CharLCDPlate(busnum = 1)

# Define a queue to communicate with worker thread
LCD_QUEUE = Queue()

# Globals
PLAYLIST_MSG   = []
STATION        = 1
NUM_STATIONS   = 0

# Buttons
NONE           = 0x00
SELECT         = 0x01
RIGHT          = 0x02
DOWN           = 0x04
UP             = 0x08
LEFT           = 0x10
UP_AND_DOWN    = 0x0C
LEFT_AND_RIGHT = 0x12

HOME = '/home/pi/PiCcola'

VOL_MIN      = -20
VOL_MAX      =  15
VOL_DEFAULT  =   0

volCur       = VOL_MIN   
volNew       = VOL_DEFAULT # 'Next' volume after interactions
volSpeed     = 1.0         # Speed of volume change (accelerates w/hold)
volSet       = False       # True if currently setting volume

# Char 7 gets reloaded for different modes.  These are the bitmaps:
charSevenBitmaps = [
  [0b10000, # Play (also selected station)
   0b11000,
   0b11100,
   0b11110,
   0b11100,
   0b11000,
   0b10000,
   0b00000],
  [0b11011, # Pause
   0b11011,
   0b11011,
   0b11011,
   0b11011,
   0b11011,
   0b11011,
   0b00000],
  [0b00000, # Next Track
   0b10100,
   0b11010,
   0b11101,
   0b11010,
   0b10100,
   0b00000,
   0b00000]]


#
# rotary encoders stuff
#

from rotary_class import RotaryEncoder
import re

global volumeknob, tunerknob

def getBoardRevision():
	revision = 1
	with open("/proc/cpuinfo") as f:
		cpuinfo = f.read()
	rev_hex = re.search(r"(?<=\nRevision)[ |:|\t]*(\w+)", cpuinfo).group(1)
	rev_int = int(rev_hex,16)
	if rev_int > 3:
		revision = 2
	boardrevision = revision
	return boardrevision


def tuner_event(event):
  print "tuner"
  global tunerknob
  switch = 0
  ButtonNotPressed = tunerknob.getSwitchState(MENU_SWITCH)
  # Suppress events if tuner button pressed
  if ButtonNotPressed:
    if event == RotaryEncoder.CLOCKWISE:
      switch = UP_SWITCH
      print "rotate clockwise"
    elif event == RotaryEncoder.ANTICLOCKWISE:
      switch = DOWN_SWITCH
      print "rotate anticlockwise"
  if event ==  RotaryEncoder.BUTTONDOWN:
    switch = MENU_SWITCH
    print "push button"
  return
  
def volume_event(event):
  print "volume"
  global volumeknob
  switch = 0
  ButtonNotPressed = volumeknob.getSwitchState(MUTE_SWITCH)
  # Suppress events if volume button pressed
  if ButtonNotPressed:
    if event == RotaryEncoder.CLOCKWISE:
      switch = RIGHT_SWITCH
      print "rotate clockwise"
      output = run_cmd("mpc volume +2")
    elif event == RotaryEncoder.ANTICLOCKWISE:
      switch = LEFT_SWITCH
      print "rotate anticlockwise"
      output = run_cmd("mpc volume +2")
  if event ==  RotaryEncoder.BUTTONDOWN:
    switch = MUTE_SWITCH
    print "push button"
  return  


volumeknob = RotaryEncoder(LEFT_SWITCH,RIGHT_SWITCH,MUTE_SWITCH,volume_event,getBoardRevision())
tunerknob = RotaryEncoder(UP_SWITCH,DOWN_SWITCH,MENU_SWITCH,tuner_event,getBoardRevision())

# ----------------------------
# WORKER THREAD
# ----------------------------

# Define a function to run in the worker thread
def update_lcd(q):
   
   while True:
      msg = q.get()
      # if we're falling behind, skip some LCD updates
      while not q.empty():
         q.task_done()
         msg = q.get()
      LCD.setCursor(0,0)
      LCD.message(msg)
      q.task_done()
   return


def cleanExit():
    if LCD is not None:
        time.sleep(0.5)
        LCD.backlight(LCD.OFF)
        LCD.clear()
        LCD.stop()
        run_cmd("mpc stop")



# ----------------------------
# MAIN LOOP
# ----------------------------

def main():
   global STATION, NUM_STATIONS, PLAYLIST_MSG

   atexit.register(cleanExit)

   # Stop music player
   output = run_cmd("mpc stop" )

   # Setup AdaFruit LCD Plate
   LCD.begin(16,2)
   LCD.clear()
   LCD.backlight(LCD.VIOLET)

   # Create the worker thread and make it a daemon
   worker = Thread(target=update_lcd, args=(LCD_QUEUE,))
   worker.setDaemon(True)
   worker.start()
   
   # Display startup banner
   LCD_QUEUE.put('    PiCcola\n  Radio', True)

   # Load our station playlist
   load_playlist()
   sleep(2)
   LCD.clear()


    # Create volume bargraph custom characters (chars 0-5):
   for i in range(6):
      bitmap = []
      bits   = (255 << (5 - i)) & 0x1f
      for j in range(8): bitmap.append(bits)
      LCD.createChar(i, bitmap)

   # Create up/down icon (char 6)
   LCD.createChar(6,
      [0b00100,
      0b01110,
      0b11111,
      0b00000,
      0b00000,
      0b11111,
      0b01110,
      0b00100])


# ----------------------------
# START THE MUSIC!
# ----------------------------

   # Start music player
   LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)
   run_cmd("mpc volume +2")
   mpc_play(STATION)
   countdown_to_play = 0
      
   # Main loop
   while True:
      press = read_buttons()

      # LEFT button pressed
      if(press == LEFT):
         STATION -= 1
         if(STATION < 1):
            STATION = NUM_STATIONS
         LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)
         # start play in 300msec unless another key pressed
         countdown_to_play = 3

      # RIGHT button pressed
      if(press == RIGHT):
         STATION += 1
         if(STATION > NUM_STATIONS):
            STATION = 1
         LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)
         # start play in 300msec unless another key pressed
         countdown_to_play = 3

      # # UP button pressed
      # if(press == UP):
      #    output = run_cmd("mpc volume +2")
      #    print "vol up ="+output
      #
      # # DOWN button pressed
      # if(press == DOWN):
      #    output = run_cmd("mpc volume -2")
      #    print "vol down ="+output

      if press == UP or press == DOWN:
          # Just entering volume-setting mode; init display
         LCD.setCursor(0, 1)
         volCurI = int((volCur - VOL_MIN) + 0.5)
         n = int(volCurI / 5)
         s = (chr(6) + ' Volume ' +
            chr(5) * n +       # Solid brick(s)
            chr(volCurI % 5) + # Fractional brick 
            chr(0) * (6 - n))  # Spaces
         LCD.message(s)
         volSet   = True
         volSpeed = 1.0
         # Volume-setting mode now active (or was already there);
         # act on button press.
         if press == UP:
            print "press UP"
            volNew = volCur + volSpeed
            if volNew > VOL_MAX: volNew = VOL_MAX
         else:
            print "press Down"
            volNew = volCur - volSpeed
            if volNew < VOL_MIN: volNew = VOL_MIN
         volTime   = time.time() # Time of last volume button press
         volSpeed *= 1.15        # Accelerate volume change
         print "volume = %s"% volCur
         
         
      
      # SELECT button pressed
      if(press == SELECT):
         menu_pressed()

      # If we haven't had a key press in 300 msec
      # go ahead and issue the MPC command
      if(countdown_to_play > 0):
         countdown_to_play -= 1
         if(countdown_to_play == 0):
            # Play requested station
            mpc_play(STATION)

      delay_milliseconds(99)
   update_lcd.join()


# ----------------------------
# READ SWITCHES
# ----------------------------

def read_buttons():

   buttons = LCD.buttons()
   # Debounce push buttons
   if(buttons != 0):
      while(LCD.buttons() != 0):
         delay_milliseconds(1)
   return buttons



def delay_milliseconds(milliseconds):
   seconds = milliseconds / float(1000)	# divide milliseconds by 1000 for seconds
   sleep(seconds)



# ----------------------------
# LOAD PLAYLIST OF STATIONS
# ----------------------------

def load_playlist():
   global STATION, NUM_STATIONS, PLAYLIST_MSG
   print "playlist shellscript"
   # Run shell script to add all stations
   # to the MPC/MPD music player playlist
   output = run_cmd("mpc clear")
   output = run_cmd(HOME + "/radio_playlist.sh")
   print "Done"

   # Load PLAYLIST_MSG list
   PLAYLIST_MSG = []
   with open (HOME + "/radio_playlist.sh", "r") as playlist:
      # Skip leading hash-bang line
      for line in playlist:
         if line[0:1] != '#!':  
               break
      # Remaining comment lines are loaded
      for line in playlist:
         if line[0] == "#" :
            PLAYLIST_MSG.append(line.replace(r'\n','\n')[1:-1] + "                ")
   playlist.close()
   NUM_STATIONS = len(PLAYLIST_MSG)


# ----------------------------
# RADIO SETUP MENU
# ----------------------------

def menu_pressed():
   global STATION

   MENU_LIST = [
      '1. Display Time \n   & IP Address ',
      '2. Output Audio \n   to HDMI      ',
      '3. Output Audio \n   to Headphones',
      '4. Auto Select  \n   Audio Output ',
      '5. Reload       \n   Playlist File',
      '6. System       \n   Shutdown!    ',
      '7. Exit         \n                ']

   item = 0
   LCD.clear()
   LCD.backlight(LCD.YELLOW)
   LCD_QUEUE.put(MENU_LIST[item], True)

   keep_looping = True
   while (keep_looping):

      # Wait for a key press
      press = read_buttons()

      # UP button
      if(press == UP):
         item -= 1
         if(item < 0):
            item = len(MENU_LIST) - 1
         LCD_QUEUE.put(MENU_LIST[item], True)

      # DOWN button
      elif(press == DOWN):
         item += 1
         if(item >= len(MENU_LIST)):
            item = 0
         LCD_QUEUE.put(MENU_LIST[item], True)

      # SELECT button = exit
      elif(press == SELECT):
         keep_looping = False

         # Take action
         if(  item == 0):
            # 1. display time and IP address
            display_ipaddr()
         elif(item == 1):
            # 2. audio output to HDMI
            output = run_cmd("amixer -q cset numid=3 2")
         elif(item == 2):
            # 3. audio output to headphone jack
            output = run_cmd("amixer -q cset numid=3 1")
         elif(item == 3):
            # 4. audio output auto-select
            output = run_cmd("amixer -q cset numid=3 0")
         elif(item == 4):
            # 5. reload our station playlist
            LCD_QUEUE.put("Reloading\nPlaylist File...", True)
            load_playlist()
            sleep(2)
            STATION = 1
            LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)
            mpc_play(STATION)
         elif(item == 5):
            # 6. shutdown the system
            LCD_QUEUE.put('Shutting down\nLinux now! ...  ', True)
            LCD_QUEUE.join()
            output = run_cmd("mpc clear")
            output = run_cmd("sudo shutdown now")
            LCD.clear()
            LCD.backlight(LCD.OFF)
            exit(0)
      else:
         delay_milliseconds(99)

   # Restore display
   LCD.backlight(LCD.VIOLET)
   LCD_QUEUE.put(PLAYLIST_MSG[STATION - 1], True)



# ----------------------------
# DISPLAY TIME AND IP ADDRESS
# ----------------------------

def display_ipaddr():
   show_wlan0 = "ip addr show wlan0 | cut -d/ -f1 | awk '/inet/ {printf \"w%15.15s\", $2}'"
   show_eth0  = "ip addr show eth0  | cut -d/ -f1 | awk '/inet/ {printf \"e%15.15s\", $2}'"
   ipaddr = run_cmd(show_eth0)
   if ipaddr == "":
      ipaddr = run_cmd(show_wlan0)

   LCD.backlight(LCD.VIOLET)
   i = 29
   muting = False
   keep_looping = True
   while (keep_looping):

      # Every 1/2 second, update the time display
      i += 1
      #if(i % 10 == 0):
      if(i % 5 == 0):
         LCD_QUEUE.put(datetime.now().strftime('%b %d  %H:%M:%S\n')+ ipaddr, True)

      # Every 3 seconds, update ethernet or wi-fi IP address
      if(i == 60):
         ipaddr = run_cmd(show_eth0)
         i = 0
      elif(i == 30):
         ipaddr = run_cmd(show_wlan0)

      # Every 100 milliseconds, read the switches
      press = read_buttons()
      # Take action on switch press
      
      # UP button pressed
      if(press == UP):
         output = run_cmd("mpc volume +2")

      # DOWN button pressed
      if(press == DOWN):
         output = run_cmd("mpc volume -2")

      # SELECT button = exit
      if(press == SELECT):
         keep_looping = False

      # LEFT or RIGHT toggles mute
      elif(press == LEFT or press == RIGHT ):
         if muting:
            #amixer command not working, can't use next line
            #output = run_cmd("amixer -q cset numid=2 1")
            mpc_play(STATION)
            # work around a problem.  Play always starts at full volume
            delay_milliseconds(400)
            output = run_cmd("mpc volume +2")
            output = run_cmd("mpc volume -2")
         else:
            #amixer command not working, can't use next line
            #output = run_cmd("amixer -q cset numid=2 0")
            output = run_cmd("mpc stop" )
         muting = not muting
         
      delay_milliseconds(99)



# ----------------------------

def run_cmd(cmd):
   p = Popen(cmd, shell=True, stdout=PIPE, stderr=STDOUT)
   output = p.communicate()[0]
   return output



#def run_cmd_nowait(cmd):
#   pid = Popen(cmd, shell=True, stdout=NONE, stderr=STDOUT).pid



def mpc_play(STATION):
   pid = Popen(["/usr/bin/mpc", "play", '%d' % ( STATION )]).pid



if __name__ == '__main__':
  main()
