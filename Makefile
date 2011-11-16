# build number, increment with each new build, reset on new version
DIST := $(shell rpm --eval "%{?dist}")
RELEASE := 1
ifeq ($(DIST),el5)
	REQUIRES = python-httplib2, python-simplejson
else
	REQUIRES = python-httplib2
endif

PY_VERSION := $(shell python -V 2>&1)
ifeq ($(strip $(DESTDIR)),)
	root=
else
	root=--root $(DESTDIR)
endif

.PHONY:	default install rpm

default:
	python setup.py build

install:
	python setup.py install $(root)

rpm:
	python setup.py bdist_rpm --release="$(RELEASE)$(DIST)" \
		--requires "$(REQUIRES)"

.PHONY: test
test:
	cd test ; python lounge_test.py

.PHONY:	clean
clean:
	rm -f MANIFEST
	rm -rf dist build
