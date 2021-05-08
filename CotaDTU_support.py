import sys
import time
import socket
import json
import os
import math
import hashlib
import subprocess
import queue
import threading
import webbrowser
import asyncio

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import simpledialog, filedialog, messagebox
py3 = True

from CotaTransmitter import CotaTransmitter
from CotaConfigEditor import CotaConfigEditor
from CotaMsgHandler import create_msg, CotaMsgHandler
from cmd_dicts import cmds, orion_cfg_params
from LogPlottingGUI import create_Plot_Data_GUI
from LpmAutoAssign import LpmAutoAssign

data_queue = queue.Queue(maxsize=50)
cmd_queue = queue.Queue(maxsize=50)
ct = CotaTransmitter()
ce = CotaConfigEditor()
msg_handler = CotaMsgHandler(cmd_queue, data_queue, ct)
lpm_assign_stop = threading.Event()

DTU_VERSION = "1.2.4"
AUTO_UPDATE_PERIOD = 10000

def connect(e=None):
    w.menubar.entryconfig("Edit", state="disabled")
    if root._job is not None:
        root.after_cancel(root._job)
        root._job = None

    hostname = w.hostEntry.get()
    host_list = list(w.hostEntry['values'])
    if hostname not in host_list:
        host_list.append(hostname)
    w.hostEntry['values'] = tuple(host_list)
    if hostname == "":
        return
    cmd_queue.put(create_msg('CONNECT', (hostname,)))

    trees = [
        w.clientDetailTree,
        w.clientListTree,
        w.sysinfoTree,
        w.lpmRxDetailTree,
        w.lpmRxListTree,
        w.lpmSlotListTree,
        w.cotaConfigTree,
        w.logfileTree,
    ]

    listboxes = [
        w.advancedTxList,
        w.advancedRxList,
    ]
    for tree in trees:
        clear_tree(tree)

    for listbox in listboxes:
        listbox.delete(0,"end")
    update_status('CONNECTING')
    update_ssh_status('')
    if ct.log_man.connected:
        ct.log_man.connected = False

def connect_ssh():
    ssh_username = simpledialog.askstring('Username', 'Enter SSH username:')
    ssh_passwd = simpledialog.askstring('Password', 'Enter SSH password:', show='*')
    if ssh_username in ['', None] or ssh_passwd in ['', None]:
        update_status('CANCELLED')
        return

    cmd_queue.put(create_msg('CONNECT_LOG', (ssh_username, ssh_passwd)))
    update_ssh_status('CONNECTING')

def search_for_tx():
    loop = asyncio.get_event_loop()
    cmd_queue.put(create_msg('SEARCH_FOR_TX', (loop,)))
    update_status('SEARCHING')

def populate_tx_list(tx_list):
    num_found = 0
    if not isinstance(tx_list, list):
        update_status(tx_list)
        return

    if len(tx_list) > 0:
        tx_list.sort()
        w.hostEntry['values'] = tuple(tx_list)
        w.hostEntry.current(0)
        num_found = len(tx_list)
    update_status(f'{num_found} transmitters found')

def on_connect(connected):
    update_status(connected)
    if not connected:
        root._job = None
        return

    system_type = ct.system_type
    if system_type == "Orion":
        w.advancedTxList.insert("end", *ct.debug_cmds_orion.keys())
    else:
        w.advancedTxList.insert("end", *ct.debug_cmds_venus.keys())

    w.advancedRxList.insert("end", *ct.rx_cmd_list.keys())

    tabs = w.CotaNotebook.tabs()
    for t in tabs:
        title = w.CotaNotebook.tab(t, "text")
        if title == "ESL" and ct.lpm_mode is True:
            w.CotaNotebook.add(t)
        elif title == "ESL" and ct.lpm_mode is False:
            w.CotaNotebook.hide(t)
        # TODO remove this before release
        elif title == "Debug":
            w.CotaNotebook.add(t)

    w.menubar.entryconfig("Edit", state="normal")
    w.CotaNotebook.bind('<<NotebookTabChanged>>',lambda e:switch_tabs(e))
    w.clientListTree.bind('<Button-3>',lambda e:client_popup(e))
    w.lpmSlotListTree.bind('<Button-3>',lambda e:lpm_slot_popup(e))
    auto_update()

def display_help_file():
    filename = os.path.realpath('cotadtu_help.pdf')
    if os.path.exists(filename):
        try:
            webbrowser.open(filename, new=2) # Open in a new tab
        except:
            messagebox.showerror('Error', 'Error opening help file')
    else:
        messagebox.showerror('Error', 'Help file not found')

def checkpassword(passwd):
    # Example generation
    # salt = os.urandom(32)
    # key = hashlib.pbkdf2_hmac('sha256', 'mypassword'.encode('utf-8'), salt, 100000)

    # Store them as:
    # storage = salt + key 
    stored_key = b''.join([
        b'\xde\xc1\x19\xa8\xb9\xe7\xfe\xeb<\x8b\xa6\x176\x9d',
        b'\xc6~\x1c\xba\xbbE\xe2)\xfaZW\xc5Xl\x0cmtEV\xc3\x8a',
        b'\x8a\xf2\x82\xe1\xd2%\x16f\xaa\x94Q\x84\xf4\xb2\x12',
        b'\x85\xb2\xcf0\xf0\r\x0cVI]c\xb4\xfb\x9c'
    ])
    stored_salt = stored_key[:32]
    new_key = hashlib.pbkdf2_hmac(
        'sha256',
        passwd.encode('utf-8'),
        stored_salt, 
        100000
    )

    if stored_salt+new_key == stored_key:
        return True
    else:
        return False

def update_status(status):
    if type(status) == int:
        status = ct.CLIENTSTATUS.get(status, "UNKNOWN")
    elif status is None:
        status = 'No Status'
    elif status is True:
        status = 'SUCCESS'
    elif status is False:
        status = 'ERROR'
    w.lastStatusEntry.delete(0, 'end')
    w.lastStatusEntry.insert('end', status)

def update_ssh_status(status):
    w.sshRespEntry.delete(0, 'end')
    w.sshRespEntry.insert('end', status)

def set_upd_interval():
    global AUTO_UPDATE_PERIOD
    upd = simpledialog.askinteger("Update interval (s)", "Enter new value",
                            initialvalue=int(AUTO_UPDATE_PERIOD/1000))
    if upd is not None:
        AUTO_UPDATE_PERIOD = upd * 1000

def enable_debug_tab():
    entered_passwd = simpledialog.askstring(
                "Enable Debugging",
                "Enter password",
                show='*')
    if entered_passwd is None:
        return
    if not checkpassword(entered_passwd):
        update_status('WRONG PASSWD')
        return

    update_status('DEBUG ON')
    w.sysinfoTree.bind('<Double-Button-1>',lambda e:edit_sysinfo(e))
    w.clientListTree.bind('<Double-Button-1>',lambda e:edit_receiver(e))

    tabs = w.CotaNotebook.tabs()
    for t in tabs:
        title = w.CotaNotebook.tab(t, "text")
        if title == "Debug":
            w.CotaNotebook.add(t)

def update_lists():
    try:
        sel_tab = w.CotaNotebook.tab(w.CotaNotebook.select(), "text")
    except Exception as e:
        update_status(str(e))
    if sel_tab == "Demo":
        update_demo_lists()
        update_sysinfo()
    elif sel_tab == "ESL":
        update_lpm_lists()
    elif sel_tab == "Debug":
        cmd_queue.put(create_msg('rx_list', None))

def auto_update():
    update_lists()
    root._job = root.after(AUTO_UPDATE_PERIOD, auto_update)

def copy_id(e):
    curitem = e.widget.focus()
    if curitem != '':
        rx_id = e.widget.item(curitem)['text']
        root.clipboard_clear()
        root.clipboard_append(rx_id)

def clear_tree(tree):
    for row in tree.get_children():
        tree.delete(row)

def select_rx(e):
    rx_detail()

def select_lpm_slot(e):
    lpm_detail()

def lpm_detail():
    curitem = w.lpmSlotListTree.focus()
    if curitem != '':
        rx_id = w.lpmSlotListTree.item(curitem)['text']
        if rx_id == "0":
            return
        cmd_queue.put(create_msg('rx_detail', (rx_id,)))

def redraw_rx_detail(rx_details):
    sel_tab = w.CotaNotebook.tab(w.CotaNotebook.select(), "text")
    trees = {"Demo": w.clientDetailTree,
             "ESL" : w.lpmRxDetailTree}

    current_tree = trees.get(sel_tab, None)
    if current_tree is not None:
        clear_tree(current_tree)
        for key, val in rx_details.items():
            current_tree.insert("", 'end', text=key, values=(val,))

def rx_detail():
    sel_tab = w.CotaNotebook.tab(w.CotaNotebook.select(), "text")
    trees = {"Demo": w.clientListTree,
             "ESL" : w.lpmRxListTree}

    current_tree = trees.get(sel_tab, None)
    if current_tree is not None:
        curitem = current_tree.focus()
        if curitem != '':
            rx_id = current_tree.item(curitem)['text']
            cmd_queue.put(create_msg('rx_detail', (rx_id,)))

def update_demo_lists():
    cmd_queue.put(create_msg('rx_list', None))

def redraw_rx_list(client_list):
    if client_list is None or not isinstance(client_list, list):
        client_list = []

    sel_tab = w.CotaNotebook.tab(w.CotaNotebook.select(), "text")
    trees = {"Demo" : w.clientListTree,
             "ESL"  : w.lpmRxListTree,
             "Debug": w.debugClientListTree}

    current_tree = trees.get(sel_tab, None)

    # Temporarily unbind the select event so that we dont 
    # request the RX list again when redrawing
    current_tree.unbind('<<TreeviewSelect>>')

    focus_item = current_tree.focus()
    if focus_item != '':
        focus_id = current_tree.item(focus_item)['text']
        selected_items = current_tree.selection()
        selected_ids = [current_tree.item(item)['text'] for item in selected_items]
    else:
        focus_id = ''
        selected_ids = []

    clear_tree(current_tree)
    if ct.system_type == "Orion":
        rx_name = "RX ID"
    else:
        rx_name = "Client ID"

    if sel_tab == "Demo" or sel_tab == "Debug":
        for c in client_list:
            current_tree.insert("", 'end', text=c[rx_name], 
                    values=(c['LinkQuality'],
                            c['Status']))
        if len(client_list) == 0:
            clear_tree(current_tree)
    elif sel_tab == "ESL":
        for c in client_list:
            current_tree.insert("", 'end', text=c[rx_name],
                        values=(c['Status']))
    if focus_id != '':
        for row in current_tree.get_children():
            if current_tree.item(row)['text'] == focus_id:
                current_tree.selection_add(row)
                current_tree.focus(row)
            elif current_tree.item(row)['text'] in selected_ids:
                current_tree.selection_add(row)
    
    # Re-bind the select event
    current_tree.bind('<<TreeviewSelect>>', lambda e:select_rx(e))

def update_lpm_lists():
    cmd_queue.put(create_msg('rx_list', None))
    cmd_queue.put(create_msg('lpm_list', None))

def redraw_lpm_list(lpm_list):
    if lpm_list is None or len(lpm_list) == 0:
        lpm_list = [
            {
                'Short ID': '1',
                'BatteryLevel': 100,
                'NetCurrent': 5000,
                'Status': 2,
                'LpmMode': 0,
                'rssiValue': -40,
                'QueryTime': 12345,
                'Long ID': '0x00124544545',
                'LpmDisplayUpdate': 5,

            }
        ]

    current_tree = w.lpmSlotListTree
    # Temporarily unbind the select event so that we dont 
    # request the RX list again when redrawing
    current_tree.unbind('<<TreeviewSelect>>')
    
    focus_item = current_tree.focus()
    if focus_item != '':
        focus_id = current_tree.item(focus_item)['text']
        selected_items = current_tree.selection()
        selected_ids = [current_tree.item(item)['text'] for item in selected_items]
    else:
        focus_id = ''
        selected_ids = []
    clear_tree(current_tree)

    for client in lpm_list:
        c_lpm = client.get('LpmMode', 0)
        if 'Active' in client.keys():
            if c_lpm == 2:
                lpmmode = 'ON'
            else:
                lpmmode = 'OFF'
        else:
            if c_lpm == 1:
                lpmmode = 'ON'
            else:
                lpmmode = 'OFF' 
        qtime = client.get('QueryTime', 0)
        dispupdate = client.get('LpmDisplayUpdate', -1)
        rssi = client.get('rssiValue', -1)
        longid = client['Long ID']
        if '   ' in longid or '0x000000' in longid or '--' in longid:
            longid = '0'
        w.lpmSlotListTree.insert("", 'end', text=longid, 
                values=(client.get('Short ID', '0'),
                        client.get('BatteryLevel', 0),
                        client.get('NetCurrent', 0),
                        lpmmode,
                        rssi,
                        dispupdate,
                        time.strftime('%H:%M:%S', time.gmtime(qtime)),
                        ct.CLIENTSTATUS[ct.system_type].get(
                            client['Status'], "UNKNOWN")))

    if focus_id != '':
        for row in current_tree.get_children():
            if current_tree.item(row)['text'] == focus_id:
                current_tree.selection_add(row)
                current_tree.focus(row)
            elif current_tree.item(row)['text'] in selected_ids:
                current_tree.selection_add(row)
    
    # Re-bind the select event
    current_tree.bind('<<TreeviewSelect>>', lambda e:select_lpm_slot(e))

def update_sysinfo():
    cmd_queue.put(create_msg('GET_SYSTEM_INFO', None))

def redraw_sysinfo(sysinfo):
    if type(sysinfo) == str:
        update_status(sysinfo)
    elif type(sysinfo) == dict:
        for row in w.sysinfoTree.get_children():
            w.sysinfoTree.delete(row)
        for key, val in sysinfo.items():
            if key != 'Status':
                w.sysinfoTree.insert("", 'end', text=key, values=(val,))

def sys_btn_cmd(e):
    ''' These are the system buttons displayed on the main demo and ESL pages
    There may still need to be some changes between the buttons here and the
    advanced commands in the Debug tab
    '''
    cmd = e.widget['text']

    if cmd == "Send Discovery":
        disc_chan = simpledialog.askstring("Send Discovery", "Enter Channel",
                                initialvalue=ct.sysinfo.get('COMM Channel', ''))
        if disc_chan is None:
            return
        cmd_queue.put(create_msg('send_disc', (disc_chan,)))
    else:
        cmd_queue.put(create_msg('SEND_SYS_CMD', (cmd,)))
    update_sysinfo()

def demo_rx_btn(e):
    ''' These are the basic client buttons on the main demo page
    Rather than having separate functions for each button, this function
    reads the button text and sends the corresponding command
    '''
    client_btn_mapping = {
        'Register'       : 'register_rx',
        'Unregister'     : 'remove_rx',
        'Start Charge'   : 'start_charging',
        'Stop Charge'    : 'stop_charging',
        'Identify'       : 'identify_rx',
        'Sleep'          : 'rx_sleep',
    }
    cmd = e.widget['text']
    curitem = w.clientListTree.focus()
    if curitem == '':
        return

    rx_id = w.clientListTree.item(curitem)['text']
    cmd_type = client_btn_mapping.get(cmd, None)
    if cmd_type is not None:
        cmd_queue.put(create_msg(cmd_type, (rx_id,)))
        root.after(50, auto_update)

def lpm_rx_btn(e):
    ''' These are the basic client buttons on the main ESL page
    Rather than having separate functions for each button, this function
    reads the button text and sends the corresponding command
    '''
    rx_lpm_btn_mapping = {
        'Assign >'       : 'lpm_assign',
        '< Free'         : 'lpm_free',
        'LPM On'         : 'rx_lpm',
        'Standby'        : 'app_command', # 87
        'Disp Upd'       : 'app_command', # 86 <interval>
        'Antenna'        : 'app_command', # 83 <ant 1-4>
        'Slot Count'     : 'lpm_slots',
        'Start Charging' : 'start_charging',
        'Stop Charging'  : 'stop_charging',
    }

    curitem = w.lpmRxListTree.focus()
    slotitem = w.lpmSlotListTree.focus()

    rx_id = None
    slot_num = None
    slot_id = None
    data_tuple = None

    if curitem != '':
        try:
            rx_id = w.lpmRxListTree.item(curitem)['text']
        except:
            pass
    if slotitem != '':
        try:
            slot_num = w.lpmSlotListTree.item(slotitem)['values'][0]
            slot_id = w.lpmSlotListTree.item(slotitem)['text']
        except:
            pass

    cmd = e.widget['text']

    if cmd in ['Assign >']:
        if rx_id and slot_num:
            data_tuple = (rx_id, slot_num)
    elif cmd in ['Slot Count']:
        new_slot_count = simpledialog.askinteger("Slot Count", "Enter new value")
        if new_slot_count:
            data_tuple = (new_slot_count,)
    elif cmd in ['Start Charging', 'Stop Charging']:
        data_tuple = ('all',)
    else:
        print('Unknown button pressed')
        return

    cmd_type = rx_lpm_btn_mapping.get(cmd, None)
    if data_tuple:
        # TODO: uncomment the following
        # cmd_queue.put(create_msg(cmd_type, data_tuple))
        print(cmd_type, data_tuple)
        update_lpm_lists()

def lpm_load_whitelist(e):
    temp_whitelist = {}
    whitelist_fname = filedialog.askopenfilename(
        filetypes = (("CSV files","*.csv"),
                        ("TXT files","*.txt"),
                        ("All files","*.*")))

    if not whitelist_fname:
        return

    with open(whitelist_fname) as fp:
        fdata = fp.readlines()
    for line in fdata:
        entry = line.rstrip().split(',')
        if len(entry) == 1:
            key = entry[0]
            val = None
            temp_whitelist[key] = val
        elif len(entry) == 2:
            key = entry[0]
            try:
                val = int(entry[1])
            except Exception as e:
                messagebox.showerror('Error', f'Error: {key}: {e}')
            else:
                temp_whitelist[key] = val
    
    ct.lpm_whitelist = temp_whitelist

    update_status(f'Loaded {len(temp_whitelist)} IDs')

def display_whitelist():
    # TODO move this to separate file if it grows beyond displaying the whitelist
    whitelist = ct.lpm_whitelist
    whitelist_win = tk.Toplevel()
    whitelist_win.wm_title("LPM Whitelist")
    whitelist_win.wm_geometry("300x600")
    button_close = tk.Button(whitelist_win, text="Close", command=whitelist_win.destroy)
    button_close.pack(side="bottom",fill='x')
    whitelist_scrollbar = tk.Scrollbar(whitelist_win, orient="vertical")
    whitelist_scrollbar.pack(side="right", fill="y")
    whitelist_tree = ttk.Treeview(whitelist_win, yscrollcommand=whitelist_scrollbar.set)
    whitelist_scrollbar.config(command=whitelist_tree.yview)
    whitelist_tree.pack(anchor="w",fill="both", expand=True)
    whitelist_tree.configure(columns="Col1")
    whitelist_tree.heading("#0",text="RX ID")
    whitelist_tree.heading("#0",anchor="w")
    whitelist_tree.column("#0",width="200")
    whitelist_tree.column("#0",minwidth="20")
    whitelist_tree.column("#0",stretch="1")
    whitelist_tree.column("#0",anchor="center")
    whitelist_tree.heading("Col1",text="Slot")
    whitelist_tree.heading("Col1",anchor="w")
    whitelist_tree.column("Col1",width="100")
    whitelist_tree.column("Col1",minwidth="20")
    whitelist_tree.column("Col1",stretch="1")
    whitelist_tree.column("Col1",anchor="center")
    for key, val in whitelist.items():
            whitelist_tree.insert("", 'end', text=key, values=(val,))

def start_auto_assignment():
    if len(ct.lpm_whitelist) < 1:
        messagebox.showerror('Error', 'No receivers in whitelist')
        return

    update_status('STARTING ASSIGNMENT')
    lpm_assign_stop.clear()
    auto_assign_thread = LpmAutoAssign(
        cmd_queue, ct.lpm_whitelist, w.lpmRxListTree, w.lpmSlotListTree, lpm_assign_stop
    )
    auto_assign_thread.name = 'LpmAutoAssignThread'
    auto_assign_thread.start()

def stop_auto_assignment():
    for thread in threading.enumerate():
        if thread.name == 'LpmAutoAssignThread' and thread.is_alive():
            update_status('STOPPING ASSIGNMENT')
            lpm_assign_stop.set()

def lpm_slot_menu(e, command):
    curitem = w.lpmSlotListTree.focus()
    if curitem == '':
        return

    app_cmds = {
        'Display': '86',
        'Antenna': '83',
        'LPM'    : '81',
        'Standby': '87',
    }

    rx_id = w.lpmSlotListTree.item(curitem)['text']
    cmd_type = 'app_command'
    try:
        cmd, arg = command.split(' ')
    except ValueError:
        cmd = command
        arg = None

    if cmd == "Display":
        new_disp_upd = simpledialog.askinteger("Display Update", 
                        "Enter new display update interval")
        if new_disp_upd == 0:
            messagebox.showerror('Error', 'Must be greater than zero')
            return
        else:
            data_tuple = (rx_id, app_cmds.get(cmd), new_disp_upd)
    elif cmd == "Antenna":
        try:
            new_antenna = int(arg)
        except ValueError:
            # TODO support auto antenna selection
            messagebox.showerror('Error', 'Not supported')
            return
        data_tuple = (rx_id, app_cmds.get(cmd), new_antenna)
    elif cmd == "LPM":
        lpm_mode = {"On": 1, "Off": 0}.get(arg)
        if lpm_mode is not None:
            data_tuple = (rx_id, app_cmds.get(cmd), lpm_mode)
    elif cmd == "Remove":
        cmd_type = 'lpm_free'
        data_tuple = (rx_id,)
    elif cmd == "Standby":
        data_tuple = (rx_id, app_cmds.get(cmd))
    elif cmd == "Location":
        messagebox.showerror('Error', 'Not supported')
        return
        # TODO view/edit x/y/z location data
        # if arg == "View":
        #     pass
        # elif arg == "Edit":
        #     pass
    else:
        return
    
    # TODO: uncomment the following
    # cmd_queue.put(create_msg(cmd_type, data_tuple))
    print(cmd_type, data_tuple)

def edit_sysinfo(e):
    editable = {
        'COMM Channel'     : 'set_comm_channel',
        'Valid AMBs'       : 'set_valid_ambs',
        'Power Level (dBm)': 'set_power_level',
    }
    curitem = e.widget.focus()
    if curitem != '':
        param = e.widget.item(curitem)['text']
        curval = e.widget.item(curitem)['values'][0]
        if param in editable.keys():
            newval = simpledialog.askstring(param, "Enter new value",
                        initialvalue=curval)
            if newval is not None:
                cmd_type = editable[param]
                cmd_queue.put(create_msg(cmd_type, (newval,)))
                update_sysinfo()

def switch_tabs(e):
    new_tab = e.widget.tab(e.widget.select(), "text")
    if new_tab == "Demo":
        update_demo_lists()
        update_sysinfo()
    elif new_tab == "ESL":
        update_lpm_lists()
    elif new_tab == "Debug":
        cmd_queue.put(create_msg('rx_list', None))

def edit_receiver(e):
    curitem = e.widget.focus()
    if curitem == '':
        return
    rx_id = e.widget.item(curitem)['text']
    newval = simpledialog.askstring('Receiver Config', "Enter receiver config (5=STANDARD,6=EXTENDED)",
        initialvalue='5')
    if newval not in ['5', '6']:
        update_status('INVALID TYPE')
        return
    else:
        cmd_queue.put(create_msg('rx_config', (rx_id, newval)))

def send_app_cmd():
    cur_cmd = w.advancedRxList.curselection()
    cur_client = w.debugClientListTree.focus()
    if cur_cmd == () or cur_client == '':
        return
    data = w.clientCmdSendEntry.get()
    cmd = w.advancedRxList.get(cur_cmd)
    if cmd not in ct.rx_cmd_list:
        return
    rx_id = w.debugClientListTree.item(cur_client)['text']
    cmd_queue.put(create_msg('app_command', (rx_id, cmd, data)))

def send_tx_cmd():
    curitem = w.advancedTxList.curselection()
    if curitem == ():
        return
    tx_cmd_text = w.advancedTxList.get(curitem)
    data = w.sendAdvTxEntry.get()
    if data == '':
        cmd_queue.put(create_msg('SEND_SYS_CMD', (tx_cmd_text,)))
    else:
        cmd_queue.put(create_msg('SEND_SYS_CMD', (tx_cmd_text, data)))

def get_app_cmd_data():
    curitem = w.debugClientListTree.focus()
    if curitem != '':
        cur_cmd = w.advancedRxList.curselection()
        cmd = w.advancedRxList.get(cur_cmd)
        rx_id = w.debugClientListTree.item(curitem)['text']
        cmd_queue.put(create_msg('app_command_data', (rx_id, cmd)))

def redraw_app_cmd_data(client_data):
        w.clientCmdRespEntry.delete(0, 'end')
        w.clientCmdRespEntry.insert('end', client_data)

def load_cota_config():
    cmd_queue.put(create_msg('GET_ALL_CONFIG', None))
    update_status('LOADING')

def edit_config_val(e):
    curitem = e.widget.focus()
    if curitem == '':
        return
    param = e.widget.item(curitem)['text']
    curval = e.widget.item(curitem)['values'][0]
    newval = simpledialog.askstring(param, "Enter new value",
        initialvalue=curval)
    if ct.system_type == "Orion":
        if newval is not None:
            cmd_queue.put(create_msg('set_cfg_param', (param, newval)))
            cmd_queue.put(create_msg('get_cfg_param', (param,)))
    else:
        if param not in ct.ce.idx:
            return
        if newval is not None:
            for row in w.cotaConfigTree.get_children():
                    w.cotaConfigTree.delete(row)
            ct.ce.UpdateValue(param, newval)
            for name in ct.ce.names:
                    w.cotaConfigTree.insert("", 'end', text=name, 
                            values=(ct.ce.values[ct.ce.idx[name]],))

def save_cota_config():
    ''' Need to check system type here
    If orion, send SAVE_CONFIG_PARAM
    Else if Venus, send SAVE_ALL_CONFIG
    '''
    if ct.system_type == "Venus":
        cmd_queue.put(create_msg('SAVE_ALL_CONFIG', None))
        update_status('SAVING')

    else:
        pass

def redraw_config(result):
    clear_tree(w.cotaConfigTree)

    if ct.system_type == "Orion":
        for key, val in ct.cfg_params.items():
            w.cotaConfigTree.insert("", 'end', text=key, 
                    values=(val,))
    else:
        for name in ct.ce.names:
            w.cotaConfigTree.insert("", 'end', text=name, 
                    values=(ct.ce.values[ct.ce.idx[name]],))
    update_status(result)

def list_log_files():
    if not ct.log_man.connected:
        update_ssh_status('NOT CONNECTED')
        return
    cmd_queue.put(create_msg('LIST_LOGFILES', None))
    update_ssh_status('LOADING')

def populate_loglist(files):
    clear_tree(w.logfileTree)
    if not isinstance(files, list):
        update_ssh_status(files)
    else:
        for file in files:
            if '.csv' in file.filename:
                file_size = math.ceil(file.st_size / 1000)
                w.logfileTree.insert("", 'end', text=file.filename, 
                    values=(file_size,))
        update_ssh_status('SUCCESS')

def download_log_file():
    cur_file = w.logfileTree.focus()
    if cur_file == '':
        update_ssh_status('NO FILE SELECTED')
        return
    remotefile = w.logfileTree.item(cur_file)['text']
    localfile = filedialog.asksaveasfilename(
        initialfile=remotefile,
        filetypes = (("CSV files","*.csv"),("All files","*.*")))
    if not localfile:
        update_ssh_status('SAVE CANCELLED')
        return
    cmd_queue.put(create_msg('DOWNLOAD_LOG', (localfile, remotefile)))
    update_ssh_status('DOWNLOADING')

def delete_log_file():
    cur_file = w.logfileTree.focus()
    if cur_file == '':
        update_ssh_status('NO FILE SELECTED')
        return
    remotefile = w.logfileTree.item(cur_file)['text']
    confirm = messagebox.askyesno(
        'Confirm delete?',
        f'Are you sure you want to delete {remotefile}?'
    )
    if confirm:
        cmd_queue.put(create_msg('DELETE_LOG', (remotefile,)))
        cmd_queue.put(create_msg('LIST_LOGFILES', None))
    else:
        update_ssh_status('DELETE CANCELLED')

def start_logging():
    if not ct.log_man.connected:
        update_ssh_status('NOT CONNECTED')
        return
    rx_list = []
    sel_items = w.debugClientListTree.selection()
    if sel_items != '':
        for item in sel_items:
            rx_list.append(w.debugClientListTree.item(item)['text'])
    rx_list = ','.join(rx_list)

    try:
        hours_to_log = int(w.logHrsEntry.get())
        num_samples = int(w.logDelayEntry.get())
    except:
        update_ssh_status('Invalid log parameters')
        return

    if all([
            hours_to_log > 0,
            num_samples > 0,
            len(rx_list) > 0
        ]):
        cmd_queue.put(create_msg('START_LOG', 
            (rx_list, hours_to_log, num_samples)
        ))
    else:
        update_ssh_status('Invalid log parameters')

def stop_logging():
    if not ct.log_man.connected:
        update_ssh_status('NOT CONNECTED')
        return
    cmd_queue.put(create_msg('STOP_LOG', None))

def get_mcu_log():
    cmd_queue.put(create_msg('get_mcu_log', (100,)))

def save_mcu_log(window, log_data):
    log_file_name = filedialog.asksaveasfilename(
        initialfile='mcuLog.txt',
        filetypes = (("TXT files","*.txt"),("All files","*.*")))
    if log_file_name:
        with open(log_file_name, 'w') as fp:
            try:
                fp.write('\n'.join(log_data))
            except Exception as e:
                update_status(f'ERROR: {e}')
            else:
                update_status('SUCCESS')
    window.attributes("-topmost", True)

def display_mcu_log(mcu_log):
    mcu_log.reverse()
    if len(mcu_log) > 1:
        mcu_log = mcu_log[:-1]
    log_win = tk.Toplevel()
    log_win.wm_title("Log viewer")
    log_win.wm_geometry("800x400")
    button_close = tk.Button(log_win, text="Close", command=log_win.destroy)
    button_close.pack(side="bottom",fill='x')
    button_save = tk.Button(log_win, text="Save", 
        command=lambda: save_mcu_log(log_win, mcu_log))
    button_save.pack(side="bottom",fill='x')
    log_scrollbar = tk.Scrollbar(log_win, orient="vertical")
    log_scrollbar.pack(side="right", fill="y")
    log_box = tk.Listbox(log_win, yscrollcommand=log_scrollbar.set)
    log_scrollbar.config(command=log_box.yview)
    log_box.pack(anchor="w",fill="both", expand=True)

    for line in mcu_log:
        log_box.insert("end", line)
    log_box.yview('end')

def log_plot_dialog():
    create_Plot_Data_GUI(root)

def handle_data_queue():
    try:
        new_data = data_queue.get_nowait()
    except:
        root.after(50, handle_data_queue)
        return
    cmd = cmds.get(new_data.type, None)
    if cmd is not None:
        func = globals().get(cmd['recv_func'], None)
        if func is not None:
            func(new_data.data)

    root.after(50, handle_data_queue)

def clean_quit(status):
    lpm_assign_stop.set()
    update_status(status)
    root.destroy()

def send_disconnect():
    cmd_queue.put(create_msg('QUIT', None))

def client_popup(event):
    m = tk.Menu(root, tearoff=0) 
    m.add_command(label="Copy ID", command = lambda : copy_id(event)) 
    try: 
        m.tk_popup(event.x_root, event.y_root) 
    finally: 
        m.grab_release()

def lpm_slot_popup(event):
    m = tk.Menu(root, tearoff=0)

    location_submenu = tk.Menu(m, tearoff=0)
    location_submenu.add_command(label="View", command = lambda : lpm_slot_menu(event, "Location View"))
    location_submenu.add_command(label="Edit", command = lambda : lpm_slot_menu(event, "Location Edit"))

    antenna_submenu = tk.Menu(m, tearoff=0)
    antenna_submenu.add_command(label="1",    command = lambda : lpm_slot_menu(event, "Antenna 1"))
    antenna_submenu.add_command(label="2",    command = lambda : lpm_slot_menu(event, "Antenna 2"))
    antenna_submenu.add_command(label="3",    command = lambda : lpm_slot_menu(event, "Antenna 3"))
    antenna_submenu.add_command(label="4",    command = lambda : lpm_slot_menu(event, "Antenna 4"))
    antenna_submenu.add_command(label="Auto", command = lambda : lpm_slot_menu(event, "Antenna Auto"))

    lpm_submenu = tk.Menu(m, tearoff=0)
    lpm_submenu.add_command(label="On",     command = lambda : lpm_slot_menu(event, "LPM On"))
    lpm_submenu.add_command(label="Off",    command = lambda : lpm_slot_menu(event, "LPM Off"))

    m.add_command(label="Remove",         command = lambda : lpm_slot_menu(event, "Remove")) 
    m.add_cascade(label="Select Antenna", menu=antenna_submenu) 
    m.add_cascade(label="LPM",            menu=lpm_submenu) 
    m.add_command(label="Standby",        command = lambda : lpm_slot_menu(event, "Standby"))
    m.add_cascade(label="Location",       menu=location_submenu) 
    m.add_command(label="Display Update", command = lambda : lpm_slot_menu(event, "Display Update"))
    try: 
        m.tk_popup(event.x_root, event.y_root) 
    finally: 
        m.grab_release()

def clear_user_args(e):
    if e.widget is w.advancedTxList:
        w.sendAdvTxEntry.delete(0, 'end')
    elif e.widget is w.advancedRxList:
        w.clientCmdSendEntry.delete(0, 'end')
    
def init(top, gui, *args, **kwargs):
    global w, top_level, root
    w = gui
    top_level = top
    root = top
    root.title("Cota DTU (v{})".format(DTU_VERSION))
    root.geometry("1075x640")
    datafile = "cota.ico" 
    logofile = "ossia.png"
    if not hasattr(sys, "frozen"):
        datafile = os.path.join(os.path.dirname(__file__), datafile) 
        logofile = os.path.join(os.path.dirname(__file__), logofile) 
    else:  
        datafile = os.path.join(sys.prefix, datafile)
        logofile = os.path.join(sys.prefix, logofile)
    try:
        root.iconbitmap(default=datafile)
    except:
        pass
    logo = tk.PhotoImage(file=logofile)
    w.ossiaLogoBtn.configure(image=logo)
    w.ossiaLogoBtn.logo = logo
    tabs = w.CotaNotebook.tabs()
    for t in tabs:
        title = w.CotaNotebook.tab(t, "text")
        if title != 'Demo':
            w.CotaNotebook.hide(t)
    w.menubar.entryconfig("Edit", state="disabled")
    root._job = None
    root.protocol("WM_DELETE_WINDOW", send_disconnect)
    msg_handler.start()
    handle_data_queue()

def destroy_window():
    global top_level
    top_level.destroy()
    top_level = None

if __name__ == '__main__':
    import CotaDTU
    CotaDTU.vp_start_gui()




