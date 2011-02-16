# build number, increment with each new build, reset on new version
RELEASE = 1`rpm --eval "%{dist}"`


PY_VERSION := $(shell python -V 2>&1)
PY_EXTRA = --install-script install.sh
ifeq ($(PY_VERSION), Python 2.3.4)
	PY_EXTRA=
endif

ifeq ($(strip $(DESTDIR)),)
	root=
else
	root=--root $(DESTDIR)
endif

.PHONY:	default install

default:
	python setup.py build

install:
	python setup.py install $(root)

rpm:
	python setup.py bdist_rpm --release="$(RELEASE)" --requires "httplib2" \
		--obsoletes "python-lounge < 2.1" --provides "python-lounge = %{version}" $(PY_EXTRA)

.PHONY: test
test:
	cd test ; python lounge_test.py

.PHONY:	clean
clean:
	rm -f MANIFEST
	rm -rf dist build
