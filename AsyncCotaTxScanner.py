import asyncio
import ipaddress
import socket

class AsyncCotaTxScanner():
    def __init__(self, loop, port, timeout):
        self.target_addresses = []
        self.my_ip = None
        self.port = port
        self.timeout = timeout
        self.results = []
        self.loop = loop

    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            self.my_ip = s.getsockname()[0]
        except Exception:
            self.my_ip = None
        finally:
            s.close()
        return self.my_ip

    def get_host_addresses(self):
        if self.get_ip() is None:
            return
        try:
            ipv4net = ipaddress.ip_network(f'{self.my_ip}/24', strict=False)
            self.target_addresses = list(map(str, ipv4net.hosts()))
        except:
            pass

    @property
    def __scan_coroutines(self):
        return [self.__scan_target(address) for address in self.target_addresses]

    def execute(self):
        if len(self.target_addresses) > 0:
            self.loop.run_until_complete(asyncio.wait(self.__scan_coroutines))

    async def __scan_target(self, address):
        try:
            await asyncio.wait_for(
                asyncio.open_connection(address, self.port, loop=self.loop), timeout=self.timeout)
            self.results.append(address)
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            pass
