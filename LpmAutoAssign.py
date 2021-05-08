import time
from threading import Thread, Event
from CotaMsgHandler import create_msg

class LpmAutoAssign(Thread):
    ''' LPM Auto Assignment Thread
    The purpose of this class is to provide a separate thread
    that does the following:
        1) Reads the entries in rx_list and lpm_list front panel widgets
        2) Checks to see if any of the new entries to rx_list exist in the whitelist
        3) Enqueues a command to assign the newly discovered receivers to slots
    
    This thread will run until either:
        1) The stop_event is sent from the main thread, or
        2) All whitelist IDs have been assigned to slots
    '''
    def __init__(self, cmd_queue, lpm_whitelist, rx_list_widget, lpm_list_widget, stop_event):
        super().__init__()
        self.cmd_queue = cmd_queue
        self.lpm_whitelist = lpm_whitelist
        self.rx_list_widget = rx_list_widget
        self.lpm_list_widget = lpm_list_widget
        self.stop_event = stop_event

    def read_lists(self):
        self.discovered_rx_ids = []
        self.assigned_slot_ids = {}

        for row in self.rx_list_widget.get_children():
            rx_id = self.rx_list_widget.item(row)['text']
            self.discovered_rx_ids.append(rx_id)

        for row in self.lpm_list_widget.get_children():
            rx_id = self.lpm_list_widget.item(row)['text']
            slot_num = self.lpm_list_widget.item(row)['values'][0]
            self.assigned_slot_ids[rx_id] = slot_num

    def queue_assignment(self, rx_id, slot_num):
        self.cmd_queue.put(create_msg('lpm_assign', (rx_id, slot_num)))

    def run(self):
        print('starting auto assignment')
        keep_running = True
        while keep_running:
            self.read_lists()
            print('discovered: ', self.discovered_rx_ids)
            print('lpm_list: ', self.assigned_slot_ids)

            # Remove IDs from whitelist when they appear in lpm list
            # Meaning they were successfully assigned
            for rx_id in self.assigned_slot_ids:
                if rx_id in self.lpm_whitelist:
                    print(f'removing {rx_id} from whitelist')
                    del(self.lpm_whitelist[rx_id])

            # Queue up commands to assign IDs to slots if they 
            # are discovered and in the whitelist
            for rx_id in self.discovered_rx_ids:
                if rx_id in self.lpm_whitelist:
                    slot_num = self.lpm_whitelist.get(rx_id)
                    if slot_num is None:
                        # TODO: if no slot number, assign to next available
                        slot_num = 'NEXT'
                    print(f'setting {rx_id} to slot {slot_num}')
                    # TODO: uncomment the following
                    # queue_assignment(rx_id, slot_num)

            time.sleep(2)

            if self.stop_event.is_set() or len(self.lpm_whitelist) == 0:
                keep_running = False

        print('auto assignment thread has ended')