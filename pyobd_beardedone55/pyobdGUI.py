#!/usr/bin/env python3
# vim: shiftwidth=4:tabstop=4:expandtab
############################################################################
#
# pyobdGUI.py
#
# Copyright 2004 Donour Sizemore (donour@uchicago.edu)
# Copyright 2009 Secons Ltd. (www.obdtester.com)
# Copyright 2019 Brian LePage (github.com/beardedone55/)
#
# This file is part of pyOBD.
#
# pyOBD is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# pyOBD is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyOBD; if not, see https://www.gnu.org/licenses/.
############################################################################
############################################################################
#
# Modified from the original by Brian LePage on the following dates:
#   June 2, 2018
#   June 6, 2018
#   July 3, 2018
#   September 29, 2018
#   November 30, 2018
#   December 2, 2018
#   December 25, 2018
#   January 22, 2019
#   February 18, 2019
#   February 19, 2019
#   February 23, 2019
#   February 27, 2019
#   March 2, 2019
#   March 31, 2019
#   April 5, 2019
#   May 11, 2019
#   May 23, 2019
#   May 26, 2019
#
# For a complete history, see https://github.com/beardedone55/pyobd
############################################################################

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from . import obd_io #OBD2 funcs
import os #os.environ

import sys
import serial
from serial.tools import list_ports
import platform
import time
import configparser #safe application configuration
import webbrowser #open browser from python
import logging

from .obd2_codes import pcodes
from .obd2_codes import ptest

ID_ABOUT  = 101
ID_EXIT   = 110
ID_CONFIG = 500
ID_CLEAR  = 501
ID_GETC   = 502
ID_RESET  = 503
ID_LOOK   = 504
ALL_ON    = 505
ALL_OFF   = 506

ID_DISCONNECT = 507
ID_HELP_ABOUT = 508
ID_HELP_VISIT = 509
ID_HELP_ORDER = 510

class MyApp(QApplication):

    StatusEvent = pyqtSignal(list)
    ResultEvent = pyqtSignal(str,int, int, str)
    TestEvent = pyqtSignal(list)
    DTCEvent = pyqtSignal(list)
    DTCClearEvent = pyqtSignal(int)
    SensorProducerReady = pyqtSignal()

    def __init__(self, myArgs):
        super().__init__(myArgs)
        self.OnInit()

    # A listctrl which auto-resizes the column boxes to fill
    # removed style for now
    class MyListCtrl(QTableWidget):
        def __init__(self, sortable=True):
            super().__init__()
            self.horizontalHeader().setStretchLastSection(True)
            self.verticalHeader().hide()
            self.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.sortable = sortable

        def addTableRow(self, rowSize, data, bold=False, italic=False, alignment=Qt.AlignLeft):
            newRow = self.rowCount()
            self.insertRow(newRow)
            #Truncate data to length of table row and populate row
            for i, cellData in enumerate(data[:rowSize]):
                cellData = QTableWidgetItem(cellData)
                cellData.setFlags(cellData.flags() & ~Qt.ItemIsEditable) #Make item uneditable
                cellData.setTextAlignment(alignment | Qt.AlignVCenter)
                font = cellData.font()
                font.setBold(bold)
                font.setItalic(italic)
                cellData.setFont(font)
                self.setItem(newRow, i, cellData)

            if rowSize > len(data):
                self.setSpan(newRow, len(data)-1, 1, rowSize - (len(data)-1))

        def setColumnCount(self, columns):
            super().setColumnCount(columns)
            if self.sortable:
                self.horizontalHeader().sectionClicked.connect(self.sortMyList)

        def sortMyList(self, column):
            header = self.horizontalHeader()
            if not header.isSortIndicatorShown():
                header.setSortIndicatorShown(True)

            self.sortItems(column, header.sortIndicatorOrder())

    class SensorList(MyListCtrl):

        SENSOR_OFF = '1'
        SENSOR_ON = '0'

        def __init__(self, ecu):
            super().__init__()
            self.pid_lookup = {}
            self.senprod = None
            self.ecu = ecu
            icon_path = os.path.dirname(__file__) + '/icons_gpl'
            self.checkBoxClear = QPixmap(icon_path + '/Checkbox-Empty-icon.png')
            self.checkBoxFull = QPixmap(icon_path + '/Checkbox-Full-icon.png')
            self.checkBoxes = {}

        def addTableRow(self, rowSize, data):
            super().addTableRow(rowSize, data, alignment=Qt.AlignHCenter)
            pid = data[self.pid_column]
            newRowNum = self.rowCount() - 1
            self.pid_lookup[pid] = newRowNum
            checkbox = QLabel()
            checkbox.setAlignment(Qt.AlignCenter)
            self.setCellWidget(newRowNum,self.active_column,checkbox)
            checkbox.setPixmap(self.checkBoxClear)
            self.item(newRowNum,self.last_column).setText(str(self.SENSOR_OFF))
            self.checkBoxes[int(pid)] = checkbox

        def setColumnCount(self, columns, pid_column, active_column = 0):
            super().setColumnCount(columns+1)
            self.pid_column = pid_column
            self.active_column = active_column
            self.last_column = columns
            self.setColumnHidden(pid_column, True)
            #last column will be used to sort by 'Active'
            self.setColumnHidden(self.last_column, True)

        def sortMyList(self, column):
            if column == self.active_column:
                column = self.last_column
            super().sortMyList(column)
            for i in range(self.rowCount()):
                pid = self.item(i, self.pid_column).text()
                self.pid_lookup[pid] = i

        def getPid(self, row):
            return self.item(row, self.pid_column).text()

        def setSensorThread(self,senprod):
            self.senprod = senprod

        def sensor_toggle(self, row, col):
            pid = int(self.getPid(row))
            ecu = self.ecu
            checkbox = self.checkBoxes[pid]

            if self.item(row,self.last_column).text() != self.SENSOR_ON:
                self.item(row,self.last_column).setText(self.SENSOR_ON)
                self.senprod.signals.sensorOnEvent.emit(pid,ecu)
                checkbox.setPixmap(self.checkBoxFull)
            else:
                self.senprod.signals.sensorOffEvent.emit(pid,ecu)
                self.item(row,self.last_column).setText(self.SENSOR_OFF)
                checkbox.setPixmap(self.checkBoxClear)

    class TestList(MyListCtrl):
        def __init__(self):
            super().__init__()
            self.setColumnCount(2)
            self.setHorizontalHeaderLabels(['Built-In Test Description','Status'])
            self.horizontalHeader().setStretchLastSection(False)
            self.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
            self.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
            self.testStatusItems = {}

            self.addTableRow(2,[ptest[0], '0'])
            self.dtcNumItem = self.item(0,1)
            self.dtcNumItem.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

            for i,description in enumerate(ptest[1:],1): #fill MODE 1 PID 1 test description
                self.addTableRow(1, [description])
                testStatusItem = QLabel()
                testStatusItem.setAlignment(Qt.AlignCenter)
                self.setCellWidget(i,1,testStatusItem)
                self.testStatusItems[description] = testStatusItem

        def addTableRow(self, rowSize, data):
            rowNum = self.rowCount()
            super().addTableRow(rowSize, data)
            self.hideRow(rowNum)

        def setStatusIcon(self, row, icon):
            self.testStatusItems[self.item(row,0).text()].setPixmap(icon)
            self.showRow(row)

        def setIconForTest(self, test, icon):
            testStatusItem = self.testStatusItems[test]
            testStatusItem.setPixmap(icon)
            for i in range(self.rowCount()):
               if self.cellWidget(i,1) is testStatusItem:
                    self.showRow(i)
                    break 

        def setNumDTCs(self, numDTCs):
            self.dtcNumItem.setText(str(numDTCs))
            self.showRow(self.row(self.dtcNumItem))

    #Add a Widget to a panel with a layout and return the Panel
    class MyPanel(QWidget):
        def __init__(self, widget=None):
            super().__init__()
            layout = QVBoxLayout()
            if widget is not None:
                layout.addWidget(widget)
            self.setLayout(layout)

    class MyNumberInput(QLineEdit):
        def __init__(self, defaultText='', width=20):
            super().__init__(defaultText)
            self.setFixedWidth(width)
            validator = QIntValidator()
            validator.setBottom(0)
            self.setValidator(validator)

    class sensorProducer(QThread):
        class CustomSlots(QObject):
            sensorTabEvent = pyqtSignal(str)
            sensorOnEvent = pyqtSignal(int,str)
            sensorOffEvent = pyqtSignal(int,str)
            sensorAllOffEvent = pyqtSignal(str)

            def __init__(self):
                super().__init__()

            def connectSlots(self, parent):
                self.sensorOnEvent.connect(parent.on)
                self.sensorOffEvent.connect(parent.off)
                self.sensorAllOffEvent.connect(parent.all_off)
                self.sensorTabEvent.connect(parent.selectEcu)

            def disconnectSlots(self):
                self.sensorOnEvent.disconnect()
                self.sensorOffEvent.disconnect()
                self.sensorAllOffEvent.disconnect()
                self.sensorTabEvent.disconnect()

        def __init__(self,_notify_window):
            self._notify_window=_notify_window
            self.active = {}
            super().__init__ ()

        def run(self):

            self.signals = self.CustomSlots()
            
            self.ecu = None

            self.signals.connectSlots(self)

            #Thread is ready to take events
            self._notify_window.SensorProducerReady.emit()

            port = self._notify_window.port

            while not self.isInterruptionRequested():
                QCoreApplication.processEvents()
                ecu = self.ecu
                if ecu is not None and len(self.active[ecu]) > 0:
                    results = port.get_sensors(self.active[ecu], ecu)
                    for pid,s in results.items():
                        self._notify_window.ResultEvent.emit(ecu,pid,4,"%s (%s)" % (s[1], s[2]))

            self.signals.disconnectSlots()

        def off(self, pid, ecu):
            if ecu not in self.active:
                self.active[ecu] = []

            if pid in self.active[ecu]:
                self.active[ecu].remove(pid)

        def on(self, pid, ecu):
            if ecu not in self.active:
                self.active[ecu] = []

            if pid not in self.active[ecu]:
                self.active[ecu].append(pid)

        def all_off(self, ecu):
            self.active[ecu] = []

        def selectEcu(self, ecu):
            if ecu == 'None':
                self.ecu = None
            else:
                if ecu not in self.active:
                    self.active[ecu] = []
                self.ecu = ecu

  #class producer end
    class LogHandler(logging.Handler):
        def __init__(self,logDisplay):
            super().__init__()
            self.logDisplay = logDisplay

        def emit(self,record):
            record = self.format(record)
            self.logDisplay.append(record)

    class LogDisplay(QTextEdit):
        def __init__(self):
            super().__init__()
            self.setReadOnly(True)
            self.setLineWrapMode(QTextEdit.NoWrap)

    def stop(self):
        if self.port != None: #if stop is called before any connection port is not defined (and not connected )
            self.port.close()
        self.StatusEvent.emit([0,1,"Disconnected"])
        self.StatusEvent.emit([2,1,"----"])

    def initCommunication(self):
        self.StatusEvent.emit([0,1,"Connecting...."])
        self.port = obd_io.OBDPort(self.COMPORT,self.BAUDRATE,self,self.SERTIMEOUT,self.RECONNATTEMPTS)

        if self.port.State==0: #Cant open serial port
            return None

        self.logger.info("Communication initialized...")

        vinList = []

        if len(self.port.ecu_addresses) > 0:
            for ecu in self.port.ecu_addresses:
                self.updateTestTable(ecu)
                supp = self.port.get_supported(ecu) #read supported mode $01
                                                    #PIDS of each ECU that responds
                ecuName = 'ECU' + str(self.port.getEcuNum(ecu))
                self.add_sensor_table(ecuName, ecu, supp)
                vin = self.port.get_vin(ecu)
                if vin != '':
                    vinList.append(vin)

            self.StatusEvent.emit([4,1,','.join(vinList)])

        return "OK"

    def sensor_control_on(self): #after connection enable few buttons
        self.configAction.setEnabled(False)
        self.connectAction.setEnabled(False)
        self.disconnectAction.setEnabled(True)
        self.getDTCAction.setEnabled(True)
        self.clearDTCAction.setEnabled(True)
        self.GetDTCButton.setEnabled(True)
        self.ClearDTCButton.setEnabled(True)

        for sensorTable in self.sensorTables.values():
           sensorTable.cellClicked.connect(sensorTable.sensor_toggle)

    def sensor_control_off(self): #after disconnect disable fer buttons
        self.getDTCAction.setEnabled(False)
        self.clearDTCAction.setEnabled(False)
        self.configAction.setEnabled(True)
        self.connectAction.setEnabled(True)
        self.disconnectAction.setEnabled(False)
        self.GetDTCButton.setEnabled(False)
        self.ClearDTCButton.setEnabled(False)
        for sensorTable in self.sensorTables.values():
            sensorTable.cellClicked.disconnect()

    def add_sensor_table(self, title, ecu, supp):
        sensorTable = self.SensorList(ecu)
        self.sensorTables[ecu] = sensorTable
        pid_column = 2
        sensorTable.setColumnCount(5,pid_column)
        sensorTable.setHorizontalHeaderLabels(['Active','PID', 'PID','Sensor','Value'])
        sensorTable.setColumnWidth(0,55)
        sensorTable.setColumnWidth(1,40)
        sensorTable.setColumnWidth(3,250)
        #Create entry in table for each supported PID (excluding PID $01)
        #Decode of PID $01 is on Test tab
        for i, supported in enumerate(supp[1:],2):
            if supported == '1':
                obd_sensor = obd_io.obd_sensors.SENSORS[i]
                s = obd_sensor.name
                pid_hex = obd_sensor.cmd[-2:]
                pid_dec = int(pid_hex,16)
                row = sensorTable.rowCount()
                sensorTable.addTableRow(6, ['','$' + pid_hex, str(pid_dec), s, '',''])
                sensorTable.item(row,3).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.sensorTabs.addTab(sensorTable, title)

    def updateTestTable(self,ecu):
        res = self.port.get_tests(ecu)
        for test in ptest:
            if test == ptest[0]:
                self.OBDTests.setNumDTCs(res[test])
            elif test == ptest[1]:
                if res[test]:
                    self.OBDTests.setIconForTest(test, self.checkEngineIcon)
                else:
                    self.OBDTests.setIconForTest(test, self.checkEngineOffIcon)
            else:
                if res[test] == 1:
                    self.OBDTests.setIconForTest(test, self.completeIcon)
                elif res[test] == -1:
                    self.OBDTests.setIconForTest(test, self.failedIcon)

    def build_sensor_page(self):
        self.sensorTabs = QTabWidget()
        self.sensorTabs.tabBarClicked.connect(self.sensorTabClicked)
        sensorPage = self.MyPanel(self.sensorTabs)
        self.nb.addTab(sensorPage, "Live Data")

    def build_DTC_page(self):
        self.DTCpanel = QWidget()
        self.GetDTCButton  = QPushButton('Get DTC')
        self.ClearDTCButton = QPushButton('Clear DTC')

        panelLayout = QGridLayout()
        panelLayout.addWidget(self.GetDTCButton,0,0)
        panelLayout.addWidget(self.ClearDTCButton,0,1)

        #bind functions to button click action
        self.GetDTCButton.clicked.connect(self.GetDTC)
        self.ClearDTCButton.clicked.connect(self.QueryClear)

        self.dtc = self.MyListCtrl()

        self.dtc.setColumnCount(3)
        self.dtc.setHorizontalHeaderLabels(['Code','Status','Trouble Code'])
        self.dtc.setColumnWidth(0,100)
        self.dtc.setColumnWidth(1,100)
        panelLayout.addWidget(self.dtc,1,0,1,2)
        self.DTCpanel.setLayout(panelLayout)

        self.nb.addTab(self.DTCpanel, "DTC")

    def exportLog(self):
        filename = QFileDialog.getSaveFileName(caption='Export Log to File...')
        try:
            fh = open(filename[0],'w')
            logdata = self.logDisplay.toPlainText()
            fh.write(logdata)
        except Exception as e:
            self.logger.error('Error exporting log file!!!')
            self.logger.error('%s',str(e))

    def write_config(self):
        with open(self.configfilepath, 'w') as f:
            self.config.write(f)

    def build_log_page(self):
        tracePanel = QWidget()
        self.logDisplay = self.LogDisplay()
        logHandlers = [self.LogHandler(self.logDisplay)]

        def removeLogFile(self):
            self.logToFile = False
            self.logFile = ''
            self.config.set('pyOBD','LOGTOFILE',self.logToFile)
            self.config.set('pyOBD','LOGFILE',self.logFile)
            self.write_config()

        logging.basicConfig(level=self.logLevel, handlers = logHandlers, \
                            format = '%(levelname)s:\t%(message)s')

        self.logger = logging.getLogger('PyOBD')

        if self.logToFile:
            try:
                logFileHandler = logging.FileHandler(self.logFile,'w')
            except Exception as e:
                self.logger.warning('Error opening log file: %s', str(e))
                removeLogFile(self)
            else:
                self.logFileHandler = logFileHandler
                self.logger.addHandler(self.logFileHandler)

        LogExportButton  = QPushButton('Export Log')
        LogExportButton.clicked.connect(self.exportLog)

        panelLayout = QVBoxLayout()
        panelLayout.addWidget(self.logDisplay)
        panelLayout.addWidget(LogExportButton,alignment=Qt.AlignRight)
        tracePanel.setLayout(panelLayout)
        self.nb.addTab(tracePanel, "Trace")

    def OnInit(self):

        self.ThreadControl = 0 #say thread what to do
        self.COMPORT = 0
        self.BAUDRATE = 0
        self.senprod = None
        self.DEBUGLEVEL = 0 #debug everthing
        self.sensorTables = {}
        self.port = None

        icon_path = os.path.dirname(__file__) + '/icons_free'
        self.completeIcon = QPixmap(icon_path + '/check-icon2.png')
        self.failedIcon = QPixmap(icon_path + '/delete-icon.png')
        icon_path = os.path.dirname(__file__) + '/icons_pubdomain'
        self.checkEngineIcon = QPixmap(icon_path + '/check-engine.png')
        self.checkEngineOffIcon = QPixmap(icon_path + '/check-engine-off.png')

        def CreateMenuItem(ItemName, ToolTipText, ItemTrigger):
            menuItemAction = QAction(ItemName)
            menuItemAction.setStatusTip(ToolTipText)
            menuItemAction.triggered.connect(ItemTrigger)
            return menuItemAction


        #read settings from file
        self.config = configparser.RawConfigParser()

        #print platform.system()
        #print platform.mac_ver()[]

        if "OS" in os.environ.keys(): #runnig under windows
            self.configfilepath="pyobd.ini"
        else:
            self.configfilepath=os.environ['HOME']+'/.pyobdrc'
        if not self.config.read(self.configfilepath):
            self.COMPORT="/dev/ttyACM0"
            self.RECONNATTEMPTS=5
            self.SERTIMEOUT=5
            self.BAUDRATE='9600'
            self.logLevel=logging.WARNING
            self.logToFile = False
            self.logFile = ''
        else:
            self.COMPORT=self.config.get("pyOBD","COMPORT",fallback='/dev/ttyACM0')
            self.BAUDRATE=self.config.get("pyOBD","BAUDRATE",fallback='9600')
            self.RECONNATTEMPTS=self.config.getint("pyOBD","RECONNATTEMPTS",fallback=5)
            self.SERTIMEOUT=self.config.getint("pyOBD","SERTIMEOUT",fallback=5)
            self.logLevel=self.config.getint('pyOBD','LOGLEVEL',fallback=logging.WARNING)
            self.logToFile=self.config.getboolean('pyOBD','LOGTOFILE',fallback=False)
            self.logFile=self.config.get('pyOBD','LOGFILE',fallback='')

        frame = QMainWindow()
        frame.setWindowTitle('pyOBD-II')
        self.frame=frame

        self.ResultEvent.connect(self.OnResult)
        self.DTCEvent.connect(self.OnDtc)
        self.DTCClearEvent.connect(self.OnDtcClear)
        self.StatusEvent.connect(self.OnStatus)
        self.TestEvent.connect(self.OnTests)

        # Main notebook frames

        self.nb = QTabWidget(frame)
        self.nb.tabBarClicked.connect(self.tabClicked)
        self.frame.setCentralWidget(self.MyPanel(self.nb))

        self.status = self.MyListCtrl(sortable=False)
        self.status.setColumnCount(2)
        self.status.setHorizontalHeaderLabels(['Description','Value'])
        self.status.setColumnWidth(0,200)
        self.status.addTableRow(2, ['Link State', 'Disconnected'])
        self.status.addTableRow(2, ['Protocol', '---'])
        self.status.addTableRow(2, ['Cable Version', '---'])
        self.status.addTableRow(2, ['COM Port', self.COMPORT])
        self.status.addTableRow(2, ['Vehicle Identification Number', '-----------------'])

        statusPanel  = self.MyPanel(self.status)
        self.nb.addTab(statusPanel, "Status")

        self.OBDTests = self.TestList()

        OBDTestPanel = self.MyPanel(self.OBDTests)
        self.nb.addTab(OBDTestPanel, "Tests")

        self.build_sensor_page()

        self.build_DTC_page()

        self.build_log_page()

        self.logger.debug("Application started")

        self.frame.statusBar()

        # Creating the menubar.
        self.menuBar = self.frame.menuBar()
        self.filemenu = self.menuBar.addMenu("&File") # Adding the "filemenu" to the MenuBar
        self.settingmenu = self.menuBar.addMenu("&OBD-II")
        self.dtcmenu = self.menuBar.addMenu("&Trouble codes")
        self.optionsmenu = self.menuBar.addMenu("&Options")
        self.helpmenu = self.menuBar.addMenu("&Help")

        # Setting up the menu.

        self.exitAction = CreateMenuItem("E&xit"," Terminate the program", self.OnExit)
        self.filemenu.addAction(self.exitAction)
        self.aboutToQuit.connect(self.exitCleanup)

        self.configAction = CreateMenuItem("Configure"," Configure pyOBD",self.Configure)
        self.connectAction = CreateMenuItem("Connect"," Reopen and connect to device",self.OpenPort)
        self.disconnectAction = CreateMenuItem("Disconnect","Close connection to device",self.OnDisconnect)
        self.settingmenu.addAction(self.configAction)
        self.settingmenu.addAction(self.connectAction)
        self.settingmenu.addAction(self.disconnectAction)

        # tady toto nastavi automaticky tab DTC a provede akci
        self.getDTCAction = CreateMenuItem("Get DTCs",   " Get DTC Codes", self.GetDTC)
        self.clearDTCAction = CreateMenuItem("Clear DTC",  " Clear DTC Codes", self.QueryClear)
        self.codeLookupAction = CreateMenuItem("Code Lookup"," Lookup DTC Codes", self.CodeLookup)
        #self.testDTCAction = CreateMenuItem("Test DTC"," Test DTCs", self.onTestDTC)
        self.dtcmenu.addAction(self.getDTCAction)
        self.dtcmenu.addAction(self.clearDTCAction)
        self.dtcmenu.addAction(self.codeLookupAction)
        #self.dtcmenu.addAction(self.testDTCAction)

        self.logoptionsAction = CreateMenuItem("Logging Options","",self.setLoggingOptions)
        self.optionsmenu.addAction(self.logoptionsAction)

        self.aboutAction = CreateMenuItem("About this program","",self.OnHelpAbout)
        self.visitAction = CreateMenuItem("Visit program homepage","",self.OnHelpVisit)
        self.orderAction = CreateMenuItem("Order OBD-II interface","",self.OnHelpOrder)
        self.helpmenu.addAction(self.aboutAction)
        self.helpmenu.addAction(self.visitAction)
        self.helpmenu.addAction(self.orderAction)

        frame.show()
        frame.resize(520,400)
        self.sensor_control_off()

        return True

    def tabClicked(self, tabNum):
        if self.senprod is not None:
            if self.sensorTabs in self.nb.widget(tabNum).children():
                self.sensorTabClicked(self.sensorTabs.currentIndex())
            else:
                self.senprod.signals.sensorTabEvent.emit('None')

    def sensorTabClicked(self, tabNum):
        for sensorTable in self.sensorTables.values():
            if sensorTable is self.sensorTabs.widget(tabNum):
                self.senprod.signals.sensorTabEvent.emit(sensorTable.ecu)
                break
        else:
            self.senprod.signals.sensorTabEvent.emit('None')

    def setLoggingOptions(self):
        dialog = QDialog(self.frame)
        dialog.setWindowTitle('Set Logging Options')
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout()

        loglevelgroup = QGroupBox('Log Level')
        radio = {}
        radio[logging.DEBUG] = QRadioButton('Debug')
        radio[logging.INFO] = QRadioButton('Info')
        radio[logging.WARNING] = QRadioButton('Warning')
        radio[logging.ERROR] = QRadioButton('Error')
        radio[logging.CRITICAL] = QRadioButton('Critical')

        radio[self.logLevel].setChecked(True)
        loglevel_layout = QVBoxLayout()

        for loglevel in sorted(radio.keys()):
            loglevel_layout.addWidget(radio[loglevel])

        loglevelgroup.setLayout(loglevel_layout)
        layout.addWidget(loglevelgroup)

        def browseClick():
            filename = QFileDialog.getSaveFileName(caption='Select Log File...')[0]
            logfilename.setText(filename) 

        logfilegroup = QGroupBox('Log to File')
        logfilegroup.setCheckable(True)
        logfilegroup.setChecked(self.logToFile)
        logfilelayout = QHBoxLayout()
        logfilename = QLineEdit()
        logfilename.setText(self.logFile)
        logfilebrowse = QPushButton('...')
        logfilebrowse.clicked.connect(browseClick)
        logfilelayout.addWidget(logfilename)
        logfilelayout.addWidget(logfilebrowse,alignment=Qt.AlignRight)
        logfilegroup.setLayout(logfilelayout)
        layout.addWidget(logfilegroup)

        okButton = QPushButton('OK')
        cancelButton = QPushButton('Cancel')
        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)
        okButton.clicked.connect(dialog.accept)
        cancelButton.clicked.connect(dialog.reject)
        layout.addLayout(buttonLayout)

        dialog.setLayout(layout)
        r = dialog.exec()
        if r == QDialog.Accepted:
            for loglevel, radioButton in radio.items():
                if radioButton.isChecked():
                    self.logLevel = loglevel
                    self.config.set('pyOBD','LOGLEVEL',self.logLevel)
                    self.logger.setLevel(self.logLevel)
                    break

            newfilename = logfilename.text()

            if logfilegroup.isChecked():
                if not self.logToFile or self.logFile != newfilename:
                    try:
                        logFileHandler = logging.FileHandler(newfilename,'w')
                    except Exception as e:
                        self.logger.warning('Error opening log file: %s', str(e))
                    else:
                        if self.logToFile:
                            self.logger.removeHandler(self.logFileHandler)
                        self.logToFile = True
                        self.logFile = newfilename
                        self.logger.addHandler(logFileHandler)
                        self.logFileHandler = logFileHandler
                        self.config.set('pyOBD','LOGTOFILE',self.logToFile)
                        self.config.set('pyOBD','LOGFILE',self.logFile)
            else:
                if self.logToFile:
                    self.logger.debug('Removing log to file.')
                    self.logger.removeHandler(self.logFileHandler)
                    self.logToFile = False
                    self.config.set('pyOBD','LOGTOFILE',self.logToFile)

            self.write_config()

    def OnHelpVisit(self):
        webbrowser.open("http://www.obdtester.com/pyobd")

    def OnHelpOrder(self):
        webbrowser.open("http://www.obdtester.com/order")

    def OnHelpAbout(self): #todo about box
        Text = """<p>PyOBD is an automotive OBD2 diagnostic application that works with ELM23x cables.</p>

<p>(C) 2018-2019 Brian LePage<br>
(C) 2008-2009 SeCons Ltd.<br>
(C) 2004 Charles Donour Sizemore</p>

<p><a href='http://www.obdtester.com/'>http://www.obdtester.com/</a><br>
<a href='http://www.secons.com/'>http://www.secons.com/</a><br>
<a href='https://github.com/beardedone55/'>https://github.com/beardedone55/</a></p>

<p>PyOBD is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by the Free Software Foundation;
either version 2 of the License, or (at your option) any later version.</p>

<p>PyOBD is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.</p>

<p>You should have received a copy of the GNU General Public License along with PyOBD; if not, see <a href='https://www.gnu.org/licenses/'>https://www.gnu.org/licenses/.</a></p>
"""
        HelpAboutDlg = QMessageBox(QMessageBox.Information, 'About', Text, QMessageBox.Ok, self.frame)
        HelpAboutDlg.setTextFormat(Qt.RichText)
        HelpAboutDlg.exec()

    def OnResult(self,ecu,pid,column,data):
        if ecu in self.sensorTables:
            sensorTable = self.sensorTables[ecu]
            row = sensorTable.pid_lookup[str(pid)]
            sensorTable.item(row, column).setText(data)

    def OnStatus(self,event):
        if event[0] == 666: #signal, that connection falied
            self.sensor_control_off()
        else:
            self.status.item(event[0],event[1]).setText(event[2])

    def OnTests(self,event):
        self.OBDTests.addTableRow(3, event)

    def OnDtcClear(self, event):
        if event == 0:
            self.dtc.setRowCount(0)
        else:
            self.logger.warning('Unexpected OnDtcClear -> %d', event)

    def OnDtc(self,event):
        if len(event) == 1:
            alignment = Qt.AlignHCenter
            bold = True
        else:
            alignment = Qt.AlignLeft
            bold = False
        self.dtc.addTableRow(3, event, bold=bold, alignment=alignment)

    def OnDisconnect(self): #disconnect connection to ECU
        self.ThreadControl=666
        self.sensor_control_off()

    def OpenPort(self):
        self.nb.setCurrentWidget(self.status.parentWidget())
        self.OnStatus([0,1,"Connecting....."])
        self.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        self.stop()
        if self.senprod is not None:
            self.senprod.requestInterruption()
            self.senprod.wait()
        self.sensorTables = {}
        self.sensorTabs.clear()
        self.SensorProducerReady.connect(self.sensor_control_on)
        if self.initCommunication() == 'OK':
            self.senprod = self.sensorProducer(self)
            self.StatusEvent.emit([0,1,"Connected"])
            self.StatusEvent.emit([2,1,self.port.ELMver])
            self.StatusEvent.emit([1,1,self.port.protocol])
            for sensorTable in self.sensorTables.values():
                sensorTable.setSensorThread(self.senprod)
            self.senprod.start()
        else:
            self.StatusEvent.emit([0,1,"Connection Failed!!!!"])

        self.restoreOverrideCursor()

    def onTestDTC(self):
        self.DTCClearEvent.emit(0) #clear list
        self.DTCEvent.emit(['DTCs from Fake ECU'])
        self.DTCEvent.emit(['P0001', 'Active', 'Test DTC'])

    def GetDTC(self):
        self.DTCClearEvent.emit(0) #clear list
        DTCCodes=self.port.get_dtc()

        if DTCCodes is None: #Communication Issue
            self.OnDisconnect()

        for ecu in DTCCodes:
            self.DTCEvent.emit(['DTCs from ECU%d' % self.port.getEcuNum(ecu)])
            if len(DTCCodes[ecu]) == 0:
                self.DTCEvent.emit(["No DTC codes (codes cleared)"])
            for code in DTCCodes[ecu]:
                self.DTCEvent.emit([code[1],code[0],pcodes[code[1]]])

        self.nb.setCurrentWidget(self.DTCpanel.parentWidget())

    def CodeLookup(self):
        id = 0
        diag = QDialog(self.frame)
        diag.setWindowTitle('Diagnostic Trouble Codes')

        tree = QTreeWidget(diag)

        root = QTreeWidgetItem(tree)
        root.setText(0,"Code Reference")
        proot = root; # tree.AppendItem(root,"Powertrain (P) Codes")
        codes = sorted(pcodes.keys())
        group = ''
        for c in codes:
            if c[:3] != group:
                group_root = QTreeWidgetItem(proot)
                group_root.setText(0,c[:3]+"XX")
                proot.addChild(group_root)
                group = c[:3]
            leaf = QTreeWidgetItem(group_root)
            leaf.setText(0,c)
            group_root.addChild(leaf)
            codeText = QTreeWidgetItem(leaf)
            codeText.setText(0,pcodes[c])
            leaf.addChild(codeText)

        layout = QHBoxLayout(diag)
        layout.addWidget(tree)
        tree.header().hide()
        diag.setLayout(layout)
        diag.resize(400,500)
        diag.show()


    def QueryClear(self):
        id = 0
        diag = QMessageBox(QMessageBox.Question, 'Clear DTC?', \
            'Are you sure you wish to clear all DTC codes and freeze frame data?',\
            QMessageBox.Yes | QMessageBox.No, self.frame)

        r  = diag.exec()
        if r == QMessageBox.Yes:
            self.ClearDTC()

    def ClearDTC(self):
        self.port.clear_dtc()
        self.DTCClearEvent.emit(0) #clear list
        self.nb.setCurrentWidget(self.DTCpanel.parentWidget())


    def scanSerial(self):
        """Scan for available ports. Return a list of serial names"""
        available = []
        for portItem in serial.tools.list_ports.comports():
            available.append(portItem.device)
        return available

    def Configure(self):
        id = 0
        diag = QDialog(self.frame)
        diag.setWindowTitle("Configure")
        sizer = QFormLayout()

        ports = self.scanSerial()
        comportDropdown = QComboBox()
        comportDropdown.addItems(ports)
        sizer.addRow('Choose Serial Port: ', comportDropdown)

        #baudrates = ['9600', '19200', '28800', '38400', '48000', '115200']
        baudrates = [ ]
        baudrateDropdown = QComboBox()
        baudrateDropdown.addItems(baudrates)
        sizer.addRow('Choose Baud Rate: ', baudrateDropdown)

        #timeOut input control
        timeoutCtrl = self.MyNumberInput(str(self.SERTIMEOUT))
        sizer.addRow('Timeout:', timeoutCtrl)

        #reconnect attempt input control
        reconnectCtrl = self.MyNumberInput(str(self.RECONNATTEMPTS))
        sizer.addRow('Reconnect attempts:', reconnectCtrl)

        #set actual serial port choice
        if (self.COMPORT != 0) and (self.COMPORT in ports):
            comportDropdown.setCurrentIndex(ports.index(self.COMPORT))
        else:
            comportDropdown.setCurrentIndex(0)

        if comportDropdown.currentIndex() >= 0:
            try:
                for rate in serial.Serial(ports[comportDropdown.currentIndex()]).BAUDRATES:
                    if rate >=9600 and rate <=115200:
                        baudrates.append(str(rate))
            except serial.SerialException as e:
                self.logger.error('Could not retrieve baud rates from serial port: %s', str(e))

            baudrateDropdown.addItems(baudrates)

            if (self.BAUDRATE != 0) and (self.BAUDRATE in baudrates):
                baudrateDropdown.setCurrentIndex(baudrates.index(self.BAUDRATE))
            elif '38400' in baudrates:
                baudrateDropdown.setCurrentIndex(baudrates.index('38400'))
            else:
                baudrateDropdown.setCurrentIndex(0)

        okButton = QPushButton('OK')
        cancelButton = QPushButton('Cancel')
        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)
        okButton.clicked.connect(diag.accept)
        cancelButton.clicked.connect(diag.reject)
        sizer.addRow(buttonLayout)
        diag.setLayout(sizer)

        r  = diag.exec()

        if r == QDialog.Accepted and comportDropdown.currentIndex() >=0 and baudrateDropdown.currentIndex() >=0:

            #create section
            if self.config.sections()==[]:
                self.config.add_section("pyOBD")
            #set and save COMPORT
            self.COMPORT = ports[comportDropdown.currentIndex()]
            self.config.set("pyOBD","COMPORT",self.COMPORT)

            self.BAUDRATE = baudrates[baudrateDropdown.currentIndex()]
            self.config.set("pyOBD","BAUDRATE",self.BAUDRATE)

            #set and save SERTIMEOUT
            #If user enters a blank, it will remain unchanged
            try:
                self.SERTIMEOUT = int(timeoutCtrl.text())
            except:
                pass

            self.config.set("pyOBD","SERTIMEOUT",self.SERTIMEOUT)
            self.status.item(3,1).setText(self.COMPORT);

            #set and save RECONNATTEMPTS
            #If user enters a blank, it will remain unchanged
            try:
                self.RECONNATTEMPTS = int(reconnectCtrl.text())
            except ValueError:
                pass

            self.config.set("pyOBD","RECONNATTEMPTS",self.RECONNATTEMPTS)

            #write configuration to cfg file
            self.write_config()

    def exitCleanup(self):
        self.ThreadControl=666

    def OnExit(self):
        self.quit()
