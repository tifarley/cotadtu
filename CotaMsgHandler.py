import queue
from threading import Thread
from types import SimpleNamespace

from cmd_dicts import cmds

def create_msg(msgtype, data):
    new_msg = SimpleNamespace(
        type=msgtype,
        data=data)
    return new_msg

class CotaMsgHandler(Thread):
    ''' Cota Msg Handler Thread
    The purpose of this class is to provide a separate thread
    that has two tasks:
        1) Wait for items to appear in a command queue
        2) Process those commands and sends the results back through
           the data queue

    The purpose of this is to separate the I/O (network) from the GUI
    to create a more robust and responsive user experience
    '''
    def __init__(self, cmd_q, data_q, ct):
        super().__init__()
        self.cmd_q = cmd_q
        self.data_q = data_q
        self.ct = ct
        self.keep_running = True
        self.daemon = True
        self.no_conn_reqd = [
            'CONNECT',
            'SEARCH_FOR_TX',
            'QUIT',
        ]

    def return_data(self, data_msg):
        self.data_q.put(data_msg)

    def stop_thread(self):
        self.keep_running = False

    def run(self):
        while self.keep_running:
            deq = self.cmd_q.queue
            quit_cmd = create_msg('QUIT', None)
            if any([c.type == 'QUIT' for c in deq]):
                deq.clear()
                deq.appendleft(quit_cmd)
            try:
                new_cmd = self.cmd_q.get(timeout=5)
            except:
                new_cmd = None
            if hasattr(new_cmd, 'type'):
                # print("got new cmd: {}: {}".format(new_cmd.type, new_cmd.data))
                result = create_msg(new_cmd.type, {})
                if new_cmd.type not in self.no_conn_reqd and self.ct.is_connected is False:
                    self.cmd_q.task_done()
                    result.data = 'Not Connected'
                    self.return_data(result)
                    continue
                try:
                    func = getattr(self.ct, cmds[new_cmd.type]['send_func'], None)
                except Exception as e:
                    func = None
                if func is not None:
                    try:
                        if new_cmd.data is not None:
                            result.data = func(*new_cmd.data)
                        else:
                            result.data = func()
                    except Exception as e:
                        result.data = e
                    self.cmd_q.task_done()
                    self.return_data(result)

