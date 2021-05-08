import os
import paramiko

class RemoteLogManager:
    def __init__(self):
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.sftp_client = None
        self.connected = False

    def set_config(self, hostname, system_type, username, password):
        self.hostname = hostname
        if system_type == 'Orion':
            self.port = 22
            self.RemoteDirectory = '/home/pi/scripts/'
            self.log_script = 'OrionLogger.py'
        else: # Venus
            self.port = 2222
            self.RemoteDirectory = '/home/gumstix/scripts/'
            self.log_script = 'logClientDetailRemote.py'

        self.username = username
        self.password = password

    def connect(self, port):
        try:
            self.ssh_client.connect(hostname=self.hostname,
                port=port,
                username=self.username,
                password=self.password,
                compress=True)
        except Exception as e:
            raise e
        else:
            self.sftp_client = self.ssh_client.open_sftp()
            self.connected = True
            
    def disconnect(self):
        if self.connected:
            self.ssh_client.close()
            self.connect = False

    def start_logging(self, rx_list, hours_to_log, log_interval):
        num_samples = hours_to_log*3600 // log_interval
        log_cmd = 'cd {};nohup python3 {} -t localhost -c {} -n {} -d {} &'.format(
            self.RemoteDirectory,
            self.log_script,
            rx_list, 
            num_samples,
            log_interval
        )
        status = self.execute_cmd(log_cmd)
        return status

    def stop_logging(self):
        stop_cmd = f'pkill -u {self.username} -f {self.log_script}'
        status = self.execute_cmd(stop_cmd)
        return status

    def execute_cmd(self, cmd):
        stdin,stdout,stderr = self.ssh_client.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        return exit_status

    def list_files(self):
        if self.connected:
            try:
                files = self.sftp_client.listdir_attr(self.RemoteDirectory)
                files.sort(key = lambda f: f.st_mtime, reverse=True)
                return files
            except Exception as e:
                return f'ERROR: {e}'
        else:
            return 'NOT CONNECTED'

    def download_file(self, localpath, remotefile):
        try:
            remotepath = self.RemoteDirectory + remotefile
            self.sftp_client.get(remotepath, localpath)
            fsize = os.lstat(localpath).st_size
            return f'{fsize} bytes transferred'
        except Exception as e:
            return f'ERROR: {e}'

    def delete_file(self, remotefile):
        try:
            remotepath = self.RemoteDirectory + remotefile
            ret = self.sftp_client.remove(remotepath)
            ret = 'DELETED'
        except FileNotFoundError:
            ret = 'ERROR'
        return ret
    
    def CheckScriptsFolder(self, createIfNotFound=False):
        try:
            self.sftp_client.lstat(self.RemoteDirectory)
            return True
        except FileNotFoundError:
            if createIfNotFound:
                self.sftp_client.mkdir(self.RemoteDirectory)
                try:
                    self.sftp_client.lstat(self.RemoteDirectory)
                    return True
                except:
                    return False
            else:
                return False

    def UploadFile(self, LocalPath, RemotePath):
        if os.path.exists(LocalPath):
            return self.sftp_client.put(LocalPath, RemotePath)
        else:
            return None

