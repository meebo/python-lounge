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

import cjson
import copy
import httplib2
import logging
import os
import random
import socket
import StringIO
import urllib

from cjson import DecodeError
from UserDict import DictMixin

db_config = {
	'prod': 'http://lounge:6984/',
	'dev': 'http://lounge.dev.meebo.com:6984/',
	'local': 'http://localhost:5984/',
	}
db_connectinfo = None
db_prefix = ''
db_timeout = None

def random_junk():
	return ''.join(random.sample("abcdefghijklmnopqrstuvwxyz", 6))

def use_config(cfg, testing=False):
	global db_connectinfo
	db_connectinfo = db_config[cfg]

	global db_prefix 
	if testing: 
		# for testing: prefix every database with our username
		# achieves two goals:
		# 1) don't screw up existing databases
		# 2) let two users run tests on (for example) dev at the same time
		db_prefix = 'test' + os.environ['USER'] + random_junk() + "_"
	else:
		db_prefix = ''

def get_path(it, selector):
	"""Finds a value deep within a collection of collections, hopefully without throwing any KeyErrors along the way.
	NOTE: Assumes no lists are involved.  Please patch to account for these."""
	args = selector.split('.')
	for arg in args:
		if not hasattr(it, 'get'):
			return None
		it = it.get(arg, None)
	return it

def set_path(it, selector, value):
	"""Like get_path, but sets a value instead."""
	args = selector.split('.')
	last_arg = args.pop(-1)
	for arg in args:
		try:
			it = it[arg]
		except KeyError, e:
			it[arg] = {}
			it = it[arg]
	it[last_arg] = value
	return value

# default to production config
use_config('prod')

class LoungeError(Exception):
	def __init__(self, code, key='', reason=None):
		self.key = key
		self.code = code
		self.reason = reason

	def __str__(self):
		s = "Resource %s returned %d" % (self.key, self.code)
		if self.reason:
			s += " (%s)" % self.reason
		return s
	
	def __repr__(self):
		return "%s(%d, %s, %s)" % (self.__class__.__name__, self.code, self.key, self.reason)

	@classmethod
	def make(cls, code, key='', reason=None):
		"""Make an exception from an HTTP error code."""
		if code == 404:
			return NotFound(code, key, reason)
		elif code == 408:
			return RequestTimedOut(code, key, reason)
		elif code == 409:
			return RevisionConflict(code, key, reason)
		elif code == 504:
			return ProxyTimedOut(code, key, reason)
		return cls(code, key, reason)

class NotFound(LoungeError):
	"""Exception for when you read or update a missing record."""
	pass

class AlreadyExists(LoungeError):
	"""Exception for when you write a record that already exists."""
	pass

class RevisionConflict(LoungeError):
	"""Exception for updating a record with an out-of-date revision."""
	pass

class SocketError(LoungeError):
	"""Exception for when we have an error on the socket"""
	
class RequestTimedOut(LoungeError):
	"""Exception for when a request times out"""
	pass

class ProxyTimedOut(LoungeError):
	"""Exception for proxy timeouts"""
	pass

class ValidationFailed(Exception):
	"""Exception for when an object fails validation."""
	pass

def get_db_connectinfo(resource):
	# if it's set on the resource, use it; otherwise, fall
	# back on the global db_connectinfo
	return resource.db_connectinfo or db_connectinfo

class Resource(object, DictMixin):
	"""A generic REST resource.
	
	You can override url() and make_key() to specify how to
	access the resource.
	"""
	# you can set default values for attributes here
	# e.g., defaults = {"interests": []}
	# that way when you create a new record, you can do:
	#
	# me = Person.new("kevin")
	# me.interests.append("books")
	# 
	# and you will guarantee that it will be set to 
	# some kind of list.  Saves a lot of edge-case handling!
	defaults = {}
	db_connectinfo = None

	def __init__(self):
		"""Private!  Use find or new."""
		self._responsecode = 0
		# set ._rec last!
		# TODO can we make this private?
	
	def url(self):
		"""Get the URL of this resource.

		For generic resources, the key *is* the URI.  For other resources,
		override it.
		"""
		return self._key
	
	@classmethod
	def make_key(cls, strkey):
		"""Turn some arguments into a string key.
		
		By default, just take one argument and don't touch it.

		If a subclass wants to have a special key, you can override the make_key
		method with whatever arguments you want.  For example,

		@classmethod
		def make_key(cls, protocol, username):
		  return ':'.join(protocol, username)

		Then you can do

		Whatever.find("aim", "meebokevin")

		and it will look up the record with the key aim:meebokevin
		"""
		return strkey
	
	def _encode(self, payload):
		"""Encode an object for writing.

		For typical Couch stuff, we encode as JSON.  Override as needed.
		
		Returns content-type, body pair.
		"""
		return "application/json", cjson.encode(payload)
	
	def _decode(self, payload, headers):
		"""Decode a response.

		For typical Couch stuff, we parse as JSON.  Override as needed.
		"""
		try:
			return cjson.decode(payload)
		except DecodeError:
			raise DecodeError(payload)
	
	### REST helpers
	def _request(self, method, url, args=None, body=None):
		"""Make a REST request."""

		handle = httplib2.Http(timeout=db_timeout)

		if args is not None:
			uri = url + '?' + urllib.urlencode(args)
		else:
			uri = url

		headers = None
		if body is not None:
			content_type, body = self._encode(body)
			headers = {'Content-Type': content_type}

		reason = None
		try:
			response, content = handle.request(uri, method=method, headers=headers, body=body)
			self._responsecode = int(response.get('status', 0))

		except socket.timeout, e:
			self._responsecode = 408
			raise RequestTimedOut(self._responsecode, self._key)

		except Exception, e:
			self._responsecode = 400

			if isinstance(e, socket.error):
				raise SocketError(self._responsecode, self._key, e.args[1])
			elif isinstance(e, httplib2.HttpLib2Error):
				reason = "HTTPLib2Error: %s" % str(e)
			else:
				reason = "Exception: %s" % str(e)

		# if nginx has a bad request, it will return a 400-like error page
		# without setting the correct header.
		if self._responsecode == 0:
			self._responsecode = 400

		if self._responsecode >= 400:
			raise LoungeError.make(self._responsecode, self._key, reason)

		content_type = response.get('content-type', 'application/octet-stream')
		return self._decode(content, content_type)
	
	### basic REST operations
	def _get(self, args=None):
		return self._request('GET', self.url(), args=args)
	
	def _put(self, args=None):
		result = self._request('PUT', self.url(), body=self._rec, args=args)
		return result
	
	def _delete(self, args=None):
		return self._request('DELETE', self.url(), args=args)

	@classmethod
	def generate_uuid(cls):
		"""Implement in subclasses where it's OK to have a UUID as a key"""
		raise NotImplementedError

	@classmethod	
	def new(cls, *key, **attrs):
		if not key:
			key = (cls.generate_uuid(),)
		"""Make a new record."""
		inst = cls()
		inst._key = cls.make_key(*key)
		inst._rec = copy.deepcopy(inst.defaults)
		# fill in from kwargs
		for k,v in attrs.items():
			inst._rec[k] = v
		inst._rec["_id"] = inst._key
		return inst
	
	@classmethod
	def create(cls, *key, **attrs):
		"""Make a new record and save it."""
		inst = cls.new(*key, **attrs)
		inst.save()
		return inst

	@classmethod
	def find(cls, *key):
		"""Load a record from the database.

		Ex.
		me = UserProfile.find("kevin")

		raises ResourceNotFound if there is no match
		"""
		inst = cls()
		inst._key = cls.make_key(*key)
		inst._rec = inst._get()

		return inst

	@classmethod
	def find_or_new(cls, *key):
		"""Load a record from the database, or return a new one if it does not exist."""
		try:
			return cls.find(*key)
		except NotFound:
			return cls.new(*key)
	
	def save(self, batchok=False):
		"""Create or update an existing record."""
		args = None
		if batchok:
			args = {"batch": "ok"}
		result = self._put(args)
		if result.get("ok",False):
			if "id" in result:
				self._rec["_id"] = result["id"]
			if "rev" in result:
				self._rec["_rev"] = result["rev"]
	
	def reload(self):
		"""Update a record from the database."""
		self._rec = self._get()
	
	def destroy(self):
		"""Remove a record from the database."""
		rev = None
		if '_rev' in self._rec:
			rev = {'rev': self._rec['_rev']}
		response = self._delete(rev)

	def update(self, args):
		"""Update the element in the record w/ the elements in args"""
		self._rec.update(args)

	def get_path(self, selector):
		return get_path(self._rec, selector)

	def set_path(self, selector, value):
		return set_path(self._rec, selector, value)

	def keys(self):
		return self._rec.keys()

	def __contains__(self, arg):
		return arg in self._rec

	def __setitem__(self, key, value):
		self._rec[key] = value

	def __getitem__(self, key):
		return self._rec[key]
	
	def __delitem__(self, key):
		del self._rec[key]

	def __getattr__(self, attr):
		"""Allow apps to access document attributes directly.

		Python will call __getattr__ if an attribute is not in an object's
		dictionary.  We fall back on checking the record.  So for example 
		if our document is {"monkeys": "great"}, then inst.monkeys == "great".
		"""
		try:
			return self._rec[attr]
		except KeyError:
			# or we could
			raise AttributeError("%s has no attribute '%s'" % (str(self), attr))
	
	def __setattr__(self, attr, v):
		"""Allow apps to set document attributes directly.

		If an attribute is not in the dictionary, we set it on the record
		that will be stored upon save, not on the object.  So if you do
		inst.monkeys = "great", then the document will be 
		{"monkeys": "great"}

		We need to be able to set attributes in the constructor, however.
		So we check if '_rec' has been set before doing our override.

		Instead of that special case, we could use object.__setattr__
		in the constructor.
		"""
		# override default setattr only after construction
		if ("_rec" in self.__dict__) and (not attr in self.__dict__) and attr != "_rec":
			self._rec[attr] = v
		else: 
			return object.__setattr__(self, attr, v)

class Database(Resource):
	@classmethod
	def make_key(cls, key):
		return db_prefix + key

	def url(self):
		# key is database new; url is couch url/database
		return get_db_connectinfo(self) + self._key

class Document(Resource):
	"""Base class for a lounge record.

	Example:

	class Person(Rec):
		db_name = "people"
	
	# set attributes by kwargs
	me = Person.new("kevin", age=25, gender='m')
	# set them directly
	me.interests = ["soccer","cheese"]
	me.save()
	"""

	# set this to the name of your database
	db_name = None

	# use _db_name internally-- it will add the test prefix if needed.
	# external applications can set db_name
	def get_db_name(self):
		return db_prefix + self.db_name
	_db_name = property(get_db_name)

	def __init__(self):
		# do it here, before ._rec is created, so this does not
		# become an attribute passed on to the database
		self._errors = {}
		Resource.__init__(self)

	@classmethod
	def generate_uuid(cls):
		url = get_db_connectinfo(cls) + "_uuids?count=1";
		uuids = Resource.find(url).uuids
		return uuids[0]

	def save(self, **kwargs):
		 is_valid = self.validate()
		 if not is_valid:
			 raise ValidationFailed("Validation failed for object of type %s: %s.  Errors: %s" % (self.__class__, str(self._rec), str(self._errors)))
		 super(Document, self).save(**kwargs)

	def url(self):
		# It should be OK to create a Document instance with no db-- the only
		# issue will come when you try to save it
		if self.db_name is None:
			raise NotImplementedError("Database not provided")
		return get_db_connectinfo(self) + self._db_name + '/' + urllib.quote(self._key.encode('utf8', 'xmlcharrefreplace'), safe=':/,~@!')
	
	def set_error(self, attr, msg):
		"""Add an error message to the object's errors dict.

		Call this in your validation functions to explain why validation failed.
		"""
		if attr not in self._errors:
			self._errors[attr] = []
		self._errors[attr].append(msg)

	def errors_for(self, attr):
		if attr in self._errors:
			return self._errors[attr]
		return []

	def validate(self):
		"""Used to validate our document before we save it.  Returns True if
		the document is valid, False if it isn't.

		Implement methods starting with validate_ to add your validations.
		"""
		status = True
		self._errors = {}
		# find all method named validate_
		for attr in dir(self):
			if attr.startswith('validate_'):
				f = getattr(self, attr)
				# make sure it's actually callable
				if hasattr(f, '__call__'):
					status = f() and status
		return status

	def get_attachment(self, name):
		"""
		Retrieves an attachment from this Document, raising NotFound if
		it's not found.
		"""
		return Attachment.find(self.url() + "/" + urllib.quote_plus(name))
	
	def new_attachment(self, name):
		"""Set up for saving an attachment to this document.

		When creating or updating an attachment, CouchDB requires the MVCC token
		from the owning document.  This helper sets that token and generates the
		resource URI.
		"""
		return Attachment.new(self.url() + "/" + urllib.quote_plus(name), _rev=self._rev)
	
	def remove_attachment(self, name):
		"""
		Remove the attachment from the attachments dict.  Throws a
		KeyError if the attachment isn't found in the _attachments
		dict.
		"""
		self._attachments.pop(name)

class Changes(Resource):
	""" Shortcut for accessing a database's _changes API
		Use: (given a database called 'fruits')
		changed_docs = client.Changes.find("fruits", since=[15,151,16])
		('since' is a vector rather than a single revision when using the 
		lounge)
		"""

	@classmethod
	def make_key(cls, dbname, since=None):
		cls._db_name = db_prefix + dbname
		cls._since = since
		return "_changes"

	def _get(self):
		args = {}
		if self._since: args = {'since': self._since}
		return Resource._get(self, args)

	@classmethod
	def find(cls, dbname, since=None):
		inst = cls()
		inst._key = cls.make_key(dbname, since)
		inst._rec = inst._get()

		return inst
	
	def url(self):
		return get_db_connectinfo(self) + self._db_name + '/' + self._key

	

class DesignDoc(Document):
	def __init__(self):
		try:
			Document.__init__(self)
		except NotImplementedError:
			# trap the error for db_name not overridden.  that's ok
			pass

	@classmethod
	def make_key(cls, dbname, docname):
		cls.db_name = dbname
		return "_design/" + docname

	# we override the url method here because we have different quoting behavior from a regular document
	# if they do ever fix this in couchdb, we can revert this :)
	def url(self):
		return get_db_connectinfo(self) + self._db_name + '/' + self._key

class TuplyDict(object):

	def __init__(self, row_dict):
		self._dict = row_dict
		
	def __contains__(self, item):
		return (item == 0) or (item == 1) or item in self._dict
	
	def __getitem__(self, key):
		if key == 0 or key == 1:
			return self._keyvalue[key]
		else:
			return self._dict[key]
			
	def __cmp__(self, obj):
		if isinstance(obj, tuple):
			return cmp(self._keyvalue, obj)
		else:
			return cmp(self._dict, obj._dict)
				
	def __iter__(self):
		""" We only iterate over the fake key,value tuple,
		 	for backwards compatibility
		"""
		return self._keyvalue.__iter__()
		
	@property
	def _keyvalue(self):
		return (self._dict['key'], self._dict['value'])

	def __repr__(self):
		return "TuplyDict(%s)" % repr(self._dict)

	def __str__(self):
		return str(self._dict)

class View(Resource):
	def __init__(self, db_name):
		Resource.__init__(self)
		self._db_name = db_prefix + db_name

	def url(self):
		return get_db_connectinfo(self) + self._db_name + '/' + self._key

	@classmethod
	def make_key(cls, name):
		doc, view = name.split('/')
		return '_design/' + doc + '/_view/' + view

	@classmethod
	def execute(cls, db_name, *key, **kwargs):
		inst = cls(db_name)
		inst.db_connectinfo = kwargs.pop('db_connectinfo', None)
		inst._key = cls.make_key(*key)
		args = None
		if 'args' in kwargs:
			args = copy.deepcopy(kwargs.pop('args'))
			for k,v in args.iteritems():
				# stale=ok is not json-encoded, but stuff like
				#	startkey=["one", "two"] is json-encoded.
				if k!='stale':
					# json-encode the args
					args[k] = cjson.encode(v)
		#this sets the post-body to the arguments of the view (so it's actually not a no-op)
		#this behaviour is used in TempView below
		inst._rec = kwargs
		inst._rec = inst.get_results(args)
		try:
			inst._rec['rows'] = [TuplyDict(row) for row in inst._rec['rows']]
		except TypeError:
			raise TypeError("Expected a JSON object with 'rows' attribute, got %s" % str(inst._rec))
		return inst

	def get_results(self, args):
		return self._request('GET', self.url(), args=args)

	def save(self, **kwargs):
		raise NotImplementedError

class TempView(View):
	@classmethod
	def make_key(cls):
		return '_temp_view'
	
	def get_results(self, args):
		return self._request('POST', self.url(), args=args, body=self._rec)

class AllDocView(View):
	@classmethod
	def make_key(cls):
		return '_all_docs'

class BulkDocView(View):
	@classmethod
	def make_key(cls):
		return '_all_docs'

	def get_results(self, args):
		return self._request('POST', self.url(), args=args, body=self._rec)

	@classmethod
	def fetch(cls, db, keys):
		"""Convenience method for fetching documents.  Automatically sets include_docs"""
		return cls.execute(db, keys=keys, args=dict(include_docs=True))

class Attachment(Resource):
	"""A Resource with special encoding.

	needs:
	`content_type` -- mime type to use when storing the attachment
	and either of:
	`data` -- raw data to store
	`stream` -- file-type object with data

	When retrieving an attachment, you'll always get a stream.
	"""
	def _encode(self, payload):
		content_type = payload['content_type']
		if 'data' in payload:
			data = payload['data']
		else:
			data = payload['stream'].read()
		return content_type, data
	
	def _decode(self, data, content_type='application/octet-stream'):
		return {
			"content_type": content_type,
			"stream": StringIO.StringIO(data)
		}

	def _put(self, args=None):
		if args is None:
			args = {}
		args["rev"] = self._rec["_rev"]
		result = self._request('PUT', self.url(), args=args, body=self._rec)
		return result
