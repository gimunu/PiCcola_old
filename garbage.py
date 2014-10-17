from rotary_class import RotaryEncoder
import re

LEFT_SWITCH = 14
RIGHT_SWITCH = 15
MUTE_SWITCH = 4
# Tuner rotary encoder
UP_SWITCH = 17
DOWN_SWITCH = 18
MENU_SWITCH = 25


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
    elif event == RotaryEncoder.ANTICLOCKWISE:
      switch = LEFT_SWITCH
      print "rotate anticlockwise"
  if event ==  RotaryEncoder.BUTTONDOWN:
    switch = MUTE_SWITCH
    print "push button"
  return  
  
global radio, volumeknob
  
volumeknob = RotaryEncoder(LEFT_SWITCH,RIGHT_SWITCH,MUTE_SWITCH,volume_event,getBoardRevision())
tunerknob = RotaryEncoder(UP_SWITCH,DOWN_SWITCH,MENU_SWITCH,tuner_event,getBoardRevision())
  