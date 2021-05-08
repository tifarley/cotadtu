import sys
import time
import socket
import select
import struct
import json
import os

from CotaConfigEditor import CotaConfigEditor
from RemoteLogManager import RemoteLogManager
from AsyncCotaTxScanner import AsyncCotaTxScanner

from cmd_dicts import cmds, orion_cfg_params
from orion_json_cmds import jcd_orion
from venus_json_cmds import jcd_venus

class CotaTransmitter():
    SYSTEMSTATE = {
        "Venus": {
            0: "IDLE",
            1: "CALIBRATION",
            2: "WAITING FOR RX",
            3: "READY",
            4: "POWER CYCLE",
            5: "IDENTIFY TX",
            6: "RESERVED",
        },
        "Orion": {
            0: "IDLE",
            1: "CALIBRATION",
            2: "WAITING FOR RX",
            3: "READY",
            4: "POWER CYCLE",
            5: "IDENTIFY TX",
            6: "DEBUG", 
          127: "HOLD", 
          128: "ERROR", 
        }
    }

    QUERYTYPE = {
        5: "STANDARD",
        6: "CUSTOM",
        7: "OPTIMIZED"
    }

    CLIENTSTATUS = {
        "Venus": {
            0  : 'UNKNOWN',
            1  : 'NOT_REGISTERED',
            2  : 'NOT_READY',
            3  : 'POWER_NOT_REQUESTED',
            4  : 'NOT_CHARGING',
            5  : 'CHARGING',
            6  : 'LIMITED_CHARGING',
            7  : 'PAUSED',
            8  : 'SYSTEM_ERROR',
            9  : 'COMM_ERROR',
            10 : 'NOT DETECTED',
        },
        "Orion": {
            0  : 'UNKNOWN',
            1  : 'READY',
            2  : 'CHARGING',
            3  : 'DISCOVERY',
            4  : 'REGISTERED',
            5  : 'JOINED',
            6  : 'SILENT',
            7  : 'DISCONNECT',
        }
    }

    """ Loads JSON command dict based on system type
    System type is determined automatically upon connect
    """
    SYSTEMTYPE = {
        "Venus" : jcd_venus,
        "Mars"  : jcd_venus,
        "Orion" : jcd_orion,
    }

    """ Convert demo client details to ESL client details
    Also adds units where applicable
    """
    lpm_keys =   {
        'Status':           'Status',
        'TPSMissed':        'TPSMissed',
        'BatteryLevel':     'Cap Level (%)',
        'PeakPower':        'Number of Slots',
        'NetCurrent':       'Cap Voltage (mV)',
        'RSSIValue':        'RSSIValue (dBm)',
        'ProxyRSSIValue':   'ProxyRSSIValue (dBm)',
        'ProxyLinkQuality': 'ProxyLinkQuality',
        'QueryFailedCount': 'QueryFailedCount',
    }

    """ Add units to demo client details
    """
    recv_keys_venus = {
        'AveragePower':   'AveragePower (dBm)',
        'BatteryLevel':   'BatteryLevel (%)',
        'NetCurrent':     'NetCurrent (mA)',
        'PeakPower':      'PeakPower (dBm)',
        'ProxyRSSIValue': 'ProxyRSSIValue (dBm)',
        'RSSIValue':      'RSSIValue (dBm)',
    }
    recv_keys_orion = {
        'Avg Power':     'Average Power (dBm)',
        'Battery Level': 'BatteryLevel (%)',
        'Net Current':   'Net Current (mA)',
        'Peak Power':    'Peak Power (dBm)',
        'Comm RSSI':     'Comm RSSI (dBm)',
    }


    """ Text representation of select client commands
    Also used to populate the dropdown menu
    """
    rx_cmd_list = {
        "Blink Receiver LED":    1,
        "Control USB power":    47,
        "CW Beacon":            29,
        "Discharge Batt to %":  51,
        "Firmware Version":     61,
        "Force Watchdog":       52,
        "Get Beacon Frequency": 10,
        "Get COM Channel":      11,
        "Harvest Power":        58,
        "Ping Receiver":         0,
        "Read Watchdog":        20,
        "Reset Receiver":        3,
        "Set Beacon Frequency": 82,
        "Set COM Channel":      15,
        "Sleep Receiver":        2,
    }

    """ Advanced debug commands for Orion systems
    Also used to populate the transmitter listbox
    """
    debug_cmds_orion = {
        "Charge Virtual"      : "charge_virtual",
        "Fans Full"           : "set_fans_full",
        "Pause"               : "pause",
        "Reboot All"          : "reboot",
        "Reset Array"         : "reset_array",
        "Reset NVM"           : "reset_nvm",
        "Reset Proxy"         : "reset_proxy",
        "Restart Host MCU"    : "reset_host",
        "RSSI Filter Enable"  : "set_rssi_filter_en",
        "Run"                 : "run",
        "Sample Beacon"       : "sample_beacon",
        "Send Discovery"      : "send_disc",
        "Set TX Frequency"    : "set_tx_freq",
        "Shutdown"            : "shutdown",
        "Static Charge"       : "static_charge",
        "Static Power"        : "static_power",
    }

    """ Advanced debug commands for Venus systems
    Also used to populate the transmitter listbox
    """
    debug_cmds_venus = {
        "Add Client"    : "add_client",
        "Pause"         : "pause",
        "Reboot CCB"    : "reboot",
        "Reset Array"   : "reset_array",
        "Reset FPGA"    : "reset_fpga",
        "Reset Proxy"   : "reset_proxy",
        "Restart Daemon": "restart",
        "Run"           : "run",
        "Send Discovery": "send_disc",
        "Shutdown"      : "shutdown",
    }

    def __init__(self):
        """Initialize an instance of CotaTransmitter
        """
        self.sock = None
        self.is_connected = False
        self.lpm_mode = False
        self.lpm_whitelist = {}
        self.sysinfo = {}
        self.system_type = None
        self.cfg_params = {}
        self.log_man = RemoteLogManager()

    def get_system_type(self):
        """ Sends a Venus/Mars only command and checks the response
        This is extremely hacky and seems unreliable, needs work!
        """
        test_type_recv = self.send_recv("GetVersion")
        if 'Version' in test_type_recv.get('Result', {}):
            self.set_system_type('Orion')            
        else:
            self.set_system_type('Venus')

    def set_system_type(self, system_type):
        """Sets the system type

        system_type can be "Venus", "Mars", or "Orion"
        """
        if system_type not in CotaTransmitter.SYSTEMTYPE:
            raise ValueError("Invalid transmitter type")
        self.system_type = system_type
        self.json_cmd_dict = CotaTransmitter.SYSTEMTYPE.get(system_type)

    def check_lpm_mode(self):
        # TODO: Check for LPM on Orion
        if self.system_type == "Orion":
            self.lpm_mode = True
            return self.lpm_mode
        # Try reading the LPM list to determine if LPM mode is enabled
        recv = self.send_recv('lpm_list')
        try:
            numslots = len((recv.get('Result', []).get('Slots', [])))
        except:
            numslots = 0
        self.lpm_mode = numslots > 0
        return self.lpm_mode

    def send_recv(self, cmd, **kwargs):
        """Build and send a JSON command to the message manager

        Required argument is the command to
        Optional: keyword arguments corresponding to addition command
        details to send with the command
        """
        raw_recv = b''
        recv = {"Status":"TIMEOUT"}
        if self.is_connected is False:
            return "Not Connected"
        if cmd == 'GetVersion':
            data = {"Command":{"Type":cmd}, "Result" : {}}
        elif cmd not in self.json_cmd_dict:
            return {"Status":"INVALID CMD"}
        else:
            cmd_str = self.json_cmd_dict[cmd].get('jstr', None)
            defaults = self.json_cmd_dict[cmd].get('NotSet', [])
            if not isinstance(defaults, list):
                defaults = [defaults]
            if cmd_str is None:
                return
            if cmd_str.count('%s') == 0:
                data = json.loads(cmd_str)
            else:
                if 'user_params' in kwargs.keys():
                    user_args = kwargs.get('user_params', []).split()
                    if cmd_str.count('%s') == len(user_args):
                        args = user_args
                    else:
                        args = defaults
                else:
                    if cmd_str.count('%s') == len(kwargs.values()):
                        args = kwargs.values()
                    else:
                        args = defaults
                data = json.loads(cmd_str % tuple(args))
        end_time = time.time() + 5
        while time.time() <= end_time:
            try:
                sock_read, sock_write, sock_except = select.select([self.sock], [self.sock], [self.sock])
            except Exception as e:
                return {"Status":"Socket Error - {}".format(e)}
            if self.sock in sock_write:
                try:
                    self.sock.sendall(json.dumps(data).encode())
                except Exception as e:
                    return {"Status":"Socket Send Error - {}".format(e)}
                else:
                    break
            elif self.sock in sock_except:
                self.is_connected = False
                return {"Status":"Socket Select Exception"}
        end_time = time.time() + 5
        while time.time() <= end_time:
            sock_read, sock_write, sock_except = select.select([self.sock], [self.sock], [self.sock])
            if self.sock in sock_read:
                raw_recv += self.sock.recv(32768)
                try:
                    recv = json.loads(raw_recv.decode())
                except ValueError:
                    # This means the data received is not valid JSON. Ignore it and loop again
                    # in order to read the rest of the data
                    pass
                else:
                    # The data is now valid JSON and can be decoded
                    break
            elif self.sock in sock_except:
                self.is_connected = False
                return {"Status":"Socket Select Exception"}
        return recv

    def decode_status(self, val):
        status = ''
        if val & 1 != 0:
            status += 'POWER_REQ'
        else:
            status += 'POWER_NOT_REQ'

        return status

    def connect(self, hostname, port=50000):
        self.is_connected = False
        self.hostname = hostname
        self.port = port
        self.sysinfo = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5.0)
        try:
            self.sock.connect((
                socket.gethostbyname(self.hostname),
                self.port
            ))
            self.sock.setblocking(0)
            self.is_connected = True
        except Exception as e:
            return False
        else:
            self.get_system_type()
            self.check_lpm_mode()
        return self.is_connected

    def disconnect(self):
        if self.sock == None:
            return 'SUCCESS'
        try:
            self.sock.close()
            self.is_connected = False
            return 'SUCCESS'
        except Exception as e:
            return e

    def get_sysinfo(self):
        try:
            self.sysinfo['COMM Channel'] = self.get_comm_channel()
            self.sysinfo['Power Frequency (MHz)'] = self.get_tx_freq()
            self.sysinfo['Temperature (C)'] = self.get_system_temp()
            self.sysinfo['Valid AMBs'] = self.get_valid_ambs()
            self.sysinfo['Power Level (dBm)'] = self.get_power_level()
            self.sysinfo['State'] = self.get_system_state()
        except Exception as e:
            return str(e)

        # Only get SW versions once
        if self.sysinfo.get('Code Version', None) is None:
            sw_vers = self.get_tx_firmware()

        return self.sysinfo
    
    def get_comm_channel(self):
        com_channel = self.send_recv(
            'get_comm_channel'
            ).get("Result", {}
            ).get("COM Channel", "Error")
        return com_channel
    
    def get_tx_freq(self):
        tx_freq = self.send_recv(
            'get_tx_freq'
            ).get("Result", {}
            ).get("Tx Freq", "Error")
        if tx_freq == '0':
            comm_chan = self.sysinfo.get('COMM Channel', '0')
            if comm_chan != '0':
                tx_freq = {
                    '24': '2460',
                    '25': '2450',
                    '26': '2440',
                }.get(comm_chan, 'Error')
        return tx_freq

    def get_system_temp(self):
        raw_temp = self.send_recv(
            'get_system_temp'
            ).get("Result", {}
        )
        if self.system_type == "Orion":
            amb_keys = ['AMB0', 'AMB1', 'AMB2', 'AMB3']
            try:
                sys_temp = ', '.join([raw_temp.get(t).split()[0] for t in amb_keys])
            except:
                sys_temp = 'Error'
        else:
            sys_temp = raw_temp.get("Temp", "Error")
        return sys_temp

    def get_valid_ambs(self):
        if self.system_type == "Orion":
            key = "Valid Ambs"
        else:
            key = "Good Channels"
        good_channels = self.send_recv(
            'get_valid_amb_mask'
            ).get("Result", {}
            ).get(key, "Error")
        return good_channels

    def get_power_level(self):
        power_level = self.send_recv(
            'get_power_level'
            ).get("Result", {}
            ).get("PowerLevel", "Error")
        return power_level

    def get_system_state(self):
        if self.system_type == "Orion":
            key = "System State"
        else:
            key = "State"
        sys_state = self.send_recv(
            'get_system_state'
            ).get("Result", {}
            ).get(key, "Error")
        if self.system_type == "Orion":
            try:
                sys_state = int(sys_state.split()[0])
            except Exception as e:
                sys_state = 0
        return self.SYSTEMSTATE[self.system_type].get(sys_state, "UNKNOWN")

    def get_proxy_info(self):
        pass

    def get_tx_firmware(self):
        sw_vers = self.send_recv('versions').get('Result', 'Error')
        if type(sw_vers) == dict:
            if self.system_type == "Orion":
                for key in sw_vers.keys():
                    if key == 'OS Version':
                        self.sysinfo['OS Type'] = sw_vers[key].get('OS name')
                        self.sysinfo['Hostname'] = sw_vers[key].get('Host name')
                        self.sysinfo['Kernel'] = sw_vers[key].get('Kernel ver')
                    else:
                        self.sysinfo[key] = sw_vers.get(key)
            else:
                self.sysinfo['Release Version'] = '.'.join(
                    [str(x) for x in list(
                        sw_vers['Release Version'].to_bytes(4, 'big'))
                ])
                self.sysinfo['FPGA Revision'] = '.'.join(
                    [str(x) for x in list(
                        sw_vers['FPGA Revision'].to_bytes(2, 'big'))
                ])
                self.sysinfo['Proxy FW Revision'] = '.'.join(
                    [str(x) for x in list(
                        sw_vers['Proxy FW Revision'].to_bytes(2, 'big'))
                ])
        return sw_vers

    def get_rx_list(self):
        sorted_list = []
        rx_status_dict = self.CLIENTSTATUS[self.system_type]
        if self.system_type == "Orion":
            rx_name = "Receivers"
            id_name = "RX ID"
        else:
            rx_name = "Clients"
            id_name = "Client ID"
        recv = self.send_recv('rx_list')
        rx_list = recv.get('Result', []).get(rx_name,[])
        if len(rx_list) > 0:
            try:
                sorted_list = sorted(rx_list, key = lambda c: c[id_name])
            except:
                sorted_list = rx_list
            for c in sorted_list:
                if self.system_type == "Orion":
                    try:
                        client_state_num = int(
                            c['State'].split()[0]
                        )
                    except:
                        client_state_num = 0
                    c['Status'] = rx_status_dict.get(client_state_num, "Unknown")
                    c['LinkQuality'] = c.get('Link Quality', 0)
                else:
                    c['Status'] = rx_status_dict.get(c['Status'], "Unknown")
        self.rx_list = sorted_list
        return self.rx_list

    def get_lpm_list(self):
        sorted_list = {}
        recv = self.send_recv('lpm_list')
        # TODO: remove before merge
        print('lpm_list', recv)
        if 'Slots' in recv.get('Result', {}):
            lpm_data = recv['Result']['Slots'][1:]
            # First element is None, remove it
            if len(lpm_data) > 0:
                for c in lpm_data:
                    c['Short ID'] = int(c['Short ID'])
                sorted_list = sorted(lpm_data, key = lambda c: int(c['Short ID']))
            self.lpm_list = sorted_list
            return self.lpm_list

    def get_rx_detail(self, clientid):
        self.selected_client = clientid
        self.client_details = {}
        temp_details = {}
        ignore_keys = [
            'Status',
            'Status Flags',
        ]
        recv = self.send_recv(
            'rx_detail',
            clientid=clientid
        )
        r = recv.get('Result', {})
        if self.system_type == "Orion":
            r.pop('Status', None)
        for key, val in r.items():
            if key == "Status":
                val = self.CLIENTSTATUS[self.system_type].get(val, "UNKNOWN")
            elif key == "QueryTime": # Venus
                val = time.strftime('%H:%M:%S', time.gmtime(val))
            elif key == "Model":
                if self.system_type != "Orion":
                    val = hex(val).split('0x')[1].upper()
            elif key == "DeviceStatus":
                val = self.decode_status(val)
            elif key == "Custom App Data":
                val = ''.join(eval(val))
            if self.system_type == "Orion":
                if key == 'State':
                    try:
                        val = val.split(' ')[1]
                    except:
                        val = val
                elif key == 'Status Flags':
                    for status_key, status_val in r.get(key).items():
                        temp_details[status_key] = status_val
                elif key in self.recv_keys_orion:
                    key = self.recv_keys_orion[key]
            else:
                if key in self.recv_keys_venus:
                    key = self.recv_keys_venus[key]
            if val == 255:
                val = -1
            if key not in ignore_keys:
                temp_details[key] = val

        #for key in sorted(temp_details.keys()):
        for key in temp_details.keys():
            self.client_details[key] = temp_details.get(key, '')

        return self.client_details

    def lpm_client_detail(self, clientid):
        self.client_details = {}
        recv = self.send_recv(
            client_detail,
            clientid=clientid
        )
        for key, val in recv['Result'].items():
            if key == "Status":
                val = self.CLIENTSTATUS[self.system_type].get(val, 'UNKNOWN')
            elif key == "DeviceStatus":
                val = bin(val)
            elif key == "QueryTime":
                val = time.strftime('%H:%M:%S', time.gmtime(val))
            elif key == "QueryType":
                val = self.QUERYTYPE.get(val, "UNKNOWN")
            elif key == "Model":
                val = hex(val).split('0x')[1].upper()
            if key in self.lpm_keys:
                key = self.lpm_keys[key]
                self.client_details[key] = val
        return self.client_details

    def set_comm_channel(self, newval):
        if newval.isdigit():
            if int(newval) > 12 and int(newval) < 27:
                r = self.send_recv(
                    'set_comm_channel',
                    comchan=int(newval),
                    clientid=0 #TODO allow changing client channel at the same time
                )
                return r.get('Result', []).get('Status', 'No Status')

    def set_valid_ambs(self, newval):
        if "0x" in newval:
            r = self.send_recv(
                'set_valid_amb_mask',
                goodchan=newval
            )
            return r.get('Result', []).get('Status', 'No Status')

    def set_power_lvl(self, newval):
        if newval.isdigit():
            r = self.send_recv(
                'set_power_level',
                pwr=newval
            )
            return r.get('Result', []).get('Status', 'No Status')

    def send_discovery(self, chan):
        if chan.isdigit():
            if int(chan) > 1 and int(chan) < 27:
                r = self.send_recv(
                    'send_disc',
                    comchan=chan
                )
            return r.get('Result', []).get('Status', 'No Status')

    def sys_cmd(self, cmd, data=None):
        # These are the buttons in the main window
        sys_cmds = {
            'Calibrate'            : 'calibrate',
            'Identify Transmitter' : 'identify_tx',
            'Shutdown'             : 'shutdown'
        }
        if cmd in sys_cmds:
            if cmd == 'Calibrate':
                # Sometimes calibration freezes the MM interface
                # Increase the timeout to prevent errors
                self.sock.settimeout(30.0)
                r = self.send_recv(sys_cmds[cmd])
                self.sock.settimeout(5.0)
            elif cmd == 'Shutdown':
                r = self.send_recv(sys_cmds[cmd])
                self.is_connected = False
            else:
                r = self.send_recv(sys_cmds[cmd])
        # System specific commands
        elif self.system_type == "Orion":
            if cmd in self.debug_cmds_orion:
                if data is not None:
                    r = self.send_recv(self.debug_cmds_orion[cmd], user_params=data)
                else:
                    r = self.send_recv(self.debug_cmds_orion[cmd])
        elif self.system_type == "Venus":
            if cmd in self.debug_cmds_venus:
                if data is None:
                    r = self.send_recv(self.debug_cmds_venus[cmd])
                else:
                    r = self.send_recv(self.debug_cmds_venus[cmd], data=data)
        try:
            result = r.get('Result', []).get('Status', 'No Status')
        except Exception as e:
            if cmd == 'Reboot All':
                result = 'SUCCESS'
            else:
                result = 'ERROR'
        return result

    def register_rx(self, clientid):
        r = self.send_recv(
            'register_rx',
            clientid=clientid,
            querytype=5
        )
        return r.get('Result', []).get('Status', 'No Status')

    def unregister_rx(self, clientid):
        r = self.send_recv(
            'remove_rx',
            clientid=clientid
        )
        return r.get('Result', []).get('Status', 'No Status')

    def remove_rx(self, clientid):
        r = self.send_recv(
            'rx_leave',
            clientid=clientid
        )
        return r.get('Result', []).get('Status', 'No Status')

    def rx_sleep(self, clientid):
        r = self.send_recv(
            'rx_sleep',
            clientid=clientid
            )
        return r.get('Result', []).get('Status', 'No Status')

    def start_charging(self, clientid):
        r = self.send_recv(
            'start_charging',
            devices=clientid
        )
        return r.get('Result', []).get('Status', 'No Status')

    def stop_charging(self, clientid):
        r = self.send_recv(
            'stop_charging',
            devices=clientid
        )
        return r.get('Result', []).get('Status', 'No Status')

    def rx_config(self, clientid, querytype):
        r = self.send_recv(
            'rx_config',
            devices=clientid,
            querytype=querytype,
        )
        return r.get('Result', []).get('Status', 'No Status')

    def app_cmd(self, clientid, cmd, data):
        if cmd in self.rx_cmd_list:
            if self.system_type == "Orion":
                if data is None or data == '':
                    data = '[]'
                r = self.send_recv(
                    'app_command',
                    clientid=clientid,
                    appcmd=self.rx_cmd_list[cmd],
                    data=data,
                )
            else:
                cmddata = []
                cmddata.append(self.rx_cmd_list[cmd])
                if data is not None and data != '':
                    cmddata.append(int(data))
                format_data = ','.join(map(str, cmddata))
                r = self.send_recv(
                    'app_command',
                    clientid=clientid,
                    data=format_data,
                )
            return r.get('Result', []).get('Status', 'No Status')

    def app_command_data(self, clientid, client_cmd):
        r = self.send_recv(
            'app_command_data',
            clientid=clientid
        )
        try:
            if self.system_type == "Orion":
                try:
                    status = r['Result']['Values'][1]['Data'].split()
                except:
                    return "NO DATA"
                if client_cmd == "Get COM Channel":
                    try:
                        # In newer B4 FW, a header block was added which shifted
                        # the COMM channel from the 1st to the 4th byte
                        # The first byte is now the number of bytes in NVM
                        # As long as this number stays < 11 (the first valid channel)
                        # this logic will work
                        first_byte = int(status[0], 16)
                        if first_byte < 11:
                            first_byte = int(status[3], 16)
                        data = first_byte
                    except:
                        return "NO DATA"
                elif client_cmd == "Firmware Version":
                    data = "0x" + "".join(
                        [x.replace('0x', '') for x in status[0:4][::-1]]
                    )
                elif client_cmd == "Read Watchdog":
                    data = f'{status[5]}, {status[6]}'
                elif client_cmd == "Set Beacon Frequency":
                    data = f'{(int(status[1], 16) << 8) + int(status[0], 16)}'
                elif client_cmd == "Get Beacon Frequency":
                    try:
                        freq_bytes = ' '.join(x[2:] for  x in status[0:4])
                        freq_bytes = bytearray.fromhex(freq_bytes)
                        data = round(struct.unpack('<L',freq_bytes)[0] / 1e6)
                    except:
                        pass
                else:
                    data = " ".join(status[0:8])
                return data
            else:
                status = r["Result"]["Data"]
                if client_cmd == "Get COM Channel":
                    data = status[1]
                elif client_cmd == "Firmware Version":
                    data = "0x" + "".join(
                        [hex(x).strip('0x') for x in status[1:][::-1]]
                    )
                elif client_cmd == "Read Watchdog":
                    data = str(status[6]) + ", " + str(status[7])
                else:
                    data = " ".join([hex(x) for x in status[1:8]])
                return data
        except:
            return "NO DATA"

    def lpm_assign(self, clientid, slot):
        result = ''
        startTime = time.time()
        endTime = startTime + 10
        while result != 'SUCCESS' and time.time() <= endTime:
            r = self.send_recv(
                'lpm_assign',
                clientid=clientid,
                slot=slot
            )
            result = r.get('Result', []).get('Status', '')
        return result

    def lpm_remove(self, slot):
        resultLpm = ''
        startTime = time.time()
        endTime = startTime + 5
        while resultLpm != 'SUCCESS' and time.time() <= endTime:
            r = self.send_recv(
                'lpm_free',
                slot=slot
            )
            resultLpm = r.get('Result', []).get('Status', '')
        return resultLpm

    def set_rx_lpm(self, clientid):
        resultLpm = ''
        startTime = time.time()
        endTime = startTime + 10
        while resultLpm != 'SUCCESS' and time.time() <= endTime:
            r = self.send_recv(
                'app_command',
                clientid=clientid,
                cmd=81,
                data=["1"]
            )
            resultLpm = r.get('Result', []).get('Status', '')
        return resultLpm

    def set_rx_lpm_standby(self, clientid):
        resultSleep = ''
        startTime = time.time()
        endTime = startTime + 10
        time.sleep(0.5)
        while resultSleep != 'SUCCESS' and time.time() <= endTime:
            r = self.send_recv(
                'app_command',
                clientid=clientid,
                cmd=87,
                data=[]
            )
            resultSleep = r.get('Result', []).get('Status', '')
        return resultSleep

    def set_lpm_slots(self, slots):
        r = self.send_recv(
            'lpm_slots',
            slots=slots
        )
        return r.get('Result', []).get('Status', 'No Status')

    def set_rx_screen_update(self, clientid, updTime):
        r = self.send_recv(
            'app_command',
            clientid=clientid,
            data=[86,int(updTime)]
        )
        return r.get('Result', []).get('Status', 'No Status')

    def set_tile_lpm(self, state="on"):
        r = self.send_recv(
            'lpm',
            state=state
        )
        return r.get('Result', []).get('Status', 'No Status')

    def get_amb_info(self):
        r = self.send_recv('get_valid_ambs')
        return r.get('Result', [])

    def identify_rx(self, clientid):
        r = self.send_recv(
            'identify_rx',
            clientid=clientid,
            time=10
        )
        return r.get('Result', []).get('Status', 'No Status')

    def get_tx_id(self):
        r = self.send_recv('get_tx_id')
        return r.get('Result', []).get('ChargerId', 'Unknown')

    def get_all_config(self):
        ''' Get system configuration
        If tile is Venus/Mars system, download the Cota Config
        If tile is Orion, get all config params stored in NVM
        '''
        if self.system_type == "Orion":
            return self.get_all_cfg_params()
        else:
            self.ce = CotaConfigEditor()
            try:
                self.ce.ConnectSsh(self.hostname)
            except:
                return 'CONFIG ERROR'
            else:
                self.ce.DownloadConfig()
                self.ce.DisconnectSsh()
                return 'SUCCESS'    

    def save_all_config(self):
        ''' Save system configuration
        If tile is Venus/Mars system, upload new Cota Config
        If tile is Orion, ???
        '''
        if self.system_type == "Venus":
            try:
                self.ce.ConnectSsh(self.hostname)
            except:
                return 'SAVE ERROR'
            else:
                self.ce.UploadConfig()
                self.ce.DisconnectSsh()
                return 'SUCCESS'

        elif self.system_type == "Orion":
            # Params are saved as soon as they are set in Orion
            pass

    def get_all_cfg_params(self):
        self.cfg_params = {}
        try:
            for param in orion_cfg_params.values():
                self.get_cfg_param(param)
        except Exception as e:
            return repr(e)
        return 'SUCCESS'

    def get_cfg_param(self, param):
        r = self.send_recv(
            'get_cfg_param',
            cfg_param=param
        )
        cfg_val = r.get('Result', []).get('Value', 'Unknown')
        if cfg_val != 'Unknown':
            self.cfg_params[param] = cfg_val
            return 'SUCCESS'
        return 'ERROR'

    def set_cfg_param(self, param, value):
        r = self.send_recv(
            'set_cfg_param',
            cfg_param=param,
            cfg_value=value
        )
        return r.get('Result', []).get('Status', 'No Status')

    def charge_virtual(self):
        r = self.send_recv('charge_virtual')
        return r.get('Result', []).get('Status', 'No Status')

    def reset_host(self):
        r = self.send_recv(
            'reset_host', hold='0.5', block='1.0'
        )
        return r.get('Result', []).get('Status', 'No Status')

    def search_for_tx(self, loop):
        host_list = []
        try:
            scanner = AsyncCotaTxScanner(loop, 50000, 2)
            scanner.get_host_addresses()
            scanner.execute()
            for host in scanner.results:
                try:
                    hostname = socket.gethostbyaddr(host)[0]
                except:
                    hostname = host
                host_list.append(hostname)
        except Exception as e:
            return f'ERROR: {e}'
        else:
            # scanner.close_loop()
            return host_list

    def connect_logman(self, username, password):
        self.log_man.set_config(
            self.hostname, 
            self.system_type,
            username, 
            password)
        default_port = self.log_man.port
        if self.system_type == 'Venus':
            try:
                self.log_man.connect(port=default_port)
            except Exception as e:
                try:
                    self.log_man.connect(port=22)
                except Exception as e:
                    return f'ERROR: {e}'
        else:
            try:
                self.log_man.connect(port=default_port)
            except Exception as e:
                return f'ERROR: {e}'
        return 'SSH CONNECTED'

    def list_logs(self):
        files = self.log_man.list_files()
        return files

    def download_log(self, localfile, remotefile):
        try:
            ret = self.log_man.download_file(localfile, remotefile)
        except Exception as e:
            ret = f'ERROR: {e}'
        return ret

    def delete_log(self, remotefile):
        try:
            ret = self.log_man.delete_file(remotefile)
        except Exception as e:
            ret = f'ERROR: {e}'
        return ret
    
    def start_logging(self, rx_list, hours_to_log, log_interval):
        try:
            status = self.log_man.start_logging(
                rx_list,
                hours_to_log,
                log_interval
            )
        except Exception as e:
            return f'ERROR: {e}'
        else:
            if status == 0:
                return 'LOG STARTED'
            else:
                return f'ERROR: {status}'
    
    def stop_logging(self):
        try:
            status = self.log_man.stop_logging()
        except Exception as e:
            return f'ERROR: {e}'
        else:
            if status == 0:
                return 'LOG ENDED'
            else:
                return f'ERROR: {status} (no running log)'
    
    def get_mcu_log(self, num_entries):
        r = self.send_recv(
            'get_mcu_log',
            num_entries=num_entries,
            file='mcu'
        )
        entries = r.get('Result', []).get('Entries', [])
        if len(entries) < 1:
            entries = ['No log entries']
        return entries
