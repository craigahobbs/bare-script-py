# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
BareScript WSGI application
"""

from functools import partial
import posixpath
from pathlib import Path, PurePath
import re
import sys

from . import barescript_parse_script, execute_script, fetch_http, url_file_relative
from .library import string_encode_utf8


def wsgi_application(src, script_name, function_name, globals_=None, debug=False, max_statements=None, fetch_fn=fetch_http):
    """
    Create a WSGI application function from a BareScript application. The application script is
    executed once, and its application function is called for each request with the request's WSGI
    environ object. The environ object contains the WSGI environ's string, number, and boolean
    values, its "PATH_INFO" value is decoded as UTF-8, and its "wsgi.input" value is the request
    content string. If the application function fails, the response is "500 Internal Server
    Error" with the JSON error ``{"error": "UnexpectedError"}``. The application function
    returns a WSGI response object with a "status" string (e.g. "200 OK"), a "headers" array of
    [key, value] string arrays, and a "content" string or byte value array.

    :param src: The map of application source file POSIX paths (relative to the application
        source directory) to file content strings or bytes. Includes and :func:`systemFetch` calls
        read from this map before falling back to the fetch function.
    :type src: dict
    :param script_name: The application script's source file path
    :type script_name: str or ~pathlib.PurePath
    :param str function_name: The application function's global name
    :param globals_: Optional global variables
    :type globals_: dict or None
    :param bool debug: If true, execute in debug mode
    :param max_statements: Optional maximum number of statements for the application script
        execution and for each request
    :type max_statements: int or None
    :param fetch_fn: The :func:`fetch function <fetch_fn>` for resources not in the source map
        (default is :func:`fetch_http`)
    :type fetch_fn: callable or None
    :returns: The WSGI application function
    :raises ValueError: The application script or function is unknown
    """

    # Execute the application script
    app_src = {PurePath(path).as_posix(): content for path, content in src.items()}
    script_name = PurePath(script_name).as_posix()
    app_fetch_fn = partial(_fetch_src, app_src, fetch_fn)
    url_fn = partial(url_file_relative, script_name)
    app_globals = dict(globals_) if globals_ is not None else {}
    options = _script_options(app_globals, app_fetch_fn, url_fn, partial(print, file=sys.stderr), debug, max_statements)
    script_text = app_src.get(script_name)
    if script_text is None:
        raise ValueError(f'Unknown application script "{script_name}"')
    if isinstance(script_text, bytes):
        script_text = script_text.decode('utf-8')
    execute_script(barescript_parse_script(script_text, 1, script_name), options)

    # Get the application function
    app_fn = app_globals.get(function_name)
    if not callable(app_fn):
        raise ValueError(f'Unknown application function "{function_name}"')

    return partial(_wsgi_application, app_fn, app_globals, app_fetch_fn, url_fn, debug, max_statements)


def wsgi_load_source(root_dir, src_dirs):
    """
    Read an application's source directories into an application source map (see
    :func:`wsgi_application`). A source directory that doesn't exist is skipped, as are hidden files and
    directories (names that start with ".").

    :param root_dir: The application root directory
    :type root_dir: str or ~pathlib.Path
    :param src_dirs: The source directory paths, relative to the root directory
    :type src_dirs: list(str)
    :returns: The map of source file POSIX path, relative to the root directory, to file content bytes
    :rtype: dict
    """

    root_path = Path(root_dir)
    return {
        path.relative_to(root_path).as_posix(): path.read_bytes()
        for src_dir in src_dirs
        for path in _load_files(root_path / src_dir)
    }


def wsgi_load_statics(root_dir, static_dirs, index='index.html'):
    """
    Create an application's static file map - BareScript can't list the application source map, so
    the host passes the static file map to the application as a global, and the application adds a
    static request for each file. A static directory that doesn't exist is skipped, as are hidden files
    and directories (names that start with ".").

    :param root_dir: The application root directory
    :type root_dir: str or ~pathlib.Path
    :param dict static_dirs: The map of URL path prefix (e.g. "/" or "/static/") to static file
        directory path, relative to the root directory. A prefix without a trailing slash gets one.
    :param index: The index file name - an index file is also served at its directory's URL path
        (e.g. "/" for "/index.html"). If None, there are no index files.
    :type index: str or None
    :returns: The map of URL path to source file POSIX path, relative to the root directory
    :rtype: dict
    """

    root_path = Path(root_dir)
    statics = {}
    for url_prefix, static_dir in static_dirs.items():
        url_prefix = url_prefix if url_prefix.endswith('/') else url_prefix + '/'
        static_path = root_path / static_dir
        for path in _load_files(static_path):
            url_path = url_prefix + path.relative_to(static_path).as_posix()
            src_path = path.relative_to(root_path).as_posix()
            statics[url_path] = src_path
            if path.name == index:
                statics[url_path[:-len(index)]] = src_path
    return statics


# Helper to list a directory's files, in order, skipping hidden files and directories
def _load_files(dir_path):
    for path in sorted(dir_path.rglob('*')):
        if path.is_file() and not any(part.startswith('.') for part in path.relative_to(dir_path).parts):
            yield path


# The WSGI application function
def _wsgi_application(app_fn, app_globals, fetch_fn, url_fn, debug, max_statements, environ, start_response):
    wsgi_errors = environ.get('wsgi.errors')
    log_fn = partial(print, file=wsgi_errors) if wsgi_errors is not None else None
    try:
        # Create the script environ object - the path is decoded as UTF-8 and the request content is read as a string
        script_environ = {key: value for key, value in environ.items() if isinstance(value, _ENVIRON_TYPES)}
        if 'PATH_INFO' in script_environ:
            script_environ['PATH_INFO'] = _environ_utf8(script_environ['PATH_INFO'])
        # A request without a content length (e.g. chunked) is read to its end if the server terminates the input
        content_length = environ.get('CONTENT_LENGTH')
        if content_length:
            content = environ['wsgi.input'].read(int(content_length)) if int(content_length) > 0 else b''
        elif environ.get('wsgi.input_terminated'):
            content = environ['wsgi.input'].read()
        else:
            content = b''
        script_environ['wsgi.input'] = content.decode('utf-8', errors='replace')

        # Call the application function with a copy of the application globals
        options = _script_options(dict(app_globals), fetch_fn, url_fn, log_fn, debug, max_statements)
        status, headers, content = _wsgi_response(app_fn([script_environ], options))
    except Exception as exc: # pylint: disable=broad-exception-caught
        if log_fn is not None:
            log_fn(f'BareScript WSGI application error: {exc}')
        status = '500 Internal Server Error'
        headers = [('Content-Type', 'application/json')]
        content = b'{"error":"UnexpectedError"}'

    # Respond - a HEAD response has no content, but its content length is the GET response's (except for a status
    # that never has content - 1xx and 204)
    if environ.get('REQUEST_METHOD', '').upper() == 'HEAD':
        if not status.startswith(('1', '204')) and not any(key.lower() == 'content-length' for key, _ in headers):
            headers.append(('Content-Length', str(len(content))))
        start_response(status, headers)
        return []
    start_response(status, headers)
    return [content]


# The WSGI environ value types copied to the script environ object - strings, numbers, and booleans
_ENVIRON_TYPES = (str, int, float)


# Helper to decode a WSGI environ string (bytes as Latin-1) as UTF-8 - a string that isn't UTF-8 is unchanged
def _environ_utf8(value):
    try:
        return value.encode('latin-1').decode('utf-8')
    except UnicodeError:
        return value


# Helper to validate a WSGI response object - returns (status, headers, content bytes)
def _wsgi_response(response):
    status = response.get('status') if isinstance(response, dict) else None
    if not isinstance(status, str) or not _R_STATUS.fullmatch(status):
        raise ValueError('Invalid response status')

    # Headers - a header name is an HTTP token, and a header value is Latin-1 text without line breaks
    headers = response.get('headers')
    if headers is None:
        headers = []
    if not isinstance(headers, list):
        raise ValueError('Invalid response headers')
    for header in headers:
        if not isinstance(header, list) or len(header) != 2 or not isinstance(header[0], str) or not isinstance(header[1], str) or \
           not _R_HEADER_NAME.fullmatch(header[0]) or not _R_HEADER_VALUE.fullmatch(header[1]):
            raise ValueError('Invalid response headers')

    # Content - an integer byte value array converts directly, and other numbers are checked one by one
    content = response.get('content')
    if content is None:
        content_bytes = b''
    elif isinstance(content, str):
        content_bytes = string_encode_utf8(content)
    elif isinstance(content, list) and set(map(type, content)) <= {int}:
        try:
            content_bytes = bytes(content)
        except ValueError:
            raise ValueError('Invalid response content') from None
    elif isinstance(content, list) and \
         all(isinstance(byte, (int, float)) and not isinstance(byte, bool) and 0 <= byte <= 255 and byte == int(byte)
             for byte in content):
        content_bytes = bytes(int(byte) for byte in content)
    else:
        raise ValueError('Invalid response content')

    return status, [tuple(header) for header in headers], content_bytes


# The response status (e.g. "200 OK"), header name, and header value regular expressions
_R_STATUS = re.compile(r'[1-9][0-9]{2} [\t\x20-\x7e\x80-\xff]*')
_R_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_R_HEADER_VALUE = re.compile(r'[\t\x20-\x7e\x80-\xff]*')


# Helper to create the script execution options
def _script_options(globals_, fetch_fn, url_fn, log_fn, debug, max_statements):
    options = {
        'debug': debug,
        'fetchFn': fetch_fn,
        'globals': globals_,
        'logFn': log_fn,
        'statementCount': 0,
        'urlFn': url_fn
    }
    if max_statements is not None:
        options['maxStatements'] = max_statements
    return options


# The application fetch function - reads GET requests from the application source map
def _fetch_src(src, fetch_fn, request):
    if request.get('body') is None and request.get('method') in (None, 'GET'):
        src_path = posixpath.normpath(PurePath(request['url']).as_posix()).lstrip('/')
        content = src.get(src_path)
        if content is not None:
            if request.get('binary', False):
                return string_encode_utf8(content) if isinstance(content, str) else content
            return content.decode('utf-8') if isinstance(content, bytes) else content
    return fetch_fn(request) if fetch_fn is not None else None
