import virtualbox
import paramiko
import subprocess
import logging
import re
from datetime import datetime


class Machine:
    def __init__(self, vmJSONinfo, constants):
        self.name = vmJSONinfo['name']
        self.login = vmJSONinfo['login']
        self.password = vmJSONinfo['password']
        self.repoPath = vmJSONinfo['repoPath']
        self.makePath = vmJSONinfo["makePath"]
        self.makeCmd = vmJSONinfo['makeCmd']
        self.guest = vmJSONinfo['guest']
        self.outLogPath = constants['logPath']

        self.logPath = '{}/{}_{}_output'.format(self.makePath, datetime.now().strftime('%Y-%m-%d %H:%M'), self.name)
        self.startedVmFlag = False
        self.vboxMgr = None
        self.vm = None
        self.session = None
        self.ip = 0
        self.ssh = None
        if self.guest:
            self.cmd_separator = ';'
        else:
            self.cmd_separator = '&'

        logging.debug(
            'Initializing: name: {}, login: {}, password: {}, repoPath: {}, makePath: {}, makeCmd: {}, guest: {}, outLogPath: {}, logPath: {}'.format(
                self.name, self.login, self.password, self.repoPath, self.makePath, self.makeCmd, self.guest, self.outLogPath, self.logPath))

    def initialize(self):
        if self.guest:
            # starting up virtual machine using VirtualBox API
            self.vboxMgr = virtualbox.VirtualBox()
            self.vm, self.session = Machine.power_up_virtual_machine(self)
            self.ip = Machine.get_machine_ip(self)

            # setting up ssh connection between host and guest
            self.ssh = paramiko.client.SSHClient()
            # ssh.load_system_host_keys() <-- is it needed?
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.ip, port=22, username=self.login, password=self.password)

    def get_active_branch(self):
        logging.debug('Getting active branch')
        cmd = 'cd {}{} git branch'.format(self.repoPath, self.cmd_separator)
        output, error, recv_status = Machine.run_cmd(self, cmd)

        regex = re.search('\*.*?\\n', output)
        if regex:
            return regex.group()[1:-1]
        else:
            raise Exception("Didn't find active branch")

    def create_branch(self, branch):
        logging.debug('Creating branch {}'.format(branch))
        cmd = 'cd {}{} git branch {}'.format(self.repoPath, self.cmd_separator, branch)
        Machine.run_cmd(self, cmd)

        # validate if branch was created
        cmd = 'cd {}{} git branch'.format(self.repoPath, self.cmd_separator)
        output, error, recv_status = Machine.run_cmd(self, cmd)

        if branch in output:
            return True
        else:
            raise Exception("Failed to create new branch")

    def switch_branch(self, branch):
        logging.debug('Switching to branch {}'.format(branch))
        cmd = 'cd {}{} git checkout {}'.format(self.repoPath, self.cmd_separator, branch)
        output, error, recv_status = Machine.run_cmd(self, cmd)

        if recv_status == 0:
            return True
        else:
            return False

    def delete_branch(self, branch):
        logging.debug('Deleting branch {}'.format(branch))
        cmd = 'cd {}{} git branch -D {}'.format(self.repoPath, self.cmd_separator, branch)
        output, error, recv_status = Machine.run_cmd(self, cmd)

        if recv_status == 0:
            return True
        else:
            raise Exception("Failed to delete branch {}".format(branch))

    def pull_changes_from_remote_branch(self, branch):
        logging.info('{} - Pulling changes from branch {}'.format(self.name, branch))
        cmd = 'cd {}{} git pull origin {}'.format(self.repoPath, self.cmd_separator, branch)
        output, error, recv_status = Machine.run_cmd(self, cmd)

        if recv_status == 0:
            return True
        else:
            if "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!" in error:
                raise Exception("Remote host identification has changed. Please update host key")
            elif "error: Your local changes to the following files would be overwritten by merge" in error:
                raise Exception("Unsaved changes in branch. Please commit them first")
            else:
                raise Exception("Failed pulling new changes ".format(branch))

    def build_application(self):
        logging.info('{} - Building application...'.format(self.name))
        cmd = 'cd {}{} {} >> {}'.format(self.makePath, self.cmd_separator, self.makeCmd, self.logPath)
        output, error, recv_status = Machine.run_cmd(self, cmd)
        if recv_status == 0:
            return True
        else:
            logging.error(error)
            raise Exception("Building application failed")

    def clean_up_log(self):
        return 0

    def copy_log_to_log_dir(self):
        logging.debug('Copying log from {} to log directory {}'.format(self.logPath, self.outLogPath))
        if self.guest:
            cmd = 'pscp -pw {} {}@{}:{} {}'.format(self.login, self.password, self.ip, self.logPath, self.outLogPath)
        else:
            cmd = 'COPY "{}" "{}"'.format(self.logPath, self.outLogPath)
        Machine.run_win_cmd(cmd)
        Machine.clean_up_log(self)

    def run_cmd(self, cmd):
        logging.debug('Running cmd {}'.format(cmd))
        if self.guest:
            output, error, recv_status = Machine.run_ssh_cmd(self.ssh, cmd)
        else:
            output, error, recv_status = Machine.run_win_cmd(cmd)
        return output.decode(), error.decode(), recv_status

    @staticmethod
    def run_ssh_cmd(ssh, cmd):
        stdin, stdout, stderr = ssh.exec_command(cmd)
        # waiting until command is finished
        recv_status = stdout.channel.recv_exit_status()
        error = stderr.read()
        output = stdout.read()
        return output, error, recv_status

    @staticmethod
    def run_win_cmd(cmd):
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # waiting until command is finished
        output, error = process.communicate()
        recv_status = process.returncode
        return output, error, recv_status

    def power_up_virtual_machine(self):
        logging.info("Powering up virtual machine {}".format(self.name))
        machine = self.vboxMgr.find_machine(self.name)
        session = 0
        if machine.state != virtualbox.library.MachineState(5):
            session = machine.create_session()
            session.unlock_machine()
            machine.launch_vm_process(session, 'gui', '').wait_for_completion()
            self.startedVmFlag = True
        else:
            logging.warning("Machine already started")
        return machine, session

    def get_machine_ip(self):
        ip = self.vm.enumerate_guest_properties('/VirtualBox/GuestInfo/Net/0/V4/IP')
        return ip[1][0]

    def power_down_virtual_machine(self):
        # TODO close it with the same state as it was before
        logging.info("Powering down virtual machine {}".format(self.name))
        if self.startedVmFlag:
            self.session.console.power_down()
