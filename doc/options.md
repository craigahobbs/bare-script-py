# Options


## ExecuteScriptOptions

~~~ {eval-rst}
.. class:: ExecuteScriptOptions

   The BareScript runtime options :class:`dict`

   .. attribute:: debug
      :type: bool, optional

      If true, execute in debug mode

   .. attribute:: fetchFn
      :type: callable, optional

      The :func:`fetch function <fetch_fn>`

   .. attribute:: globals
      :type: dict, optional

      The global variables

   .. attribute:: logFn
      :type: callable, optional

      The :func:`log function <log_fn>`

   .. attribute:: maxStatements
      :type: int, optional
      :value: 1e9

      The maximum number of statements; 0 for no maximum

   .. attribute:: statementCount
      :type: int, optional
      :value: 0

      The current statement count

   .. attribute:: urlFn
      :type: callable, optional

      The :func:`URL modifier function <url_fn>`

   .. attribute:: systemPrefix
      :type: str, optional

      The system include prefix
~~~


## Fetch Functions

~~~ {eval-rst}
.. function:: fetch_fn(request)

   The fetch function interface

   :param request: The `request model <library/model.html#var.vName='SystemFetchRequest'>`__
   :type url: dict
   :returns: The response text
   :rtype: str
~~~


~~~ {eval-rst}
.. autofunction:: bare_script.fetch_http
~~~


~~~ {eval-rst}
.. autofunction:: bare_script.fetch_read_only
~~~


~~~ {eval-rst}
.. autofunction:: bare_script.fetch_read_write
~~~


## Log Functions

~~~ {eval-rst}
.. function:: log_fn(text)

   The log function interface

   :param text: The log text
   :type text: str
~~~


~~~ {eval-rst}
.. autofunction:: bare_script.log_stdout
~~~


## URL Functions

~~~ {eval-rst}
.. function:: url_fn(url)

   The URL function interface

   :param url: The URL
   :type url: str
   :returns: The modified URL
   :rtype: str
~~~


~~~ {eval-rst}
.. autofunction:: bare_script.url_file_relative
~~~
