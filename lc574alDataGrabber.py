# -*- coding: utf-8 -*-
#!/usr/bin/env python

import serial
import numpy
import pickle
import datetime
import re
import pyparsing
import pdb

def dataGrabber():
  """
  Write data from the LeCroy LC574AL oscilloscope over GPIB-USB to a file.

  This program uses the Prologix GPIB-USB controller (prologix.biz) to communicate with the LeCroy LC574AL oscilloscope, collect the trace data from all of the input channels, and write it to a file that can be used from a python script. This program was written because of the unacceptably slow speed of data transfer via RS232. The scope of this program is very narrow: it is a drop-in replacement for manually collecting trace data from the scope over RS232 during the typical workflow of creating marks on a sample with the pulse generator. This program would typically be run at the end of a spectroscopy scan, after the STM image data has been saved and after the STOP button has been pressed on the scope.

  Data is collected from all input channels, regardless of what (if anything) is plugged into them. The data is restructured and saved as a python pickle so that it is trivial to access it from a python program later on. Data from the oscilloscope is structured in a nested series of dictionaries and lists as follows: The root object is a python dictionary with two fields, "metadata" and "data". The "metadata" field contains a string that identifies the oscillosocpe. The "data" field contains a python list with entries corresponding to each segment the oscilloscope has recorded. Each entry in the "data" list is a dictionary with four fields: "C1", ..., "C4", and "time". All items in the dictionary are numpy arrays; the "time" array is the ordinate and the "C1", etc arrays are the abscissae. Times are recorded relative to the initial trigger event.

  For example, I sometimes do a spectroscopy scan using a regular 4x4 array of spectroscopy points. Therefore there are 16 total spectroscopy locations, the coordinates of which are recorded in the SM4 file that XPMPro records. Each of these 16 pulses are recorded by the oscilloscope, and this program will put the data for each of them into the 16 elements of the "data" list. If I had done a regular 8x8 array spectroscopy scan, this program would create a "data" list 64 elements long, and so on. Assuming there is zero temporal offset on the scope, the first element of the "time" array in the first item of the "data" list would be 0.0000... Assuming there was a 0.25s gap betweeen the first pulse and the second, the first element of the "time" array in the second item of the "data" list would be 0.25000000..., and so on.

  This program automatically saves the data to a file using the standard format: YYYYMMDD-HHMM_lc574al_<sample name>_<experimenter name>.dat
  """

  # Some parameters that define the GPIB network topology and how the filename is constructed.
  scopeGPIBAddr = 5
  sampleName = "jrs0076"
  experimenterInitials = "jrs"

  # Initialize the Prologix controller.
  prologix = serial.Serial("/dev/ttyUSB0", timeout=0)

  # Configure the prologix box to be a CONTROLLER, set it to talk to the scope, make sure the scope automatically responds after it has been addressed, and make the prologix box the controller-in-charge
  prologix.write("++mode 1\n")
  prologix.write("++addr" + str(scopeGPIBAddr) + "\n")
  prologix.write("++auto 1\n")
  prologix.write("++ifc\n")

  # Begin by pulling all of the pertinant data from the oscilloscope and putting it into an intermediate data structure.
  intermediateDict = {}
  
  # Grab identifying information about the scope and put it into the intermediate dict.
  idn = ask("*IDN?", prologix)
  intermediateDict["idn"] = idn

  # Get the WAVEDESC data for all of the channels and add it to the intermediate dict.
  intermediateDict["wavedesc"] = []
  for indx in range(1,5):
    wavedescStr = ask("C" + str(indx) + ':INSPECT? "WAVEDESC"', prologix)
    intermediateDict["wavedesc"].append(wavedescStr)

  # Get data from the channels on the scope and put it into the intermediate dict.
  intermediateDict["simple"] = []
  for indx in range(1,5):
    print "Channel " + str(indx) + " start."
    simpleStr = ask("C" + str(indx) + ':INSPECT? "SIMPLE"', prologix)
    print "..complete.\n"
    intermediateDict["simple"].append(simpleStr)

  # Get the trigger times and put it into the intermediate dict.
  intermediateDict["trigtime"] = ask('C1::INSPECT? "TRIGTIME"', prologix)
  
  
  # Now that all of the data has been copied from the oscilloscope, begin constructing the object that will be written to the disk.
  datObject = {"metadata": {},\
               "data": []}
  
  # First, the metadata.
  datObject["metadata"]["idn"] = intermediateDict["idn"]
  for indx, txt in enumerate(intermediateDict["wavedesc"]):
    datObject["metadata"]["C" + str(indx + 1)] = txt
    
  # To get the data part of the object, I will start by parsing the SIMPLE data that came from the oscilloscope.
  datObject["data"] = genTraceArrays(intermediateDict)
  
  # Finally I'll construct the temporal arrays and add them to the object that will be written to disk.
  temArrays = genTimeArrays(intermediateDict)
  for indx, array in timArrays:
    datObject["data"][indx]["time"] = array


  # Write the data to a file.
  now = datetime.datetime.now()
  filename = "_".join([now.strftime("%Y%m%d-%H%M"), "ls574al", sampleName, experimenterName]) + ".dat"


def ask(reqStr, serDev):
  """
  Write a request to a device and return the response as a string.
  
  This method abstracts the write and read process of getting data out of a device over the prologix controller. Instead of two or three commands, the user just passes a string (reqStr) and serial object (serDev) to the method. The reqStr is the exact string to be passed to the serial.write() method, and the serDev is the serial device to be used. This method deals with the timing of the communication so the user doesn't have to think about it.
  """
  
  # I may have gotten some extra carriage returns on the end of reqStr, remove them.
  reqStr = reqStr.strip()
  
  # I'm using the STB command to mark the end of the response from the oscilloscope.
  serDev.write(reqStr + ";*STB?\r\n")
  
  # Initialize the variables we need to read everything out of the device buffer.
  line = ""
  txt = ""
  
  while True:
    bufr = serDev.read()
    line += bufr
    if "\n" in bufr:
      # If line containts "*STB" then I'm at the end of the oscilloscope's response. Break the loop.
      if re.search("\*STB", line):
	txt += line.split(";*STB")[0]
	break
      else:
	# We aren't at the end of the data stream, but we're at the end of the line so reset it.
	txt += line
	line = ""
  
  serDev.flushInput()
  return txt


def genTimeArrays(intermediateDict):
  """
  Return list of arrays of temporal data for the trigger events.
  
  This method queries the oscilloscope and generates the temporal data for each trigger event. The indices of the returned list correspond to the index of the trigger event.
  """
  
  # Create a list out of the lines in the trigtime string.
  trigtimeList = intermediateDict["trigtime"].split("\r\n")
  
  # Set up some pyparsing objects to parse the values coming out of the trigtime list.
  digits = pyparsing.Word(pyparsing.nums)
  plusminus = pyparsing.oneOf("+ -")
  scinot = pyparsing.Combine(pyparsing.Optional(plusminus) + digits + pyparsing.Literal(".") + digits + pyparsing.oneOf("e E") + plusminus + digits)
  datLine = scinot + scinot
  
  # Initialize the list that will contain the inital values for the arrays containing the temporal data, then populate it by parsing the strings in the trigtime list.
  initialTimeValues = []
  
  for line in trigtimeList:
    try:
      offsetList = datLine.parseString(line)
      # I'm explicitly doing this sum because I know there are only two elements in the offsetList.
      initialTimeValues.append(float(offsetList[0]) + float(offsetList[1]))
    else:
      # It wasn't data. Ignore.
      pass
    
  # Find the timestep given by the line with "HORIZ_INTERVAL" in one of the channels' wavedesc.
  horizIntvlParser = pyparsing.Suppress("HORIZ_INTERVAL") + pyparsing.Suppress(":") + scinot
  horizIntvl = float(horizIntvlParser.searchString(intermediateDict["wavedesc"][0])[0][0])
  
  # Find the total number of points recorded for each trigger event by looking at WAVE_ARRAY_COUNT in on of the channels' wavedesc.
  waveArrayCountParser = pyparsing.Suppress("WAVE_ARRAY_COUNT") + pyparsing.Suppress(":") + scinot
  waveArrayCount = int(waveArrayCountParser.searchString(intermediateDict["wavedesc"][0])[0][0])
  ptsPerTrig = waveArrayCount / len(initialTimeValues)
  
  # Generate a list of numpy arrays containing the temporal data for each trigger.
  timeArrayList = []
  protoTimeArray = np.arange(0, (ptsPerTrig * horizIntvl), horizIntvl)
  for trigTime in trigTimeList:
    timeArrayList.append(protoTimeArray + trigTime)
    
  return timeArrayList


def genTraceArrays(intermediateDict):
  """
  Return list containing all the trace data according to trigger event.
  """
  
  # Set up some pyparsing objects to parse the simple strings.
  digits = pyparsing.Word(pyparsing.nums)
  plusminus = pyparsing.oneOf("+ -")
  scinot = pyparsing.Combine(pyparsing.Optional(plusminus) + digits + pyparsing.Literal(".") + digits + pyparsing.oneOf("e E") + plusminus + digits)
  scinot.setParseAction(lambda tokens: float(tokens[0]))
  
  block = pyparsing.Group(pyparsing.OneOrMore(scinot))
  segment = pyparsing.Suppress(pyparsing.Literal("Segment No") + digits)
  channel = pyparsing.Literal("C") + digits
  preamble = pyparsing.Suppress(channel + pyparsing.Literal(":INSP"))
  quote = pyparsing.Suppress(pyparsing.Literal("\""))
  simple = preamble + quote + pyparsing.OneOrMore(segment + block) + quote
  
  
  
  
  
  
  
  


def setOscilloscopeDate(serDev):
  """
  Sets the date on the oscilloscope according to the local machine time.
  """
  now = datetime.datetime.now()
  year = now.strftime("%Y")
  month = now.strftime("%b")
  day = now.strftime("%d")
  hour = now.strftime("%H")
  minute = now.strftime("%M")
  sec = now.strftime("%S")
  cmd = "DATE " + ",".join([day,month,year,hour,minute,sec])
  print cmd
  serDev.write(cmd + "\r\n")