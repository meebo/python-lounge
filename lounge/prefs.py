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

from xml.dom.minidom import parse
import os
import time
import logging

class PrefsException(Exception):
	pass

class InvalidPrefEntry(PrefsException):
	pass

class Prefs:
	"""pass in any number of conf files to the constructor.
	The hierarchy is from right to left.  e.g. if the value of foo in A is 100, and the value of foo in B is 200
	And the constructor looks like Prefs('A','B') then calling get_prefs('foo') will return 200.
	This object can also reload a conf file thats been changed.  To enable that behaviour, pass in the
	argument reload as True.  There is a race condition since we're using integer stat times.  If the file is
	updated twice in the same second and the prefs module is reading the file at the same time, the second
	write may be ignored and lost.  If this worries you, set os.stat_float_times(True) so that the resolution of
	stat calls becomes milliseconds.
	
	Overriding preference files in a debug environment:
	If you want to use a different preference file for debugging an application, but don't want to modify either
	your code or your production prefs file, you can use an environment variable to override the pref file path.
	For example:
	You have a prefs file at /var/lounge/etc/pref.xml and you don't want to mess with it.  Instead, you'd like
	to use a different prefs file at /home/shaun/etc/pref.xml.  To do so, export the following environment 
	variable (example is for BASH):
		export LOUNGE_PREF_OVERRIDES='/var/lounge/etc/pref.xml:/home/shaun/etc/pref.xml'
	When you instantiate a prefs object, it will parse that environment variable and use your debug pref file
	if whenever it would have ordinarily used the production prefs file.

	If you want to override multiple prefs files, you can separate the pairs with semicolons.
	Example of multiple overrides:
		export LOUNGE_PREF_OVERRIDES='/first/pref/file:/first/over/ride;/second/pref/file:/second/over/ride'
	"""
	#args becomes a list of file names
	#kwargs is a dictionary of arguments
	def __init__(self, *args, **kwargs):
		self.check_interval = 'check_interval' in kwargs and kwargs['check_interval'] or 30
		self.pref_trees = []
		self.pref_files = {}#Key is the filename, value is a list (last change unix timestamp, index of file
		# in self.pref_trees).  its a list, not a tuple because tuples are immutable

		self.last_stat_check = 0
		self.reload = 'reload' in kwargs and kwargs['reload'] or False

		self.pref_overrides = self._get_pref_overrides()

		if 'no_missing_keys' in kwargs:
			self.no_missing_keys = kwargs['no_missing_keys']
		else:
			self.no_missing_keys = False

		for conf_file in args[::-1]:#Can't use reversed until we migrate to python2.5
			if conf_file in self.pref_overrides:
				logging.debug ("Prefs: using override: %s => %s" % (conf_file, self.pref_overrides[conf_file]))
				conf_file = self.pref_overrides[conf_file]
			dom = parse(conf_file)
			self.pref_trees.append(dom)
			stat_info = os.stat(conf_file)
			self.pref_files[conf_file] = [stat_info.st_mtime, len(self.pref_trees)-1]

	def _get_pref_overrides(self):
		"""
		Looks at the environment variable 'LOUNGE_PREF_OVERRIDES' and extracts file path override pairs.
		The environment variable should be of the form:
			"/path/to/prod/prefs:/path/to/debug/prefs;/next/prod/path:/next/debug/path;..."
		With pair items separated by colons and pairs separated by semicolons.

		This variable is nice for debugging in a non-production environment, so you can leave your production
		pref files untouched and not run the risk of sending debug settings in to production.
		"""
		override_raw = os.getenv("LOUNGE_PREF_OVERRIDES")
		pref_overrides = {}
		if override_raw:
			pref_names = []
			overrides = []
			for pair in override_raw.split(';'):
				(old,new) = pair.split(':')
				pref_names.append(old)
				overrides.append(new)
			pref_overrides = dict(zip(pref_names,overrides))
		return pref_overrides

	def find_elem(self, key, curr_tree):
		for child in curr_tree.childNodes:
			if not child.nodeName == "pref":
				continue
			if child.getAttribute('name') == key:
				return child
		return None

	def get_all_vals(self, node):
		vals = {}
		for child in node.childNodes:
			if not child.nodeName == "pref":
				continue
			vals[child.getAttribute("name")] = self.get_val(child)
		return vals
	
	def get_val(self, node, type=None):
		type = type and type or node.getAttribute("type")
		val = node.getAttribute("value")
		if type == "bool":
			if val not in ['0','1']:
				raise InvalidPrefEntry("Was expecting '0' or '1' for a boolean value, but found '%s'" % val)
			else:
				return (val == '1')
		elif type == "string":
			return val
		elif type == "int":
			return int(val)
		elif type == "stringlist":
			#return the value attribute of all children where nodetype == 'item'
			return [self.get_val(n, "string") for n in node.getElementsByTagName("item")]

	def get_pref(self, pref_name, default=None):
		if self.reload:
			self.check_reload()

		keys = pref_name.split("/")
		keys[0] = "/"
		for curr_tree in self.pref_trees:
			for key in keys:
				if key == "*":
					break
				curr_tree = self.find_elem(key, curr_tree)
				if curr_tree is None:#Element not found in this conf file, try the next one
					break #we break here to cause the for key in keys: loop to terminate
			if curr_tree is None: #if we broke out of the for key in keys: loop, skip to the next conf file
				continue
			if key == "*":
				return self.get_all_vals(curr_tree)
			return self.get_val(curr_tree)
		if default is not None:
			return default
		elif self.no_missing_keys:
			raise KeyError("get_pref couldn't find the requested preference: '%s'" % pref_name)
		else:
			logging.warning(""" get_pref couldn't find the requested preference: '%s' -- you're not using no_missing_keys, so this isn't an error, but you should probably make sure that the preference you're looking for is correct and switch over to using no_missing_keys.  Eventually, no_missing_keys will be the default behavior and then where will you be?  You'll be at Sad Towne, my friend.  Nobody wants to go to Sad Towne.  """ % pref_name)
		return default

	def check_reload(self):
		tm = int(time.time())
		if self.last_stat_check + self.check_interval < tm:
			self.last_stat_check = tm
			for filename in self.pref_files:#iterate over all the files
				stat_info = os.stat(filename)#stat them
				file = self.pref_files[filename]
				if file[0] < stat_info.st_mtime:#if the files been changed since we last loaded
					dom = parse(filename)#update the dom tree
					file[0] - stat_info.st_mtime#and the stat time
					self.pref_trees = self.pref_trees[0:file[1]] + [dom] + self.pref_trees[file[1]+1:]#splice
