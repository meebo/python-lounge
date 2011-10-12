# build number, increment with each new build, reset on new version
RELEASE = 2`rpm --eval "%{?dist}"`

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
	python setup.py bdist_rpm --release="$(RELEASE)"

.PHONY: test
test:
	cd test ; python lounge_test.py

.PHONY:	clean
clean:
	rm -f MANIFEST
	rm -rf dist build
