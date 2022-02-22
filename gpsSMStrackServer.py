import logging
import logging.handlers
import sys
import os
import signal
import time
import thread
import serial
import json

# REST API library
from flask import Flask
from flask import jsonify
from flask import request

# Retrieve SMS server settings
from settings import serialport
from settings import baudrate
from settings import pollinterval
from settings import polltimeout

# Global declaration
backLogger         = False    # Macro for logger
serialPort         = ''       # Serial communication port name
baudRate           = 0        # Serial communication baud rate
pollInterval       = 0        # GPS location poll interval
pollTimeOut        = 0        
gsmInitialize      = False    # GSM modem initialization flag
atCheck            = False    # AT command reply check flag
atDeleteMsg        = False    # Delete SMS command reply check flag
atSetTxtMsg        = False    # Set text message SMS command reply check flag
atCnmi             = False
atCpms             = False
initModem          = False
waitSendMsg        = False
enaGPSPoll         = False
secureInSecure     = False
cellPhoneNo        = ''
cellPhoneList      = []       # GPS vehicle tracker cell phone list
cellPhoneCnt       = 0        # Cell phone no. record count
cellNoIndx         = 0        # Cell phone no. index counter

# Copy serial communication setting to the global variable
serialPort = serialport
baudRate = baudrate
pollInterval = pollinterval
pollTimeOut = polltimeout

# Check for macro arguments
if (len(sys.argv) > 1):
    for x in sys.argv:
        # Optional macro if we want to enable text file log
        if(x == "LOGGER"):
            backLogger = True
        # Optional macro if we want to enable https
        elif x == "SECURE":
            secureInSecure = True
        elif x == "ENABLEPOLL":
            enaGPSPoll = True      
        
# GPS tracker list data
gpsTrackerListData=[
    {
        'gpsid' : '+60133517176',
        'latitude' : 'NA',
        'longitude' : 'NA',
        'course' : 'NA',
        'speed' : 'NA',
        'status' : 'NA',
        'datetime' : 'NA'
    }
]

# Poll request either ENABLE or DISABLE
pollConfigData=[
    {
        'id' : '000',
        'poll' : 'DISABLE'
    }
]

# Retrieve GPS vehicle tracker cell phone from stored list
try:
    firstDat = False

    # Open GPS vehicle tracker list of data
    file = open("/sources/common/sourcecode/GSM-Gateway/gpstracker.list", "r")

    # Go through the GPS vehicle tracker cell phone list
    for i in range(100):
        tempdata = ''
        tempdata = file.readline()
        tempdata = tempdata.strip('\n') # Get rid of new line character

        # Initial state the cell phone array are emptied, add first data
        if cellPhoneList == '':
            # Data exist inside stored list
            if tempdata != '':
                cellPhoneList = [tempdata]
                #tempdata = ''
                # Increment record count
                cellPhoneCnt += 1
            # NO data remain inside stored list
            else:
                break

        # Subsequent array index, append the data to the array
        else:
            # Data exist inside stored list
            if tempdata != '':
                cellPhoneList.append(tempdata)
                #tempdata = ''
                # Increment record count
                cellPhoneCnt += 1
            # NO data remain inside stored list
            else:
                break
            
        # First data update
        if firstDat == False:
            extDB = [ extDBB for extDBB in gpsTrackerListData ]
            extDB[0]['gpsid'] = tempdata
            extDB[0]['latitude'] = 'NA'
            extDB[0]['longitude'] = 'NA'
            extDB[0]['course'] = 'NA'
            extDB[0]['speed'] = 'NA'
            extDB[0]['status'] = 'NA'
            extDB[0]['datetime'] = 'NA'
            
            firstDat = True
        # New data update
        else:
            # Construct the new data
            newData = {
                        'gpsid' : tempdata,
                        'latitude' : 'NA',
                        'longitude' : 'NA',
                        'course' : 'NA',
                        'speed' : 'NA',
                        'status' : 'NA',
                        'datetime' : 'NA'
                        }
            
            # Append a NEW extension to the existing record
            gpsTrackerListData.append(newData)

    # Close the file
    file.close()

# Error
except:
    # Write to logger
    if backLogger == True:
        logger.info("DEBUG_GPS_LST: Open gpstracker.list file failed!")
    # Print statement
    else:
        print "DEBUG_GPS_LST: Open gpstracker.list file failed!"    

# For debugging
#print cellPhoneList
#print cellPhoneCnt
#print gpsTrackerListData
#sys.exit()

# Initialize REST API Flask server 
app = Flask(__name__)
            
# Setup log file 
if backLogger == True:
    path = os.path.dirname(os.path.abspath(__file__))
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logfile = logging.handlers.TimedRotatingFileHandler('/tmp/smsgpsgw.log', when="midnight", backupCount=3)
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
    logfile.setFormatter(formatter)
    logger.addHandler(logfile)

# Doing string manipulations
def mid(s, offset, amount):
    return s[offset-1:offset+amount-1]

# Handle Cross-Origin (CORS) problem upon client request
@app.after_request
def add_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')

    return response

# Get current GPS location status
# Example command to send:
# https://voip.scs.my:9000/ricinfo
@app.route('/gpsinfo', methods=['GET'])
def getRicInfoDb():
    return jsonify({'GPSInfo' : gpsTrackerListData})

# Get current GPS location status
# Example command to send:
# https://voip.scs.my:9000/smsgwinfo
@app.route('/smsgwinfo', methods=['GET'])
def getSmsGwInfoDb():
    return jsonify({'SMSGWInfo' : pollConfigData})

# Activate GPS location poll request - Will enable send SMS process
# Example command to send:
# curl -i -k -H "Content-type: application/json" -X PUT -d "{\"poll\":\"ENABLE\"}" https://voip.scs.my:9000/pollgps/000
@app.route('/pollgps/<cnfgid>', methods=['PUT'])
def updatePollConfig(cnfgid):
    global enaGPSPoll

    iCnfg = [ iCnfgG for iCnfgG in pollConfigData if (iCnfgG['id'] == cnfgid) ]
    # Update polling config - ENABLE/DISABLE
    if 'poll' in request.json:
        tempPollEn = request.json['poll']
        # Update config data
        iCnfg[0]['poll'] = request.json['poll']
        # Enable GPS poll request 
        if tempPollEn == 'ENABLE':
            enaGPSPoll = True
        # Disable GPS poll request
        else:
            enaGPSPoll = False

    return jsonify({'pollconfig': iCnfg})

# Reset GPS info python dictionary data
def reset_gpsinfo():
    global gpsTrackerListData
    global cellPhoneList
    global cellPhoneCnt

    # Reinitialize back GPS information list python dictionary data
    gpsTrackerListData=[
        {
            'gpsid' : '+60133517176',
            'latitude' : 'NA',
            'longitude' : 'NA',
            'course' : 'NA',
            'speed' : 'NA',
            'status' : 'NA',
            'datetime' : 'NA'
        }
    ]
    
    try:
        firstDat = False

        # Open GPS vehicle tracker list of data
        file = open("/sources/common/sourcecode/GSM-Gateway/gpstracker.list", "r")

        # Go through the GPS vehicle tracker cell phone list
        for i in range(100):
            tempdata = ''
            tempdata = file.readline()
            tempdata = tempdata.strip('\n') # Get rid of new line character

            # Initial state the cell phone array are emptied, add first data
            if cellPhoneList == '':
                # Data exist inside stored list
                if tempdata != '':
                    cellPhoneList = [tempdata]
                    #tempdata = ''
                    # Increment record count
                    cellPhoneCnt += 1
                # NO data remain inside stored list
                else:
                    break

            # Subsequent array index, append the data to the array
            else:
                # Data exist inside stored list
                if tempdata != '':
                    cellPhoneList.append(tempdata)
                    #tempdata = ''
                    # Increment record count
                    cellPhoneCnt += 1
                # NO data remain inside stored list
                else:
                    break
                
            # First data update
            if firstDat == False:
                extDB = [ extDBB for extDBB in gpsTrackerListData ]
                extDB[0]['gpsid'] = tempdata
                extDB[0]['latitude'] = 'NA'
                extDB[0]['longitude'] = 'NA'
                extDB[0]['course'] = 'NA'
                extDB[0]['speed'] = 'NA'
                extDB[0]['status'] = 'NA'
                extDB[0]['datetime'] = 'NA'
                
                firstDat = True
            # New data update
            else:
                # Construct the new data
                newData = {
                            'gpsid' : tempdata,
                            'latitude' : 'NA',
                            'longitude' : 'NA',
                            'course' : 'NA',
                            'speed' : 'NA',
                            'status' : 'NA',
                            'datetime' : 'NA'
                            }
                
                # Append a NEW extension to the existing record
                gpsTrackerListData.append(newData)

        # Close the file
        file.close()

    # Error
    except:
        # Write to logger
        if backLogger == True:
            logger.info("DEBUG_GPS_LST: Open gpstracker.list file failed!")
        # Print statement
        else:
            print "DEBUG_GPS_LST: Open gpstracker.list file failed!"    

        
    
# Thread for GSM modem initialization and poll request for GPS location
def serial_sms_comm (threadname, delay):
    global serialPort
    global baudRate
    global gsmInitialize
    global backLogger
    global atCheck
    global atDeleteMsg
    global atSetTxtMsg
    global cellPhoneNo
    global waitSendMsg
    global cellPhoneList
    global cellPhoneCnt
    global cellNoIndx
    global atCnmi
    global pollTimeOut
    global enGPSPoll
    global atCpms
    global enaGPSPoll
    global gpsTrackerListData

    gsmReply = ''
    sendCmdMsg = ''

    hexMsgPrtOne = ''
    hexMsgPrtTwo = ''
    decodedGPSMsg = ''
    cellPhoneNo = ''
    timeOutCnt = 0
    cmtiCnt = 0
    gpsComplete = False
    cmtiFound = False
    validCellNo = False
    msgPartOneCorr = False
    msgPartTwoCorr = False
    pollDisDelSms = False
    gpsLocTimeOut = pollTimeOut

    # Initialize serial communication port for GSM modem
    #serialGSM = serial.Serial(serialPort, baudrate = baudRate, timeout = 5)
    serialGSM = serial.Serial(serialPort, baudrate = baudRate)
    serialGSM.flushInput()
    serialGSM.flushOutput()
    
    # Serial communication loop
    while True:
        # Start initialize GSM modem
        if gsmInitialize == False:
            # Send AT command to GSM modem
            #if atCheck == False:
            serialGSM.write(b'AT\r')
            # Delay for send command before process the reply 
            time.sleep(1)
            # Start check the reply from GSM modem
            gsmReply = serialGSM.read(serialGSM.inWaiting())
            # Previous command send OK 
            if 'OK' in gsmReply:
                # Write to logger
                if backLogger == True:
                    logger.info("####################################################################")
                    logger.info("DEBUG_GSM: Wake UP GSM modem successful, Reply Data: %s" % (gsmReply))
                    logger.info("####################################################################")
                # Print statement
                else:
                    print "####################################################################"
                    print "DEBUG_GSM: Wake UP GSM modem successful, Reply Data: %s" % (gsmReply)
                    print "####################################################################"

                atCheck = True

            # Previously there is a stuck '>' character during sending SMS message
            # Complete the sends message by sending to default cell no.
            elif '>' in gsmReply:
                sendCmdMsg = 'ERROR'
                serialGSM.write(sendCmdMsg + chr(26))
                # Delay for send command before process the reply 
                time.sleep(1)
                
                # Start check the reply from GSM modem
                gsmReply = serialGSM.read(serialGSM.inWaiting())
                # Previous command send OK 
                if 'OK' in gsmReply:
                    serialGSM.write(b'AT\r')
                    # Delay for send command before process the reply 
                    time.sleep(1)
                    # Start check the reply from GSM modem
                    gsmReply = serialGSM.read(serialGSM.inWaiting())
                    # Previous command send OK 
                    if 'OK' in gsmReply:
                        # Write to logger
                        if backLogger == True:
                            logger.info("DEBUG_GSM: Wake UP GSM modem successful, Reply Data: %s" % (gsmReply))
                            logger.info("####################################################################")
                        # Print statement
                        else:
                            print "DEBUG_GSM: Wake UP GSM modem successful, Reply Data: %s" % (gsmReply)
                            print "####################################################################"
            
            # Setting for receiving SMS message behaviour, will receive +CMTI message indicator
            # AT+CNMI=2,2,0,0,0 - will received +CMT without need to read SMS message index
            serialGSM.write(b'AT+CNMI=1,1,0,0,0\r')
            # Delay for send command before process the reply 
            time.sleep(1)
            # Start check the reply from GSM modem
            gsmReply = serialGSM.read(serialGSM.inWaiting())
            # Previous command send OK 
            if 'OK' in gsmReply:
                # Write to logger
                if backLogger == True:
                    logger.info("DEBUG_GSM: SMS receiving setting for GSM modem successful, Reply Data: %s" % (gsmReply))
                    logger.info("####################################################################")
                # Print statement
                else:
                    print "DEBUG_GSM: SMS receiving setting for GSM modem successful, Reply Data: %s" % (gsmReply)
                    print "####################################################################"

            serialGSM.write(b'AT+CPMS="SM","SM","SM"\r')
            # Delay for send command before process the reply 
            time.sleep(1)
            # Start check the reply from GSM modem
            gsmReply = serialGSM.read(serialGSM.inWaiting())
            # Previous command send OK 
            if 'OK' in gsmReply:
                # Write to logger
                if backLogger == True:
                    logger.info("DEBUG_GSM: SMS memory setting for GSM modem successful, Reply Data: %s" % (gsmReply))
                    logger.info("####################################################################")
                # Print statement
                else:
                    print "DEBUG_GSM: SMS memory setting for GSM modem successful, Reply Data: %s" % (gsmReply)
                    print "####################################################################"

            serialGSM.write(b'AT+CSAS\r')
            # Delay for send command before process the reply 
            time.sleep(1)
            # Start check the reply from GSM modem
            gsmReply = serialGSM.read(serialGSM.inWaiting())
            # Previous command send OK 
            if 'OK' in gsmReply:
                # Write to logger
                if backLogger == True:
                    logger.info("DEBUG_GSM: Stored setting for GSM modem successful, Reply Data: %s" % (gsmReply))
                    logger.info("####################################################################")
                # Print statement
                else:
                    print "DEBUG_GSM: Stored setting for GSM modem successful, Reply Data: %s" % (gsmReply)
                    print "####################################################################"
                           
            # Send delete SMS message command at index 1 to 4
            serialGSM.write(b'AT+CMGDA="DEL ALL"\r')
            # Delay for send command before process the reply 
            time.sleep(1)
            # Start check the reply from GSM modem
            gsmReply = serialGSM.read(serialGSM.inWaiting())
            # Previous command send OK 
            if 'OK' in gsmReply or '>' in gsmReply:
                # Write to logger
                if backLogger == True:
                    logger.info("DEBUG_GSM: Delete ALL SMS message successful, Reply Data: %s" % (gsmReply))
                    logger.info("####################################################################")
                # Print statement
                else:
                    print "DEBUG_GSM: Delete ALL SMS message successful, Reply Data: %s" % (gsmReply)
                    print "####################################################################"
            
            serialGSM.write(b'AT+CPMS="SM","SM","SM"\r')
            # Delay for send command before process the reply 
            time.sleep(1)
            # Start check the reply from GSM modem
            gsmReply = serialGSM.read(serialGSM.inWaiting())
            # Previous command send OK 
            if 'OK' in gsmReply:
                # Write to logger
                if backLogger == True:
                    logger.info("DEBUG_GSM: Recheck SMS memory setting for GSM modem successful, Reply Data: %s" % (gsmReply))
                    logger.info("####################################################################")
                # Print statement
                else:
                    print "DEBUG_GSM: Recheck SMS memory setting for GSM modem successful, Reply Data: %s" % (gsmReply)
                    print "####################################################################"
                    
            # Send set SMS text message command
            elif atDeleteMsg == True and  atSetTxtMsg == False:
                serialGSM.write(b'AT+CMGF=1\r')
                # Delay for send command before process the reply 
                time.sleep(1)
                # Start check the reply from GSM modem
                gsmReply = serialGSM.read(serialGSM.inWaiting())
                # Previous command send OK 
                if 'OK' in gsmReply or '>' in gsmReply:
                    # Write to logger
                    if backLogger == True:
                        logger.info("DEBUG_GSM: Set GSM modem to text mode successful, Reply Data: %s" % (gsmReply))
                        logger.info("####################################################################")
                    # Print statement
                    else:
                        print "DEBUG_GSM: Set GSM modem to text mode successful, Reply Data: %s" % (gsmReply)
                        print "####################################################################"
                    atSetTxtMsg = True

            # Write to logger
            if backLogger == True:
                logger.info("DEBUG_GSM: GSM modem initialization completed")
                logger.info("####################################################################")
            # Print statement
            else:
                print "DEBUG_GSM: GSM modem initialization completed"
                print "####################################################################"
                    
            gsmInitialize = True
        
        # Previously GSM modem initialization completed
        else:
            # Listen for received SMS message
            # Start check the reply from GSM modem
            gsmReply = serialGSM.read(serialGSM.inWaiting())
            # Received data from GSM modem
            if gsmReply != '' or cmtiFound == True:
                cmtiFound = False
                if '+CMTI' in gsmReply and gpsComplete == False:
                    # Write to logger
                    if backLogger == True:
                        logger.info("DEBUG_GSM: Received NEW SMS, Reply AT command: %s" % (gsmReply))
                        logger.info("####################################################################")
                    # Print statement
                    else:
                        print "DEBUG_GSM: Received NEW SMS, Reply AT command: %s" % (gsmReply)
                        print "####################################################################"

                    # Counting for the new incoming SMS message 
                    result = gsmReply.split()
                    cmtiCount = result.count("+CMTI:")

                    # Execute the logic to verify the counting
                    # Consider 2 concurrent SMS message that will indicate truncated GPS location message
                    if cmtiCount == 2 or cmtiCount > 2:
                        cmtiCnt = 2
                    elif cmtiCount == 1:
                        cmtiCnt += 1

                # Received complete GPS location
                if cmtiCnt == 2:
                    cmtiCnt = 0
                    gpsComplete = True
                    
                    # Read SMS message at memory location 1 - Hex message part 01
                    serialGSM.write(b'AT+CMGR=1\r')
                    # Delay for send command before process the reply 
                    time.sleep(1)
                    # Start check the reply from GSM modem
                    gsmReply = serialGSM.read(serialGSM.inWaiting())
                    # Previous command send OK 
                    if 'OK' in gsmReply and 'REC UNREAD' in gsmReply:
                        # Write to logger
                        if backLogger == True:
                            logger.info("DEBUG_GSM: Received GPS location message part 01, Reply AT command: %s" % (gsmReply))
                            logger.info("####################################################################")
                        # Print statement
                        else:
                            print "DEBUG_GSM: Received GPS location message part 01, Reply AT command: %s" % (gsmReply)
                            print "####################################################################"

                        # Start extract current GPS data
                        newLine = False
                        cellPhone = False
                        getHexMsg = False
                        plusCnt = 0
                        uCounter = 0
                        hexVal = ''
                        
                        gsmReplyLen = len(gsmReply)
                        # Get the sender identification and hex message part 01
                        for a in range(0, (gsmReplyLen + 1)):
                            oneChar = mid(gsmReply, a, 1)
                            # Search for indicator to start extract the cell phone no
                            if oneChar == '+' and cellPhone == False:
                                plusCnt += 1
                                if plusCnt == 3:
                                    plusCnt = 0
                                    cellPhone = True
                                    
                            # Start retrieve cell phone number
                            elif cellPhone == True and newLine == False:
                                # End of the search, find new line 
                                if oneChar == '"':
                                    cellPhoneNo = '+' + cellPhoneNo

                                    # Check the cell phone from the record, whether its exist or not
                                     # Update python data dictionary with GPS location
                                    try:
                                        # Check the cell number whether its already exist or not
                                        # Update the existing data, throw error if record is not exist
                                        extDB = [ extDBB for extDBB in gpsTrackerListData if (extDBB['gpsid'] == cellPhoneNo) ]
                                                                                
                                        # Write to logger
                                        if backLogger == True:
                                            logger.info("DEBUG_GSM: Valid cell phone number: %s" % (cellPhoneNo))
                                            logger.info("####################################################################")
                                        # Print statement
                                        else:
                                            print "DEBUG_GSM: Valid cell phone number: %s" % (cellPhoneNo)
                                            print "####################################################################"

                                        validCellNo = True
                                        newLine = True
                                    
                                    # Cell number NOT exists!, exit loop
                                    except:
                                        # Write to logger
                                        if backLogger == True:
                                            logger.info("DEBUG_GSM: Cell phone number NOT exist!: %s" % (cellPhoneNo))
                                            logger.info("####################################################################")
                                        # Print statement
                                        else:
                                            print "DEBUG_GSM: Cell phone number NOT exist: %s" % (cellPhoneNo)
                                            print "####################################################################"

                                        validCellNo = False
                                        break

                                # Append and construct cell phone no.                                    
                                else:
                                    cellPhoneNo += oneChar

                            # Start check for the new line char, indicate SMS contents with GPS location
                            elif newLine == True and getHexMsg == False: 
                                if oneChar == '\n':
                                    getHexMsg = True

                            # Get the contents of hex message
                            elif getHexMsg == True:
                                if oneChar == '\n':
                                    # Try to decode, only process the ASCII hex data
                                    try:
                                        # Remove any unwanted character before decode
                                        hexMsgPrtOne = hexMsgPrtOne.strip().decode("hex")
                                        msgPartOneCorr = True
                                    # None ASCII hex data, exit loop
                                    except:
                                        msgPartOneCorr = False
                                        break
                                        
                                    # Write to logger
                                    if backLogger == True:
                                        logger.info("DEBUG_GSM: Received GPS location message part 01 DECODED: %s" % (hexMsgPrtOne))
                                        logger.info("####################################################################")
                                    # Print statement
                                    else:
                                        print "DEBUG_GSM: Received GPS location message part 01 DECODED: %s" % (hexMsgPrtOne)
                                        print "####################################################################"
                                    break
                                else:
                                    uCounter += 1
                                    if uCounter == 2:
                                        hexVal += oneChar
                                        if hexVal != '00':
                                            hexMsgPrtOne += hexVal
                                        hexVal = ''
                                        uCounter = 0
                                    else:
                                        hexVal += oneChar    

                        # Previously the cell phone no. are valid and message format correct
                        if validCellNo == True and msgPartOneCorr == True:
                            # Read SMS message at memory location 1 - Hex message part 01
                            serialGSM.write(b'AT+CMGR=2\r')
                            # Delay for send command before process the reply 
                            time.sleep(1)
                            # Start check the reply from GSM modem
                            gsmReply = serialGSM.read(serialGSM.inWaiting())
                            # Previous command send OK 
                            if 'OK' in gsmReply and 'REC UNREAD' in gsmReply:
                                # Write to logger
                                if backLogger == True:
                                    logger.info("DEBUG_GSM_RX: Received GPS location message part 02, Reply AT command: %s" % (gsmReply))
                                    logger.info("####################################################################")
                                # Print statement
                                else:
                                    print "DEBUG_GSM_RX: Received GPS location message part 02, Reply AT command: %s" % (gsmReply)
                                    print "####################################################################"

                                # Start extract current GPS data
                                getHexMsg = False
                                newLineCnt = 0
                                uCounter = 0
                                hexVal = ''
                                gsmReplyLen = len(gsmReply)

                                # Get hex message part 02
                                for a in range(0, (gsmReplyLen + 1)):
                                    oneChar = mid(gsmReply, a, 1)
                                    if oneChar == '\n' and getHexMsg == False:
                                        newLineCnt += 1
                                        if newLineCnt == 2:
                                            getHexMsg = True

                                    elif getHexMsg == True:
                                        if oneChar == '\n':
                                            # Try to decode, only process the ASCII hex data
                                            try:
                                                # Remove any unwanted character before decode
                                                hexMsgPrtTwo = hexMsgPrtTwo.strip().decode("hex")
                                                msgPartTwoCorr = True
                                            # None ASCII hex data, exit loop
                                            except:
                                                msgPartTwoCorr = False
                                                break
                                            
                                            # Write to logger
                                            if backLogger == True:
                                                logger.info("DEBUG_GSM: Received GPS location message part 02 DECODED: %s" % (hexMsgPrtTwo))
                                                logger.info("####################################################################")
                                            # Print statement
                                            else:
                                                print "DEBUG_GSM: Received GPS location message part 02 DECODED: %s" % (hexMsgPrtTwo)
                                                print "####################################################################"
                                            break
                                        else:
                                            uCounter += 1
                                            if uCounter == 2:
                                                hexVal += oneChar
                                                if hexVal != '00':
                                                    hexMsgPrtTwo += hexVal
                                                hexVal = ''
                                                uCounter = 0
                                            else:
                                                hexVal += oneChar 

                    # Previously the cell phone no. and decode message are valid
                    if validCellNo == True and msgPartOneCorr == True and msgPartTwoCorr == True:            
                        # Append 2 part into 1 decoded GPS location
                        decodedGPSMsg = hexMsgPrtOne + hexMsgPrtTwo
                                                
                        # Write to logger
                        if backLogger == True:
                            logger.info("DEBUG_GSM: Received GPS location message DECODED: %s" % (decodedGPSMsg))
                            logger.info("####################################################################")
                        # Print statement
                        else:
                            print "DEBUG_GSM: Received GPS location message DECODED: %s" % (decodedGPSMsg)
                            print "####################################################################"

                        # Start process the GPS location data
                        fndLatitude = False
                        fndLongitude = False
                        fndCourse = False
                        fndSpeed = False
                        timeStamp = False
                        gpsStat = False
                        latValue = ''
                        lonValue = ''
                        courseValue = ''
                        speedValue = ''
                        timeStmpValue = ''
                        gpsStatus = ''
                        decodedLength = len(decodedGPSMsg)
                        #
                        for a in range(0, (decodedLength + 1)):
                            oneChar = mid(decodedGPSMsg, a, 1)
                            # Find GPS status: Last Position or Current Position
                            if oneChar == '!' and gpsStat == False:
                                # Write to logger
                                if backLogger == True:
                                    logger.info("DEBUG_GSM: GPS Status: %s" % (gpsStatus))
                                    logger.info("####################################################################")
                                # Print statement
                                else:
                                    print "DEBUG_GSM: GPS Status: %s" % (gpsStatus)
                                    print "####################################################################"
                                gpsStat = True

                            elif oneChar != '!' and gpsStat == False:
                                gpsStatus += oneChar
                            
                            # Find a start char to get latitude value
                            if oneChar == ':' and fndLatitude == False:
                                fndLatitude = True
                            
                            # Start retrieve latitude value
                            elif fndLatitude == True and fndLongitude == False:
                                # End of the search, find longitude value
                                if oneChar == ':':
                                    # Write to logger
                                    if backLogger == True:
                                        logger.info("DEBUG_GSM: Latitude: %s" % (latValue))
                                        logger.info("####################################################################")
                                    # Print statement
                                    else:
                                        print "DEBUG_GSM: Latitude: %s" % (latValue)
                                        print "####################################################################"
                                    fndLongitude = True
                                else:
                                    # Only take number
                                    if oneChar != ',' and oneChar != 'L' and oneChar != 'o' and oneChar != 'n':
                                        latValue += oneChar

                            # Start retrieve longitude value
                            elif fndLongitude == True and fndCourse == False:
                                # End of the search, find course value
                                if oneChar == ':':
                                    # Write to logger
                                    if backLogger == True:
                                        logger.info("DEBUG_GSM: Longitude: %s" % (lonValue))
                                        logger.info("####################################################################")
                                    # Print statement
                                    else:
                                        print "DEBUG_GSM: Longitude: %s" % (lonValue)
                                        print "####################################################################"
                                    fndCourse = True
                                else:
                                    # Only take number
                                    if oneChar != 'C' and oneChar != 'o' and oneChar != 'u' and oneChar != 'r' and \
                                       oneChar != 's' and oneChar != 'e' and oneChar != ',':
                                        lonValue += oneChar

                            # Start retrieve course value
                            elif fndCourse == True and fndSpeed == False:
                                # End of the search, find course value
                                if oneChar == ':':
                                    # Write to logger
                                    if backLogger == True:
                                        logger.info("DEBUG_GSM: Course: %s" % (courseValue))
                                        logger.info("####################################################################")
                                    # Print statement
                                    else:
                                        print "DEBUG_GSM: Course: %s" % (courseValue)
                                        print "####################################################################"
                                    fndSpeed = True
                                else:
                                    # Only take number
                                    if oneChar != 'S' and oneChar != 'p' and oneChar != 'e' and oneChar != 'e' and \
                                       oneChar != 'd' and oneChar != ',':
                                        courseValue += oneChar

                            # Start retrieve speed value
                            elif fndSpeed == True and timeStamp == False:
                                # End of the search, find course value
                                if oneChar == ':':
                                    # Write to logger
                                    if backLogger == True:
                                        logger.info("DEBUG_GSM: Speed: %s" % (speedValue))
                                        logger.info("####################################################################")
                                    # Print statement
                                    else:
                                        print "DEBUG_GSM: Speed: %s" % (speedValue)
                                        print "####################################################################"
                                    timeStamp = True
                                else:
                                    # Only take number
                                    if oneChar != 'D' and oneChar != 'a' and oneChar != 't' and oneChar != 'e' and \
                                       oneChar != 'T' and oneChar != 'i' and oneChar != 'm' and \
                                       oneChar != 'e' and oneChar != ',':
                                        speedValue += oneChar

                            # Start retrieve time stamp
                            elif timeStamp == True:
                                timeStmpValue += oneChar

                        # Write to logger
                        if backLogger == True:
                            logger.info("DEBUG_GSM: Time Stamp: %s" % (timeStmpValue))
                            logger.info("####################################################################")
                        # Print statement
                        else:
                            print "DEBUG_GSM: Time Stamp: %s" % (timeStmpValue)
                            print "####################################################################"

                        # Update python data dictionary with GPS location
                        try:
                            # Check the cell number whether its already exist or not
                            # Update the existing data, throw error if record is not exist, consider its a new data
                            extDB = [ extDBB for extDBB in gpsTrackerListData if (extDBB['gpsid'] == cellPhoneNo) ]

                            extDB[0]['latitude'] = latValue
                            extDB[0]['longitude'] = lonValue
                            extDB[0]['course'] = courseValue
                            extDB[0]['speed'] = speedValue
                            extDB[0]['status'] = gpsStatus
                            extDB[0]['datetime'] = timeStmpValue
                            
                        # New cell number
                        except:
                            # Construct the new data
                            newData = {
                                        'gpsid' : cellPhoneNo,
                                        'latitude' : latValue,
                                        'longitude' : lonValue,
                                        'course' : courseValue,
                                        'speed' : speedValue,
                                        'status' : gpsStatus,
                                        'datetime' : timeStmpValue
                                        }
                            # Append a NEW extension to the existing record
                            gpsTrackerListData.append(newData)

                        # Display the current python data dictionary
                        # Write to logger
                        if backLogger == True:
                            logger.info("DEBUG_GSM: GPS JSON Data:")
                            logger.info("####################################################################")
                            logger.info(gpsTrackerListData)
                            logger.info("####################################################################")
                        # Print statement
                        else:
                            print "DEBUG_GSM: Time Stamp: %s" % (timeStmpValue)
                            print "####################################################################"
                        
                        # Delete back SMS message at index no. 1
                        serialGSM.write(b'AT+CMGDA="DEL ALL"\r')
                        # Delay for send command before process the reply 
                        time.sleep(1)
                        # Start check the reply from GSM modem
                        gsmReply = serialGSM.read(serialGSM.inWaiting())
                        # Previous command send OK 
                        if 'OK' in gsmReply or 'ERROR' in gsmReply:
                            # Poll request for GPS location continue to the next index
                            if cellPhoneCnt > 1:
                                # Reset counter after reach the last cell phone number
                                if cellNoIndx == (cellPhoneCnt - 1):
                                    cellNoIndx = 0
                                # Increment index
                                else:
                                    cellNoIndx += 1
                            waitSendMsg = False

                            hexMsgPrtOne = ''
                            hexMsgPrtTwo = ''
                            decodedGPSMsg = ''
                            cellPhoneNo = ''
                            cmtiCnt = 0
                            timeOutCnt = 0
                            gpsComplete = False
                            validCellNo = False
                            msgPartOneCorr = False
                            msgPartTwoCorr = False
        
                            # Write to logger
                            if backLogger == True:
                                logger.info("DEBUG_GSM: Delete ALL SMS message successful, Reply AT command: %s" % (gsmReply))
                                logger.info("####################################################################")
                            # Print statement
                            else:
                                print "DEBUG_GSM: Delete ALL SMS message successful, Reply AT command: %s" % (gsmReply)
                                print "####################################################################"

                    # Previously the cell phone no. and decode message are invalid
                    else:
                        # Write to logger
                        if backLogger == True:
                            logger.info("DEBUG_GSM: Error in receiving GPS poll request SMS message!")
                            logger.info("####################################################################")
                        # Print statement
                        else:
                            print "DEBUG_GSM: Error in receiving GPS poll request SMS message!"
                            print "####################################################################"

                        # Delete back SMS message at index no. 1
                        serialGSM.write(b'AT+CMGDA="DEL ALL"\r')
                        # Delay for send command before process the reply 
                        time.sleep(1)
                        # Start check the reply from GSM modem
                        gsmReply = serialGSM.read(serialGSM.inWaiting())
                        # Previous command send OK 
                        if 'OK' in gsmReply or 'ERROR' in gsmReply:
                            # Poll request for GPS location continue to the next index
                            if cellPhoneCnt > 1:
                                # Reset counter after reach the last cell phone number
                                if cellNoIndx == (cellPhoneCnt - 1):
                                    cellNoIndx = 0
                                # Increment index
                                else:
                                    cellNoIndx += 1
                            waitSendMsg = False

                            hexMsgPrtOne = ''
                            hexMsgPrtTwo = ''
                            decodedGPSMsg = ''
                            cellPhoneNo = ''
                            cmtiCnt = 0
                            timeOutCnt = 0
                            gpsComplete = False
                            validCellNo = False
                            msgPartOneCorr = False
                            msgPartTwoCorr = False

                            # Write to logger
                            if backLogger == True:
                                logger.info("DEBUG_GSM: Delete ALL SMS message successful, Reply AT command: %s" % (gsmReply))
                                logger.info("####################################################################")
                            # Print statement
                            else:
                                print "DEBUG_GSM: Delete ALL SMS message successful, Reply AT command: %s" % (gsmReply)
                                print "####################################################################"
                                
            # Check time out for waiting
            else:
                # Increment time out counting
                timeOutCnt += 1
                # Not received GPS location, stop waiting, continue to the next index
                if timeOutCnt == gpsLocTimeOut:
##                    # Delete back SMS message at index no. 1
##                    serialGSM.write('AT+CMGDA="DEL ALL"\r')
##                    # Delay for send command before process the reply 
##                    time.sleep(1)
##                    # Start check the reply from GSM modem
##                    gsmReply = serialGSM.read(serialGSM.inWaiting())
##                    # Previous command send OK 
##                    if 'OK' in gsmReply or 'ERROR' in gsmReply:
##                        # Write to logger
##                        if backLogger == True:
##                            logger.info("DEBUG_GSM: Delete ALL SMS message successful, Reply AT command: %s" % (gsmReply))
##                            logger.info("####################################################################")
##                        # Print statement
##                        else:
##                            print "DEBUG_GSM: Delete ALL SMS message successful, Reply AT command: %s" % (gsmReply)
##                            print "####################################################################"

                    # Write to logger
                    if backLogger == True:
                        logger.info("DEBUG_GSM: WAITING for SMS time out!")
                        logger.info("####################################################################")
                    # Print statement
                    else:
                        print "DEBUG_GSM: WAITING for SMS time out!"
                        print "####################################################################"

                    # Poll request for GPS location continue to the next index
                    if cellPhoneCnt > 1:
                        # Reset counter after reach the last cell phone number
                        if cellNoIndx == (cellPhoneCnt - 1):
                            cellNoIndx = 0
                        # Increment index
                        else:
                            cellNoIndx += 1
                    
                    timeOutCnt = 0
                    hexMsgPrtOne = ''
                    hexMsgPrtTwo = ''
                    decodedGPSMsg = ''
                    cellPhoneNo = ''
                    cmtiCnt = 0
                    gpsComplete = False
                    
                    waitSendMsg = False     
                        
            # Poll current GPS location by sending SMS message to GPS vehicle tracker
            if waitSendMsg == False:
                # Polling request for GPS location are enable by macro
                if enaGPSPoll == True:
                    pollDisDelSms = False
                    
                    # Start send current GPS location request
                    sendCmdMsg = b'AT+CMGS=' + '"' + cellPhoneList[cellNoIndx] + '"' + b'\r'
                    serialGSM.write(str.encode(sendCmdMsg))
                    # Delay for send command before process the reply 
                    time.sleep(3)

                    serialGSM.flushOutput()

                    time.sleep(1)

                    # Send the contents of the SMS message
                    sendCmdMsg = 'WHERE#'
                    #serialGSM.write(sendCmdMsg)
                    serialGSM.write(sendCmdMsg)
                    time.sleep(1)
                    serialGSM.write(str.encode(chr(26)))
                    time.sleep(3)
                    
                    # Write to logger
                    if backLogger == True:
                        logger.info("DEBUG_GSM: Send GPS location request [%s] successful" % (cellPhoneList[cellNoIndx]))
                        logger.info("####################################################################")
                    # Print statement
                    else:
                        print "DEBUG_GSM: Send GPS location request [%s] successful" % (cellPhoneList[cellNoIndx])
                        print "####################################################################"

                    serialGSM.flushOutput()
                    # Wait for acknowledge with a current GPS location before send another request
                    waitSendMsg = True
                    # Clear serial communication buffer
                    #serialGSM.read(serialGSM.inWaiting())
                
                # Polling request for GPS location are disable by macro     
                else:
                    # Delete ALL SMS message, only once each time after GPS location poll request are disable 
                    if pollDisDelSms == False:
                        # Start RESET the GPS information
                        reset_gpsinfo()
                        
                        # Delete back SMS message at index no. 1
                        serialGSM.write(b'AT+CMGDA="DEL ALL"\r')
                        # Delay for send command before process the reply 
                        time.sleep(1)
                        # Start check the reply from GSM modem
                        gsmReply = serialGSM.read(serialGSM.inWaiting())
                        # Previous command send OK 
                        if 'OK' in gsmReply or 'ERROR' in gsmReply:
                            # Write to logger
                            if backLogger == True:
                                logger.info("DEBUG_GSM: Delete ALL SMS message successful, Reply AT command: %s" % (gsmReply))
                                logger.info("####################################################################")
                            # Print statement
                            else:
                                print "DEBUG_GSM: Delete ALL SMS message successful, Reply AT command: %s" % (gsmReply)
                                print "####################################################################"

                        serialGSM.flushOutput()
                        time.sleep(1)

                        # Reset necessary variable
                        waitSendMsg = False
                        cellNoIndx = 0
                        
                        pollDisDelSms = True
                        
                    # Write to logger
                    if backLogger == True:
                        logger.info("DEBUG_GSM: POLL GPS location DISABLE!")
                        logger.info("####################################################################")
                    # Print statement
                    else:
                        print "DEBUG_GSM: POLL GPS location DISABLE!"
                        print "####################################################################"
                    
        time.sleep(delay)                
                        
# Script entry point
def main():
    global backLogger
    global secureInSecure
    
    # Create thread for serial communication with GSM modem
    try:
        thread.start_new_thread(serial_sms_comm, ("[serial_sms_comm]", 5 ))
    except:
        logger.info("Error: Unable to start [serial_sms_comm] thread")

    # Write to logger
    if backLogger == True:
        logger.info("DEBUG_REST_API: RestFul API web server STARTED")
    # Print statement
    else:
        print "DEBUG_REST_API: RestFul API web server STARTED"
        
    if __name__ == "__main__":
        if secureInSecure == True:
            # RUN RestFul API web server
            # Add a certificate to make sure REST web API can support HTTPS request
            # Generate first cert.pem (new certificate) and key.pem (new key) by initiate below command:
            # openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
            #app.run(host='0.0.0.0', port=8000, ssl_context=('cert.pem', 'key.pem'))
            #app.run(host='0.0.0.0', port=8000, ssl_context=('asterisk.pem', 'ca.key'))
            app.run(host='0.0.0.0', port=9000, ssl_context=('fullchain.pem', 'ca.key'))
        # Insecure web server (HTTP) - Default port 5000
        else:
            app.run(host='0.0.0.0', port=9000)        
if __name__ == "__main__":
    main()

    

    


