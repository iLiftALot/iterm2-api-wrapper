Usage
=====

Command Line Interface
----------------------

After installation, you can use the ``iterm2_api_wrapper`` (or ``it2w``) command:

.. code-block:: bash

   it2w --help

Functions
---------

The current CLI intentionally keeps a small surface area and dispatches a single
argument (``func_name``) to a handful of built-in async actions.

Show iTerm2 capabilities:

.. code-block:: bash

   it2w show_capabilities

Send one or more commands to the active iTerm2 session:

.. code-block:: bash

   it2w send_command "pwd" "ls -la"

Show UI alerts (requires iTerm2 in the foreground):

.. code-block:: bash

   it2w alert
   it2w text_input_alert
   it2w poly_modal_alert
   it2w all_alerts

Basic Commands
--------------

Run the CLI help:

.. code-block:: bash

   it2w --help

Configuration
-------------

The wrapper selects iTerm2 objects at runtime (window/tab/session). If you are
contributing to the project, see the integration tests for environment variables
used to control timeouts and enable/disable tests.

