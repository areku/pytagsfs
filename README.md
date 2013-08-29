===============
pytagsfs README
===============

-----------------------
http://www.pytagsfs.org
-----------------------


pytagsfs is a FUSE filesystem that arranges media files in a virtual directory
structure based on the file tags. For instance, a set of audio files could be
mapped to a new directory structure organizing them hierarchically by album,
genre, release date, etc. File tags can be changed by moving and renaming
virtual files and directories. The virtual files can also be modified directly,
and, of course, can be opened and played just like regular files.

This file may be distributed under the same license as pytagsfs itself.


Dependencies
============

pytagsfs has the following dependencies:

 * Python (2.4, 2.5, or 2.6): http://www.python.org/
 * sclapp (>= 0.5.2): http://www.alittletooquiet.net/software/sclapp
 * python-fuse (>= 0.2): http://fuse.sourceforge.net/wiki/index.php/FusePython
 * mutagen: http://www.sacredchao.net/quodlibet/wiki/Development/Mutagen

One of the following filesystem monitoring libraries should also be installed:

 * inotifyx (Linux only): http://www.alittletooquiet.net/software/inotifyx/
 * py-kqueue (Darwin, FreeBSD, NetBSD, OpenBSD):
   http://pypi.python.org/packages/source/p/py-kqueue/
 * gamin (many Unix-like systems, inotifyx and py-kqueue are preferred):
   http://www.gnome.org/~veillard/gamin/

To run the test suite, the following additional dependencies must be fulfilled:

 * madplay: http://www.underbit.com/products/mad/
 * vorbis-tools (for ogg123): http://www.vorbis.com/
 * flac: http://flac.sourceforge.net/
 * ctypes (Python 2.4 only): http://python.net/crew/theller/ctypes/


Installing
==========

Before installing from source, check if your distribution has packages
available.  It is not normally recommended that you install packages from
source in system-wide directories, unless you know what you're doing.

To build::

  ./setup.py build

To install::

  ./setup.py install

To clean up temporary files created while building or testing::

  ./setup.py clean

To clean all files, including built files that are required for installation::

  ./setup.py clean --all


Documentation
=============

Manual pages for both the pytagsfs and pytags commands are built via ``setup.py
build``.  Please refer to those, as well as the pytagsfs website, for
documentation.


Running Tests
=============

Tests can be run via setup.py::

  ./setup.py test

Specific tests can be specified on the command-line.  For instance, to only run
tests defined in module tests.subspat::

  ./setup.py test --tests tests.subspat

To only run tests defined by test case ShortKeySubstitutionPatternTestCase::

  ./setup.py test --tests tests.subspat.ShortKeySubstitutionPatternTestCase

To only run a specific test defined by that test case::

  ./setup.py test --tests tests.subspat.ShortKeySubstitutionPatternTestCase.testSplit

Multiple identifiers can be specified using a comma-separated list.


See Also
========

* AUTHORS
* BUGS
* COPYING
* NEWS
* TODO
