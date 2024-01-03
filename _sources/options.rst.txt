Options
=======


ExecuteScriptOptions
--------------------

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


fetch_fn
--------

.. function:: fetch_fn(url, options)

   The fetch function interface

   :param url: The URL to fetch interface
   :type url: str
   :param options: The `fetch options <https://developer.mozilla.org/en-US/docs/Web/API/fetch#parameters>`_
   :type options: dict or None, optional
   :returns: The response text
   :rtype: str


log_fn
------

.. function:: log_fn(text)

   The log function interface

   :param text: The log text
   :type text: str


url_fn
------

.. function:: url_fn(url)

   The URL function interface

   :param url: The URL
   :type url: str
   :returns: The modified URL
   :rtype: str
