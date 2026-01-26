Installation
============

Requirements
------------

* macOS (this package uses ``pyobjc`` / ``AppKit``)
* iTerm2 installed
* Python 3.13 or higher

Enable the iTerm2 Python API
----------------------------

To use the iTerm2 Python API, iTerm2 must be running and the Python API must be enabled.
See iTerm2's documentation for the exact preference name and location (it has moved
between iTerm2 releases).

At a minimum:

* iTerm2 must be running
* iTerm2 must allow Python API connections

Install from PyPI
-----------------

If you only want the library + CLI:

.. code-block:: bash

   pip install iterm2-api-wrapper

Install from source
-------------------

Clone the repository and install with pip:

.. code-block:: bash

   git clone https://github.com/iLiftALot/iterm2-api-wrapper.git
   cd iterm2-api-wrapper
   pip install -e .

Dependencies
------------

The following runtime dependencies are installed automatically (see ``pyproject.toml``):

* ``typer`` - CLI framework
* ``iterm2`` - iTerm2 Python API
* ``pyobjc`` - macOS bridge used for ``AppKit``
* ``py-applescript`` - running AppleScript (.scpt) helpers
