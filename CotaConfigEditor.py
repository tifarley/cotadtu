import sys,os,json,uuid,paramiko,time
from collections import OrderedDict

class CotaConfigEditor():
    def __init__(self):
        self.RemoteFile = '/etc/cota/Cota_Config.json'
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ftp = None
        self.cota_config = []
        self.data = None
        self.idx = {}
        self.names = []
        self.values = []

    def ConnectSsh(self,hostname):
        self.hostname = hostname
        try:
            self.ssh_client.connect(
                hostname=self.hostname,username='gumstix',password='gumstix',port=22)
        except paramiko.ssh_exception.AuthenticationException:
            self.ssh_client.connect(
                hostname=self.hostname,username='gumstix',password='gumstix',port=2222)
        self.ftp = self.ssh_client.open_sftp()

    def FixPermissions(self):
        stdin, stdout, stderr = self.ssh_client.exec_command('sudo chmod 666 {}'.format(self.RemoteFile))
        result = stdout.read()

    def DownloadConfig(self):
        self.FixPermissions()
        with self.ftp.open(self.RemoteFile) as fp:
            self.data = json.load(fp, object_pairs_hook=OrderedDict)
        for i,x in enumerate(self.data):
            self.names.append(x['Name'])
            self.values.append(x['Value'])
            self.idx[x['Name']] = i

    def UpdateValue(self, name, value):
        if name in self.names:
            i = self.idx[name]
            type = self.data[i]['Type']
            if type =='string' or type == 'hex32':
                self.data[i]['Value'] = str(value)
            else:
                self.data[i]['Value'] = int(value)
            self.values[i] = value
        
    def UploadConfig(self):
        time_str = time.strftime('%d%m%Y_%H%M%S')
        backup_cmd = 'sudo cp {} {}.bak_{}'.format(
                        self.RemoteFile, self.RemoteFile, time_str)
        stdin, stdout, stderr = self.ssh_client.exec_command(backup_cmd)
        result = stdout.read()
        self.FixPermissions()
        with self.ftp.open(self.RemoteFile, 'w') as fp:
            json.dump(self.data,fp,indent=3,separators=(',',' : '))
            fp.write('\n')

    def DisconnectSsh(self):
        self.ssh_client.close()

if __name__ == "__main__":
    ce = CotaConfigEditor()
    ce.ConnectSsh('192.168.240.2')
    ce.DownloadConfig()

