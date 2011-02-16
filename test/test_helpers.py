from lounge.client import *

# these keys cover all 128 shards
shard_keys = ['x152', 'x116', 'x67', 'x23', 'x22', 'x66', 'x117', 'x153', 'x139', 'x151', 'x20', 'x64', 'x65', 'x21', 'x150', 'x138', 'x74', 'x30', 'x141', 'x129', 'x128', 'x140', 'x31', 'x75', 'x33', 'x77', 'x106', 'x142', 'x143', 'x107', 'x76', 'x32', 'x180', 'x79', 'x124', 'x160', 'x161', 'x125', 'x78', 'x181', 'x56', 'x183', 'x163', 'x127', 'x126', 'x162', 'x182', 'x57', 'x137', 'x173', 'x193', 'x46', 'x47', 'x192', 'x172', 'x136', 'x170', 'x134', 'x69', 'x190', 'x191', 'x68', 'x135', 'x171', 'x166', 'x122', 'x53', 'x186', 'x187', 'x52', 'x123', 'x167', 'x121', 'x165', 'x185', 'x50', 'x51', 'x184', 'x164', 'x120', 'x40', 'x195', 'x175', 'x131', 'x130', 'x174', 'x194', 'x41', 'x196', 'x43', 'x132', 'x176', 'x177', 'x133', 'x42', 'x197', 'x25', 'x61', 'x110', 'x178', 'x179', 'x111', 'x60', 'x24', 'x62', 'x26', 'x157', 'x113', 'x112', 'x156', 'x27', 'x63', 'x103', 'x147', 'x36', 'x72', 'x73', 'x37', 'x146', 'x102', 'x168', 'x100', 'x71', 'x188', 'x189', 'x70', 'x101', 'x169']

# these keys all map to shard 0 (for testing temporary views)
shard0_keys = ['x152', 'x223', 'x551', 'x620', 'x895', 'x905', 'x929', 'x1006', 'x1196', 'x1377', 'x1405', 'x1429', 'x1595', 'x1758', 'x1774', 'x1851', 'x2156', 'x2227', 'x2555', 'x2579', 'x2608', 'x2624', 'x2798', 'x2891', 'x2901', 'x3005', 'x3029', 'x3195', 'x3358', 'x3374', 'x3406', 'x3596', 'x3777', 'x3852', 'x4087', 'x4117', 'x4266', 'x4484', 'x4514', 'x4538', 'x4649', 'x4665', 'x4940', 'x5044', 'x5068', 'x5289', 'x5319', 'x5335', 'x5447', 'x5736', 'x5813', 'x5983', 'x6084', 'x6114', 'x6138', 'x6249', 'x6265', 'x6487', 'x6517', 'x6666', 'x6943', 'x7047', 'x7336', 'x7444', 'x7468', 'x7689', 'x7719', 'x7735', 'x7810', 'x7980', 'x8041', 'x8330', 'x8442', 'x8733', 'x8816', 'x8986', 'x9082', 'x9112', 'x9263', 'x9481', 'x9511', 'x9660', 'x9945', 'x9969', 'x10030', 'x10341', 'x10433', 'x10742', 'x10867', 'x11163', 'x11212', 'x11382', 'x11560', 'x11611', 'x11781', 'x11888', 'x11918', 'x11934', 'x12033', 'x12342', 'x12430', 'x12741']

class TestDoc(Document):
	db_name = "pytest"

class MultiKey(Document):
	"""Test doc type that build a key from multiple args."""
	db_name = "pytest"

	@classmethod
	def make_key(cls, first, second):
		return "%s:%s" % (first, second)

def create_test_db(name):
	try:
		db = Database.find(name)
		db.destroy()
	except NotFound:
		pass
	return Database.create(name)

def assert_raises(exception, function, *args, **kwargs):
	"""Make sure that when you call function, it raises exception"""
	try:
		function(*args, **kwargs)
		assert False, "Should have raised %s" % exception
	except exception:
		pass
