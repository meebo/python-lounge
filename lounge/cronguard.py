#Copyright 2009 Meebo, Inc.
#
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

import os
import os.path
import sys
import atexit
import logging
import string

class CronGuardException(Exception):
	"""
	Parent class for all the CronGuard exceptions
	"""
	pass

class InvalidPidfileName(CronGuardException):
	"""
	Raised if we've failed to construct a pidfile name
	"""
	pass

class ProcessStillRunning(CronGuardException):
	"""
	Raised if a pidfile exists and the previous process is the executable as
	the current process
	"""
	pass

class CronGuard:
	"""
	Manages the creation and deletion of pidfiles from cron scripts.  When a
	CronGuard object is created, it will check for the existence of pidfile.
	If it finds one, it verifies the existence of the previous process and
	raises an exception.
	Registers a function to be called on exit to clean up the pidfile.
	Example:
	  from cronguard import CronGuard
	  cg = CronGuard()
	  
	The default usage should work for the majority of scripts.
	"""

	def __init__(self, pidfile_dir = "/var/run/lounge", pidfile_name = None):
		(exe_path, self.exe_name) = os.path.split(sys.argv[0])

		if not pidfile_name:
			pidfile_name = self.exe_name + ".pid"
			if not pidfile_name:
				raise InvalidPidfileName

		self.pid_path = os.path.join (pidfile_dir, pidfile_name)
		if os.path.exists(self.pid_path):
			#a pidfile already exists so get the pid and check if the process exists
			try:
				pid = int(file(self.pid_path).read())
			except ValueError:
				#if the pidfile is empty (file was opened, but the pid was never written)
				#just set this to an impossible pid so it will be caught as an improper
				#exit of the previous process.
				pid = -1
			proc_stat_path = "/proc/%d/stat" % pid
			if os.path.exists(proc_stat_path):
				#there's a process with that pid currently running, check if it's the same process or a
				#different process that just happened to get the same pid
				pid_exe = string.split(file(proc_stat_path).read())[1]
				pid_exe_no_paren = pid_exe.strip("()")
				if self.exe_name[0:len(pid_exe_no_paren)] == pid_exe_no_paren:
					#yup, this is the same process
					raise ProcessStillRunning
				else:
					#different process with the same pid
					#still means that the previous process didn't clean up the pidfile
					logging.warn("Previous process did not delete pidfile -- possible crash?")
					os.unlink(self.pid_path)
			else:
				#process exited without cleaning up pidfile
				logging.warn("Previous process did not delete pidfile -- possible crash?")
				os.unlink(self.pid_path)

		self._write_pidfile()

		atexit.register(self._remove_pidfile)

	def _write_pidfile(self):
		current_pid = os.getpid()
		pidfile = open(self.pid_path, "w")
		pidfile.write("%d" % current_pid)
		pidfile.flush()
		pidfile.close()

	def _remove_pidfile(self):
		os.unlink(self.pid_path)

if __name__ == "__main__":
	cg1 = CronGuard()
