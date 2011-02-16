#!/usr/bin/python

import logging
import os
import sys
import time
import urllib2

# prepend the location of the local python-lounge
# the tests will find the local copy first, so we don't
# have to install system-wide before running tests.
sys.path = ['..'] + sys.path

from unittest import TestCase, main
from test_helpers import *

from lounge import client
from lounge.client.validations import *

def get_data_and_headers(url):
	req = urllib2.urlopen(url)
	return req.read(), dict(req.headers)

class LoungeTestCase(TestCase):
	"""Guarantees a clean database for each test."""
	def setUp(self):
		use_config(os.environ.get("LOUNGE", "dev"), testing=True)
		create_test_db("pytest")

	def tearDown(self):
		time.sleep(0.5)
		Database.find("pytest").destroy()

	def testTimeout(self):
		""" Test that we properly throw an error on a timeout.

		Make sure that you have the most recent version of httplib2 before
		running this test, as older versions threw less-informative
		exceptions. """
		old_dbtimeout = client.db_timeout
		client.db_timeout = 0.000000000000000001
		self.assertRaises(client.RequestTimedOut, TestDoc.create, 'hellothere')
		client.db_timeout = old_dbtimeout

	def testConnectionRefused(self):
		""" Test that we properly throw an error when the connection is refused. """
		old_dbconnectinfo = client.db_connectinfo
		client.db_connectinfo = "http://localhost:98765/"
		self.assertRaises(client.SocketError, TestDoc.create, "hellothere")
		client.db_connectinfo = old_dbconnectinfo
		
	def testLargeDocs(self):
		"""Test PUTing and GETing large documents"""
		manykeys = TestDoc.new('manykeys')
		largevalues = TestDoc.new('largevalues')
		largekeys = TestDoc.new('largekeys')

		for i in xrange(10000):
			manykeys[str(i)] = str(i*2)
		manykeys.save()

		bigthings = ['one', 'two']
		for i in xrange(10000):
			bigthings[0] += str(i)
			bigthings[1] += str(-i)

		largevalues['one'] = bigthings[0]
		largevalues['two'] = bigthings[1]
		largevalues.save()

		largekeys[bigthings[0]] = 'one'
		largekeys[bigthings[1]] = 'two'
		largekeys.save()

		TestDoc.find('manykeys')
		TestDoc.find('largevalues')
		TestDoc.find('largekeys')
		
	def testBulkDocGet(self):
		"""Test bulk document retrieval"""

		a = TestDoc.create("a", x=1, y=1)
		b = TestDoc.create("b", x=2, y=4)
		c = TestDoc.create("c", x=3, y=9)
		d = TestDoc.create("d", x=4, y=16)

		view = BulkDocView.fetch("pytest", ["a", "d"])
		self.assertEqual(len(view.rows), 2)
		self.assertEqual(view.rows[0][0], 'a')
		self.assertEqual(view.rows[1][0], 'd')

	def testBasics(self):
		"""Test some basic read/write operations."""
		a = TestDoc.create("a", x=1, y=1)
		b = TestDoc.create("b", x=2, y=4)
		c = TestDoc.create("c", x=3, y=9)
		d = TestDoc.create("d", x=4, y=16)

		db = Database.find("pytest")
		assert db.doc_count==4, "pytest should have 4 records but has %d" % db.doc_count

		# delete some records
		b.destroy()
		d.destroy()

		assert_raises(NotFound, TestDoc.find, "b")

		db.reload()
		assert db.doc_count==2, "pytest should have 2 records but has %d" % db.doc_count

		# test _all_docs
		view = AllDocView.execute("pytest")
		assert view.total_rows==2
		assert len(view.rows)==2
		assert view.rows[0][0]=='a'
		assert view.rows[1][0]=='c'

	def testAllShards(self):
		"""Write to and read from each shard."""
		# put something in each shard
		for i,key in enumerate(shard_keys):
			x = TestDoc.create(key, index=i)

		for i,key in enumerate(shard_keys):
			y = TestDoc.find(key)
			assert y.index==i, "Shard %d: expected %d, got %d" % (i, i, TestDoc.index)

		for i,key in enumerate(shard_keys):
			TestDoc.find(key).destroy()
	
	def testMultiKey(self):
		# test PUT
		a = MultiKey.create("one", "two", x=2, y=3)
		# GET
		x = MultiKey.find("one", "two")
		assert x._id=="one:two"
		assert x.x==2
		assert x.y==3

		# PUT (update)
		x.z = 4
		x.save()
		assert MultiKey.find("one", "two").z==4

		# and DELETE
		MultiKey.find("one", "two").destroy()
		assert_raises(NotFound, MultiKey.find, "one", "two")

	def testUpdate(self):
		"""Try to update a record ..."""
		a = TestDoc.create("a11", x=1, y=2)
		a.save()

		assert a.x == 1
		a.update(dict(x=3,z=3))

		assert a.x == 3
		assert a.z == 3

	def testContains(self):
		"""Check if the 'in' operator works """
		a = TestDoc.create("a22", x=1)
		assert 'x' in a
		assert 'y' not in a

	def testSetGetItem(self):
		"""Test the implementation of self[key]"""
		a = TestDoc.create("a")
		a['x'] = "hi"
		assert 'x' in a
		assert a['x'] == "hi"

	def testSaveAgain(self):
		"""Create a document, then try saving again.

		If our method of getting revision numbers is wrong, the second save
		will raise an exception.
		"""
		a = TestDoc.create("a", x=1, y=2)
		a.z = 3
		a.save()
		a.w = 4
		a.save()
		aa = TestDoc.find("a")
		assert aa.z==3
		assert aa.w==4

		# clean up
		TestDoc.find("a").destroy()
	
	def testConflict(self):
		"""Try to save conflicting revisions of a document."""
		TestDoc.create("a1", x=1, y=2)
		a1, a2 = TestDoc.find("a1"), TestDoc.find("a1")
		a1.y = 3
		a1.save()
		a2.x = 1
		# This save is out of date.  We should get a RevisionConflict
		assert_raises(RevisionConflict, a2.save)

		# clean up
		TestDoc.find("a1").destroy()
	
	def dontTestTempView(self):
		"""Run a temporary view.

		Note, since this test doesn't start with 'test', it's disabled.
		Looks like there's a bug with smartproxy and temporary views, but
		we don't really use temp views."""
		k1, k2, k3, k4, k5 = shard0_keys[0:5]

		TestDoc.create(k1, x=1, y=2)
		TestDoc.create(k2, x=1, y=4)
		TestDoc.create(k3, x=2, y=6)
		TestDoc.create(k4, x=3, y=8)
		TestDoc.create(k5, x=4, y=10)

		view = TempView.execute('pytest', language="javascript", map="(function (doc) {if (doc.x == 1) {emit(doc._id, doc.y);}})")
		assert view.total_rows==2
		assert len(view.rows)==2
		assert view.rows[0]==(k1, 2)
		assert view.rows[1]==(k2, 4)

		# add another doc and make sure our results update appropriately
		doc3 = TestDoc.find(k3)
		doc3.x = 1
		doc3.save()

		view = TempView.execute('pytest', language="javascript", map="(function (doc) {if (doc.x == 1) {emit(doc._id, doc.y);}})")
		assert view.total_rows==3
		assert view.rows[2]==(k3, 6)

		# clean up for the next test
		for k in [k1,k2,k3,k4,k5]:
			TestDoc.find(k).destroy()
	
	def testView(self):
		"""Create and run a permanent view."""
		DesignDoc.create("pytest", "test", language="javascript", views={"test1": {"map": "(function (doc) {if (doc.x == 1) {emit(doc._id, doc.y);}})"}})

		# while waiting for the design doc to sync, insert some records.
		TestDoc.create("a", x=1, y=1)
		TestDoc.create("b", x=2, y=2)
		TestDoc.create("c", x=1, y=3)
		TestDoc.create("d", x=2, y=4)
		TestDoc.create("e", x=1, y=5)

		# wait up to 30 seconds for sync.  if it goes 30 seconds, there is a 
		# problem with replication
		tries = 0
		view = None
		while view is None:
			tries += 1
			assert tries<30, "Design document never replicated after 30+ seconds."
			try:
				view = View.execute('pytest', 'test/test1')
			except NotFound:
				view = None
				time.sleep(1)

		assert view.total_rows==3
		assert view.rows[0]==("a", 1)
		assert view.rows[1]==("c", 3)
		assert view.rows[2]==("e", 5)

		# test slicing a view
		view = View.execute('pytest', 'test/test1', args={'startkey': 'c', 'endkey': 'e'})
		assert view.total_rows==3
		assert len(view.rows)==2
		assert view.rows[0]==("c", 3)
		assert view.rows[1]==("e", 5)

		# test fetching a single key
		view = View.execute('pytest', 'test/test1', args={'key': 'a'})
		assert view.total_rows==3
		assert len(view.rows)==1
		assert view.rows[0]==("a", 1)

		# update a doc to add a new row to the
		doc_d = TestDoc.find("d")
		doc_d.x = 1
		doc_d.save()

		view = View.execute('pytest', 'test/test1', args={'startkey': 'c', 'endkey': 'e'})
		assert view.total_rows==4
		assert len(view.rows)==3
		assert view.rows[0]==("c", 3)
		assert view.rows[1]==("d", 4)
		assert view.rows[2]==("e", 5)

		for k in ['a','b','c','d','e']:
			TestDoc.find(k).destroy()
	
	def testFindOrNew(self):
		x = TestDoc.find_or_new('xyzzy')
		# new records have no _rev
		assert '_rev' not in x._rec
		x.cheese = 'good'
		x.save()

		x = TestDoc.find_or_new('xyzzy')
		# existing records do have a _rev
		assert '_rev' in x._rec
		assert x.cheese=='good'
		
	def testIncludeDocs(self):
		"""Create and run a permanent view with include_docs."""
		DesignDoc.create("pytest", "test", language="javascript", views={"test1": {"map": "(function (doc) {if (doc.x == 1) {emit(doc._id, doc.y);}})"}})

		# while waiting for the design doc to sync, insert some records.
		TestDoc.create("a", x=1, y=1)
		TestDoc.create("b", x=2, y=2)
		TestDoc.create("c", x=1, y=3)
		TestDoc.create("d", x=2, y=4)
		TestDoc.create("e", x=1, y=5)

		# wait up to 30 seconds for sync.  if it goes 30 seconds, there is a 
		# problem with replication
		tries = 0
		view = None
		while view is None:
			tries += 1
			assert tries<30, "Design document never replicated after 30+ seconds."
			try:
				view = View.execute('pytest', 'test/test1', args={"include_docs":True})
			except NotFound:
				view = None
				time.sleep(1)

		assert view.total_rows==3
		assert view.rows[0]==("a", 1)
		assert view.rows[1]==("c", 3)
		assert view.rows[2]==("e", 5)

		assert "doc" in view.rows[0]
		assert view.rows[0]['doc']['y'] == 1
		assert "doc" in view.rows[1]
		assert view.rows[1]['doc']['y'] == 3
		assert "doc" in view.rows[2]
		assert view.rows[2]['doc']['y'] == 5

		# test slicing a view
		view = View.execute('pytest', 'test/test1', args={'startkey': 'c', 'endkey': 'e'})
		assert view.total_rows==3
		assert len(view.rows)==2
		assert view.rows[0]==("c", 3)
		assert view.rows[1]==("e", 5)

		# test fetching a single key
		view = View.execute('pytest', 'test/test1', args={'key': 'a'})
		assert view.total_rows==3
		assert len(view.rows)==1
		assert view.rows[0]==("a", 1)

		# update a doc to add a new row to the
		doc_d = TestDoc.find("d")
		doc_d.x = 1
		doc_d.save()

		view = View.execute('pytest', 'test/test1', args={'startkey': 'c', 'endkey': 'e'})
		assert view.total_rows==4
		assert len(view.rows)==3
		assert view.rows[0]==("c", 3)
		assert view.rows[1]==("d", 4)
		assert view.rows[2]==("e", 5)

		for k in ['a','b','c','d','e']:
			TestDoc.find(k).destroy()
	
	def testDefaults(self):
		class DefDoc(Document):
			defaults = { "cheeses": [] }
			db_name = "pytest"

		one = DefDoc.new("first")
		one.cheeses.append("gouda")
		one.cheeses.append("cheddar")
		one.save()

		two = DefDoc.new("second")
		assert two.cheeses==[]
	
	def testSpacesInKey(self):
		a = MultiKey.new("one", " a b c ", x=1, y=2, z=3)
		a.save()
		b = MultiKey.find("one", " a b c ")
		assert b.x==1
		assert b.y==2
		assert b.z==3
	
	def testUnicodeKey(self):
		name = u'm\xf4t\xf4rhead'
		a = MultiKey.new("one", name, x=1, y=2)
		a.save()
		b = MultiKey.find("one", name)
		assert b.x==1
		assert b.y==2
	
	def testZeroResponseCode(self):
		# nginx will give us a zero response code in some weird circumstances.
		# we should treat it like a 400
		#assert_raises(LoungeError, Resource.find, db_connectinfo + "pytest/a b c")
		pass
	
	def testAttachment(self):
		a = TestDoc.create("a", x=1, y=1)	
		b = a.new_attachment("b.gif")
		b.content_type = "image/gif"
		b.stream = open("fixtures/b.gif")
		b.save()

		# Need to reload after we save b to get the new revision number
		a.reload()

		assert b.url().endswith("/a/b.gif"), "Attachment url '%s' is wonky" % b.url()
		b = a.get_attachment('b.gif')

		assert b.content_type=='image/gif', "Attachment should be image/gif, is %s" % b.content_type
		assert b.stream.getvalue()==open("fixtures/b.gif").read(), "Attachment should match b.gif"
		
		a.remove_attachment('b.gif')
		a.save()
		assert_raises(NotFound, a.get_attachment, 'b.gif')

	def testValidation(self):
		class CoolDoc(Document):
			db_name = "pytest"
 
			# test some helper functions for common validations
			validate_x = exists("x")
			validate_y = ensure_all("y", exists, not_blank)
			validate_z = matches("z", r'^[abc]\d+[ghi]$', "Z should match some random format") 
			validate_xyz = ensure_all("xyz", exists, (matches, r'^[abc]+$'))
			validate_abc = test("abc", lambda x: x%3==0, "abc should be a multiple of 3")

			# If you don't require 'exists', then the test()
			# attributes will all return true when the value
			# doesn't exist (not correct, since we're doing an
			# OR, not an AND)
			validate_msg = ensure_all('msg', 
						  exists, 
						  (at_least_one,
						  (min_length, 10),
						  (matches, r'^chinese$'), (matches, r'^food$')))

			validate_str_min = min_length('str_min', 5)
			validate_str_max = max_length('str_max', 7)
			validate_str_minmax = ensure_all('str_minmax',
							 (min_length, 5),
							 (max_length, 7))

			validate_isint = is_type('isint', int)
			validate_isfloat = is_type('isfloat', float)
			validate_int_min = min_int('int_min', 5)
			validate_int_max = max_int('int_max', 5)
			validate_int_minmax = ensure_all('int_minmax',
							 (min_int, 5),
							 (max_int, 10))

			# test a custom validation function
			def validate_what_is_in_x(self):
				if 'x' in self:
					if self.x==7 or self.x==9:
						self.set_error('x', 'X should not be 7 or 9')
						return False
				return True

		a = CoolDoc.new('one')
		assert not a.validate()
		assert 'x' in a._errors
		assert 'y' in a._errors
		assert 'msg' in a._errors
		# it's ok for z to not exist. but if it does exist, we check the format.
		assert 'z' not in a._errors
		assert 'xyz' in a._errors
		assert 'abc' not in a._errors
		
		a.abc = 4
		a.xyz = 'abcd'
		assert not a.validate()
		assert 'x' in a._errors
		assert 'y' in a._errors
		assert 'msg' in a._errors
		assert 'z' not in a._errors
		assert 'xyz' in a._errors
		assert 'abc' in a._errors
		self.assertEqual(a.errors_for('abc'), ['abc should be a multiple of 3'])
		self.assertEqual(a.errors_for('xyz'), ['xyz is not in the required format'])

		a.abc = 6
		a.x = 7
		a.xyz = 'abccba'
		assert not a.validate()
		assert a.errors_for('x')==['X should not be 7 or 9']
		assert 'y' in a._errors
		assert 'msg' in a._errors
		assert 'z' not in a._errors
		assert 'xyz' not in a._errors
		assert 'abc' not in a._errors

		a.x = "stuff"
		assert not a.validate()
		assert 'x' not in a._errors
		assert 'y' in a._errors
		assert 'msg' in a._errors
		assert 'z' not in a._errors

		a.y = "  \t"
		assert not a.validate()
		assert 'y' in a._errors
		assert 'msg' in a._errors
		assert a.errors_for('y')==['y should not be blank']

		a.y = "some thing"
		assert not a.validate()
		assert 'msg' in a._errors

		a.msg = 'chinese'
		assert a.validate()
		assert not a._errors
		
		a.msg = 'food'
		assert a.validate()
		assert not a._errors

		a.msg = 'short'
		assert not a.validate()
		assert 'msg' in a._errors

		a.msg = 'hellolongstring'
		assert a.validate()
		assert not a._errors

		a.z = "12345"
		assert not a.validate()
		assert a.errors_for('z')==["Z should match some random format"]

		a.z = "a123g"
		assert a.validate()
		assert not a._errors

		assert "_errors" not in a._rec

		a.isint = 'hello'
		assert not a.validate()
		assert a.errors_for('isint')
		
		a.isint = 1.5
		assert not a.validate()
		assert a.errors_for('isint')

		a.isint = 5
		assert a.validate()
		assert not a._errors

		a.isfloat = 'hello'
		assert not a.validate()
		assert a.errors_for('isfloat')
		
		a.isfloat = 5
		assert not a.validate()
		assert a.errors_for('isfloat')

		a.isfloat = 1.5
		assert a.validate()
		assert not a._errors

		a.str_min = 'fire'
		assert not a.validate()
		assert a.errors_for('str_min')
		
		a.str_min = 'fireman'
		assert a.validate()
		assert not a._errors

		a.str_max = 'firetrucks'
		assert not a.validate()
		assert a.errors_for('str_max')

		a.str_max = 'fire'
		assert a.validate()
		assert not a._errors

		a.str_minmax = 'fire'
		assert not a.validate()
		assert a.errors_for('str_minmax')

		a.str_minmax = 'firetrucks'
		assert not a.validate()
		assert a.errors_for('str_minmax')
		
		a.str_minmax = 'fireman'
		assert a.validate()
		assert not a._errors

		a.int_min = 4
		assert not a.validate()
		assert a.errors_for('int_min')
		
		a.int_min = 5
		assert a.validate()
		assert not a._errors

		a.int_max = 50
		assert not a.validate()
		assert a.errors_for('int_max')

		a.int_max = -10000
		assert a.validate()
		assert not a._errors

		a.int_minmax = -100
		assert not a.validate()
		assert a.errors_for('int_minmax')

		a.int_minmax = 100
		assert not a.validate()
		assert a.errors_for('int_minmax')
		
		a.int_minmax = 6
		assert a.validate()
		assert not a._errors

	def testListValidation(self):
		class CoolDoc(Document):
			validate_x = not_empty("x")
			validate_y = each("y", matches, r'^[abc]+$')

		a = CoolDoc.new('one', x=[], y=[])
		assert not a.validate()
		a.x = [1]
		assert a.validate()
		a.y = ['abc','abcd','ab']
		assert not a.validate()
		a.y = ['abc','abcb', 'ab']
		assert a.validate()

		class NewDoc(Document):
			validate_z = ensure_all("z",
				not_empty,
				(each, matches, r'^[abc]+$'))
		a = NewDoc.new('two', z=[])
		assert not a.validate()
		a.z = ['abc', 'abcd']
		assert not a.validate()

		a.z = ['abc', 'abcc']
		assert a.validate()
	
	def testChanges(self):
		a = TestDoc.create("a", x=1, y=1)
		b = TestDoc.create("b", x=2, y=4)
		c = TestDoc.create("c", x=3, y=9)
		d = TestDoc.create("d", x=4, y=16)

		result = Changes.find("pytest")
		changed_doc_ids = [row["id"] for row in result.results]
		self.assertEqual(sorted(changed_doc_ids), ["a","b","c","d"])

	def testDictMethods(self):
		class CoolDoc(Document): pass
		a = CoolDoc.new()
		a['one'] = 5
		assert(a.get('one',10) == 5)
		assert(a.get('two',10) == 10)
		a['two'] = 5
		assert(a.get('two',10) == 5)

	def testDbConnectInfo(self):
		class Default(Document):
			db_name = "pytest"
		class Specified(Document):
			db_name = "pytest"
			db_connectinfo = "http://brocalhost:187/"

		self.assertEqual(get_db_connectinfo(Default.new("blargh")), client.db_connectinfo)

		self.assertEqual(get_db_connectinfo(Specified.new("mlargh")), "http://brocalhost:187/")

		Default.create("whatever")
		self.assertRaises(client.LoungeError, Specified.create, "hellothere")

		Default.db_connectinfo = "http://yoyobeanbag/"
		self.assertEqual(get_db_connectinfo(Default.new("blargh")), "http://yoyobeanbag/")
		self.assertRaises(client.LoungeError, Default.create, "hellothere")

	def testPathMethods(self):
		class CoolDoc(Document): pass
		a = CoolDoc.new()
		a['one'] = {'two':{'three':'four'}}
		assert(a.get_path('one.two.three') == 'four')
		assert(a.get_path('one.two.three.four') == None)
		assert(a.get_path('two') == None)
		a.set_path('one.five.six','seven')
		assert(a['one']['two']['three'] == 'four')
		assert(a['one']['five']['six'] == 'seven')
		assert(a.get_path('one.five.six') == 'seven')

		# Shouldn't clobber non-dictionaries while traversing
		a['two'] = {'none':None, 'string':'string', 'integer':5}
		self.assertRaises(Exception, a.set_path, 'two.none.something', 'something')
		self.assertRaises(Exception, a.set_path, 'two.string.something', 'something')
		self.assertRaises(Exception, a.set_path, 'two.integer.something', 'something')
		a.set_path('two.nonexistant.something','something')

if __name__=="__main__":
	# log all REST calls if the DEBUG env var is set
	if os.environ.get("DEBUG",False):
		console = logging.StreamHandler()
		console.setLevel(logging.DEBUG)
		logging.basicConfig(level=logging.DEBUG, handler=console)
	
	use_config(os.environ.get("LOUNGE","dev"), testing=True)
	try:
		main()
	finally:
		# final cleanup
		try:
			time.sleep(0.5)
			Database.find("pytest").destroy()
			pass
		except:
			pass

# vi: noexpandtab ts=2 sw=2
