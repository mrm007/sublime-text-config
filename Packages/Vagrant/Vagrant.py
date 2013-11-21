import sublime, sublime_plugin
import subprocess
import threading
import os, functools, time
from os.path import exists, isdir, dirname
try:    
    import thread 
except ImportError:
    import _thread as thread #Py3K changed it.

settings = sublime.load_settings('Vagrant.sublime-settings')

class Prefs:
    @staticmethod
    def load():
        Prefs.vagrant_path = settings.get('vagrant_path', "/usr/bin/vagrant")
        Prefs.additional_args = settings.get('additional_args', {})
        Prefs.debug = settings.get('debug', False)

Prefs.load()

settings.add_on_change('vagrant_path', Prefs.load)
settings.add_on_change('additional_args', Prefs.load)
settings.add_on_change('debug', Prefs.load)

# StatusProcess cribbed from:
# https://github.com/stuartherbert/sublime-phpunit/blob/master/phpunit.py
class StatusProcess(object):
    def __init__(self, msg, listener):
        self.msg = msg
        self.listener = listener
        thread.start_new_thread(self.run_thread, ())

    def run_thread(self):
        progress = ""
        while True:
            if self.listener.is_running:
                if len(progress) >= 10:
                    progress = ""
                progress += "."
                sublime.set_timeout(functools.partial(self.listener.update_status, self.msg, progress), 0)
                time.sleep(1)
            else:
                break

# the AsyncProcess class has been cribbed from:
# https://github.com/stuartherbert/sublime-phpunit/blob/master/phpunit.py
# and in turn: https://github.com/maltize/sublime-text-2-ruby-tests/blob/master/run_ruby_test.py

class AsyncProcess(object):
    def __init__(self, cmd, cwd, listener):
        self.listener = listener
        
        if os.name == 'nt':
            # we have to run PHPUnit via the shell to get it to work for everyone on Windows
            # no idea why :(
            # I'm sure this will prove to be a terrible idea
            self.proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        else:
            # Popen works properly on OSX and Linux
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
        if self.proc.stdout:
            thread.start_new_thread(self.read_stdout, ())
        if self.proc.stderr:
            thread.start_new_thread(self.read_stderr, ())

    def read_stdout(self):
        while True:
            data = os.read(self.proc.stdout.fileno(), 2 ** 15)
            if data != "":
                sublime.set_timeout(functools.partial(self.listener.append_line, data), 0)
            else:
                self.proc.stdout.close()
                self.listener.is_running = False
                break

    def read_stderr(self):
        while True:
            data = os.read(self.proc.stderr.fileno(), 2 ** 15)
            if data != "":
                sublime.set_timeout(functools.partial(self.listener.append_line, data), 0)
            else:
                self.proc.stderr.close()
                self.listener.is_running = False

                break

class ShellCommand(object):
    """Base class for shelling out a command to the terminal"""
    def __init__(self):
        self.error_list = []

    def get_errors(self, path):
        self.execute(path)
        return self.error_list

    def append_line(self, message):
        print(message)

    def shell_out(self, cmd):
        try:
            data = None
            print(' '.join(cmd))

            shell = sublime.platform() == "windows"
            proc = subprocess.Popen(cmd, cwd=self.vagrantConfigPath, stdout=subprocess.PIPE, shell=shell, stderr=subprocess.STDOUT)

            if proc.stdout:
                data = proc.communicate()[0]

            return (proc.returncode, data)
        except OSError as e:
            print('OS Error. (' + e.errno + " : " + e.strerror + ')')

    def update_status(self, msg, progress):
        sublime.status_message(msg + " " + progress)

    def start_async(self, caption, executable, cwd):
        self.is_running = True
        self.proc = AsyncProcess(executable, cwd, self)
        StatusProcess(caption, self)

    def run_command(self, command, vagrantConfigPath, params={}, async = True):
        args = []

        self.vagrantConfigPath = vagrantConfigPath

        application_path = Prefs.vagrant_path

        args = [application_path]

        args.append(command)

        # Check for any extra args the user wants to include.
        for key, value in Prefs.additional_args.items():
            arg = key
            if value != "":
                arg += "=" + value
            args.append(arg)

        for key, value in params.items():
            arg = key

            if value != "":
                arg += "=" + value

            args.append(arg)
        
        print(' '.join(args))

        #result = self.shell_out(args)
        if async:
            self.start_async("Running Vagrant ", args, vagrantConfigPath)
        else:
            (returncode, data) = self.shell_out(args)
            print(data)
            return returncode

    def execute(self, path=''):
        debug_message('Command not implemented')

class Vagrant(ShellCommand):
    def __init__(self):
        super(Vagrant, self).__init__()

    def getVagrantConfigPath(self):
        window = sublime.active_window();
        
        folder = window.folders()[0]

        found = False

        while not found:
            print("Searching : " + folder)

            if exists(folder + "/Vagrantfile"):
                return folder

            # If this directory has the git folder, stop.
            if exists(folder + "/.git") and isdir(folder + "/.git"):
                print('Unable to find Vagrantfile, found .git folder and assumed this is the root of your project.')
                raise Exception("Unable to find Vagrantfile, found .git folder and assumed this is the root of your project.")

            # Have we hit rock bottom?
            if dirname(folder) == folder:
                print('Unable to find root folder, sublime-vagrant only supports git right now.')
                raise Exception("Unable to find root folder, sublime-vagrant only supports git right now.")

            # Try the next directory up.
            folder = dirname(folder)

class VagrantReload(Vagrant):
    def execute(self, path=''):
        self.run_command('reload', self.getVagrantConfigPath())

class VagrantDestroy(Vagrant):
    def execute(self, path=''):
        self.run_command('destroy', self.getVagrantConfigPath(), {'--force': ''})

class VagrantUp(Vagrant):
    def execute(self, path=''):
        self.run_command('up', self.getVagrantConfigPath())

class VagrantStatus(Vagrant):
    def execute(self, path=''):
        self.run_command('status', self.getVagrantConfigPath())

class VagrantDestroyUp(Vagrant):
    def execute(self, path=''):
        result = self.run_command('destroy', self.getVagrantConfigPath(),
                                  {'--force': ''}, False)
        if result == 0:
            self.run_command('up', self.getVagrantConfigPath())

class VagrantInit(Vagrant):
    def execute(self, path=''):
        self.run_command('init', self.getVagrantConfigPath())

class VagrantHalt(Vagrant):
    def execute(self, path=''):
        self.run_command('halt', self.getVagrantConfigPath())

class VagrantSuspend(Vagrant):
    def execute(self, path=''):
        self.run_command('suspend', self.getVagrantConfigPath())

class VagrantProvision(Vagrant):
    def execute(self, path=''):
        self.run_command('provision', self.getVagrantConfigPath())

class VagrantBaseCommand(sublime_plugin.TextCommand):
    def run(self, paths=[]):
        print("Not implemented")

    def is_enabled(self):
        try:
            if Prefs.debug:
                print('Vagrant config path found: ' . self.getVagrantConfigPath())

            Vagrant().getVagrantConfigPath()
        except Exception:
            return False

        return True

class VagrantReloadCommand(VagrantBaseCommand):
    description = 'Reload the Vagrant VM.'
    
    def run(self, args):
        '''Reload the Vagrant config for this VM'''
        cmd = VagrantReload()
        cmd.execute()

    def description(self):
        return 'Reload the Vagrant config.'

class VagrantDestroyCommand(VagrantBaseCommand):
    description = 'Destroy the Vagrant VM.'
    
    def run(self, args):
        '''Destroy the Vagrant config for this VM'''
        cmd = VagrantDestroy()
        cmd.execute()

    def description(self):
        return 'Destroy the Vagrant config.'

class VagrantUpCommand(VagrantBaseCommand):
    description = 'Start the Vagrant VM.'
    
    def run(self, args):
        '''Start the Vagrant config for this VM'''
        cmd = VagrantUp()
        cmd.execute()

    def description(self):
        return 'Start the Vagrant VM.'

class VagrantDestroyUpCommand(VagrantBaseCommand):
    description = 'Destroy & Start the Vagrant VM.'
    
    def run(self, args):
        '''Reload the Vagrant config for this VM'''
        cmd = VagrantDestroyUp()
        cmd.execute()

    def description(self):
        return 'Reload the Vagrant config.'

class VagrantHaltCommand(VagrantBaseCommand):
    description = 'Forcefully halt the Vagrant VM.'
    
    def run(self, args):
        '''Reload the Vagrant config for this VM'''
        cmd = VagrantHalt()
        cmd.execute()

    def description(self):
        return 'Forcefully halt the Vagrant VM.'

class VagrantSuspendCommand(VagrantBaseCommand):
    description = 'Suspend the Vagrant VM.'
    
    def run(self, args):
        '''Reload the Vagrant config for this VM'''
        cmd = VagrantHalt()
        cmd.execute()

    def description(self):
        return 'Suspend the Vagrant VM.'

class VagrantStatusCommand(VagrantBaseCommand):
    description = 'Status of the Vagrant VM.'
    
    def run(self, args):
        '''Reload the Vagrant config for this VM'''
        cmd = VagrantStatus()
        cmd.execute()

    def description(self):
        return 'Status of the Vagrant VM.'

class VagrantProvisionCommand(VagrantBaseCommand):
    description = 'Run any configured Vagrant provisioners.'

    def run(self, args):
        '''Run the configured provisioner configured on this VM'''
        cmd = VagrantProvision()
        cmd.execute()

class VagrantInitCommand(VagrantBaseCommand):
    description = 'Initialise a new Vagrant project.'
    
    def run(self, args):
        '''Start the Vagrant config for this VM'''
        cmd = VagrantInit()
        cmd.execute()

    def is_enabled(self):
        return True

    def description(self):
        return 'Initialise a new Vagrant project.'