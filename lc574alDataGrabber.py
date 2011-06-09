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

  This program uses the Prologix GPIB-USB controller (prologix.biz) to communicate with the LeCroy LC574AL oscilloscope, collect the trace data from all of the input channels, and write it to a file. This program was written because of the unacceptably slow speed of data transfer via RS232. The scope of this program is very narrow: it is a drop-in replacement for manually collecting trace data from the scope over RS232 during the typical workflow of creating marks on a sample with the pulse generator. This program does no initialization of equipment and thus assumes trace data has been collected by the oscilloscope and is ready for transfer. This program would typically be run at the end of a spectroscopy scan, after the STM image data has been saved and after the STOP button has been pressed on the oscilloscope.

  Data is collected from all input channels, regardless of what (if anything) is plugged into them. The data is saved as a python pickle so that it is trivial to access it from a python program later on. No parsing is done on the data collected from the oscilloscope: the data is trnasferred from the oscilloscope as text strings, and this program does minimal structuring of the returned strings into a series of nested python dictionaries. At the root level of the dictionary are five fields, one with key "idn" that stores a string containing the *IDN? response of the oscilloscope, adn four with keys "C1" ... "C4" containing dictionaries of trace data for channels 1 through 4. The trace dictionaries contain three fields: "wavedesc", "trigtime", and "simple". Each contains a string taken from the oscilloscope that has been returned from the corresponding query. For example, the wavedesc key for the channel C1 contains the string read from the oscilloscope after writing the 'C1:INSP? "WAVEDESC"' query to the oscilloscope.

  This program automatically saves the data to a file in the present directory using the standard format: YYYYMMDD-HHMM_lc574al_intermediate_<sample name>_<experimenter initials>.dat
  
  This program is called from the command line and takes no arguments.
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
  
  # Get the WAVEDESC, TRIGTIME, and SIMPLE data from the oscilloscope and put it in the proper place in the dictionary.
  for indx in range(1,5):
    indx = str(indx)
    
    f = open("place.txt","w")
    f.write("channel:"+indx)
    f.close()
    
    print("Getting WAVEDESC for C" + indx)
    wavedescStr = ask("C" + indx + ':INSPECT? "WAVEDESC"', prologix)
    print("...done")

    print("Getting TRIGTIME for C" + indx)
    trigtimeStr = ask("C" + indx + ':INSPECT? "TRIGTIME"', prologix)
    print("...done")

    print("Getting SIMPLE for C" + indx)
    simpleStr = ask("C" + indx + ':INSPECT? "SIMPLE"', prologix)
    print("...done")
    
    intermediateDict["C" + indx] = {"wavedesc": wavedescStr, \
                                    "trigtime": trigtimeStr, \
                                    "simple": simpleStr}

  # Write the data to a file.
  now = datetime.datetime.now()
  filename = "_".join([now.strftime("%Y%m%d-%H%M"), "lc574al", "intermediate", \
    sampleName, experimenterInitials]) + ".dat"
    
  f = open(filename, "w")
  pickle.dump(intermediateDict, f)
  f.close()


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
	print(line)
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
    except:
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