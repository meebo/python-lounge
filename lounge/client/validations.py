import re
from copy import copy

def max_length(attr, max, msg=None):
	""" Verify that length of attribute is less than 'max' """
	if msg is None:
		msg = 'length of %s must be <= %d' % (attr, max)

	return test(attr, lambda x: len(x) <= max, msg)

def min_length(attr, min, msg=None):
	""" Verify that length of attribute is greater than 'min' """
	if msg is None:
		msg = 'length of %s must be >= %d' % (attr, min)

	return test(attr, lambda x: len(x) >= min, msg)

def is_type(attr, typ, msg=None):
	def f(x):
		return isinstance(x, typ)
	if msg is None:
		msg = 'type of %s must be %s' % (attr, typ.__name__)
	return test(attr, f, msg)

def max_int(attr, max, msg=None):
	if msg is None:
		msg = 'value of %s must be <= %d' % (attr, max)

	return test(attr, lambda x: int(x) <= max, msg)

def min_int(attr, min, msg=None):
	if msg is None:
		msg = 'value of %s must be >= %d' % (attr, min)

	return test(attr, lambda x: int(x) >= min, msg)

def extended_getattr(obj, attr):
	"""Like getattr, but dereferences list indices."""
	index = None
	if '[' in attr:
		attr, index = attr.split('[', 1)
		index = int(index.strip(']'))
	val = getattr(obj, attr)
	if index is not None:
		val = val[index]
	return val

def strip_index(attr):
	"""Remove the index from an attribute."""
	if '[' in attr:
		return attr.split('[', 1)[0]
	return attr

def exists(attr, msg=None):
	"""Generate a validation function that verifies an attribute has been set."""
	def f(self):
		if attr not in self._rec:
			the_msg = msg
			if the_msg is None:
				the_msg = '%s must exist' % attr
			self.set_error(attr, the_msg)
			return False
		return True
	return f

def test(attr, predicate, msg):
	"""Generate an attribute validation method.

	Return a function that checks the value of some attribute.  You provide
	a predicate that accepts the value of the attribute and returns 
	True or False depending on whether value is acceptable.
	"""
	def f(self):
		try:
			val = extended_getattr(self, attr)
		except AttributeError:
			# we don't check for existence; just check the content if it does exist
			return True

		if not predicate(val):
			self.set_error(strip_index(attr), msg)
			return False
		return True
	return f

def not_empty(attr, msg=None):
	"""Verify that a list/set/dict/tuple attribute has something in it."""
	if msg is None:
		msg = '%s should not be empty' % attr
	return test(attr, lambda x: len(x)>0, msg)

def matches(attr, pattern, msg=None):
	if msg is None:
		msg = '%s is not in the required format' % attr
	# we do 'and True' so that is returns a bool, not a match object
	return test(attr, lambda x: (re.match(pattern, x) and True), msg)

def not_blank(attr, msg=None):
	if msg is None:
		msg = '%s should not be blank' % attr
	return matches(attr, r'.*\S', msg)

def _get_validation_fn(attr, method):
	"""
	If the method is a tuple, the first argument will be a validation
	generator, and the rest will be added as arguments to the
	validation generator.
	"""
	# turn this validation generator into an actual function
	if isinstance(method, tuple):
		# we have args for the validation func maker
		validation_fn_maker, validation_args = method[0], method[1:]
	else:
		# no args needed
		validation_fn_maker = method
		validation_args = ()
	return validation_fn_maker(attr, *validation_args)

def at_least_one(attr, *validations):
	""" Build a validation function that chains multiple helpers.  At
	least one of the helpers must pass.
	e.g.
	validate_delicious_food = at_least_one('kind', (matches, r'mexican'), (matches, r'indian'))
	"""
	def f(self):
		status = False
		errors_old = copy(self._errors)

		for method in validations:
			validation_fn = _get_validation_fn(attr, method)
			# execute the actual validation
			status = validation_fn(self) or status

		# If our status is True, we need to reset our errors to
		# what they were before because it's OK for tests to fail
		# as long as at least one passes.
		if status:
			self._errors = errors_old

		return status
	return f

def ensure_all(attr, *validations):
	"""Build a validation function that can chain multiple helpers.
	For this to pass, all of the helpers must pass.
	e.g.
	validate_phone = ensure_all('phone_number', exists, (matches, r'\d\d\d-\d\d\d\d-\d\d\d\d'))
	"""
	def f(self):
		status = True
		for method in validations:
			validation_fn = _get_validation_fn(attr, method)
			# execute the actual validation
			status = validation_fn(self) and status
		return status
	return f

def each(attr, *validation_builder):
	"""Build a validation function that applies a validation to each element of a list."""
	def f(self):
		status = True
		validation_fn_maker, validation_args = validation_builder[0], validation_builder[1:]

		try:
			lst = getattr(self, attr)
		except AttributeError:
			# we don't check for existence; just check the content if it does exist
			return True
		for i in range(len(lst)):
			validation_fn = validation_fn_maker('%s[%d]' % (attr, i), *validation_args)
			status = validation_fn(self) and status
		return status
	return f
