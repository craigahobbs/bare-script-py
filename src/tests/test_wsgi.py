# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import unittest.mock

from bare_script.wsgi import wsgi_application, wsgi_load_source, wsgi_load_statics


# Helper to make a WSGI request - returns (status, headers, content)
def _request(application, method, path, content=b'', environ=None):
    request_environ = {
        'REQUEST_METHOD': method,
        'PATH_INFO': path,
        'QUERY_STRING': '',
        'CONTENT_LENGTH': str(len(content)),
        'wsgi.input': BytesIO(content),
        'wsgi.version': (1, 0)
    }
    if environ is not None:
        request_environ.update(environ)
    start_response = unittest.mock.Mock()
    response_content = b''.join(application(request_environ, start_response))
    start_response.assert_called_once()
    status, headers = start_response.call_args.args
    return status, headers, response_content


# Helper to create a WSGI application from a single application script
def _application(script, **kwargs):
    return wsgi_application({'myapp.bare': script}, 'myapp.bare', 'myappApplication', **kwargs)


class TestWsgi(unittest.TestCase):

    def test_wsgi_application(self):
        application = _application('''\
function myappApplication(environ):
    return { \\
        'status': '200 OK', \\
        'headers': [['Content-Type', 'text/plain']], \\
        'content': 'Hello, ' + objectGet(environ, 'REQUEST_METHOD') + ' ' + objectGet(environ, 'PATH_INFO') + \\
            ' ' + jsonStringify(objectGet(environ, 'wsgi.input')) + ' ' + objectHas(environ, 'wsgi.version') \\
    }
endfunction
''')
        self.assertEqual(
            _request(application, 'GET', '/hello'),
            ('200 OK', [('Content-Type', 'text/plain')], b'Hello, GET /hello "" false')
        )
        self.assertEqual(
            _request(application, 'POST', '/hello', b'{"a": 1}'),
            ('200 OK', [('Content-Type', 'text/plain')], b'Hello, POST /hello "{\\"a\\": 1}" false')
        )
        self.assertEqual(
            _request(application, 'HEAD', '/hello'),
            ('200 OK', [('Content-Type', 'text/plain'), ('Content-Length', str(len(b'Hello, HEAD /hello "" false')))], b'')
        )


    def test_wsgi_application_head_content_length(self):
        application = _application('''\
function myappApplication():
    return {'status': '200 OK', 'headers': [['content-length', '3']], 'content': 'Hello'}
endfunction
''')

        # The application's content length header is kept
        self.assertEqual(_request(application, 'HEAD', '/'), ('200 OK', [('content-length', '3')], b''))


    def test_wsgi_application_head_no_content(self):
        application = _application('''\
function myappApplication(environ):
    return {'status': objectGet(environ, 'PATH_INFO') + ' Status'}
endfunction
''')

        # A status that never has content (1xx and 204) has no content length
        self.assertEqual(_request(application, 'HEAD', '204'), ('204 Status', [], b''))
        self.assertEqual(_request(application, 'HEAD', '103'), ('103 Status', [], b''))
        self.assertEqual(_request(application, 'HEAD', '200'), ('200 Status', [('Content-Length', '0')], b''))


    def test_wsgi_application_path_info(self):
        application = _application('''\
function myappApplication(environ):
    return {'status': '200 OK', 'content': objectGet(environ, 'PATH_INFO', 'none')}
endfunction
''')

        # The server decodes the path's percent-encoding as Latin-1 - the path is UTF-8
        self.assertEqual(_request(application, 'GET', '/caf\xc3\xa9/100%'), ('200 OK', [], '/café/100%'.encode('utf-8')))

        # A path that isn't UTF-8, or isn't Latin-1, is unchanged
        self.assertEqual(_request(application, 'GET', '/\xff'), ('200 OK', [], '/\xff'.encode('utf-8')))
        self.assertEqual(_request(application, 'GET', '/\u20ac'), ('200 OK', [], '/\u20ac'.encode('utf-8')))

        # No path
        self.assertEqual(_request(application, 'GET', None), ('200 OK', [], b'none'))


    def test_wsgi_application_api(self):
        src = {
            Path('myapp.bare'): '''\
include <schemaParser.bare>
include <wsgi.bare>
include 'lib/util.bare'

myappTypes = schemaParse( \\
    'action myappDouble', \\
    '    input', \\
    '        float value', \\
    '    output', \\
    '        float answer' \\
)

function myappDouble(request):
    return {'answer': utilDouble(objectGet(request, 'value'))}
endfunction

myappApplication = wsgiCreateAPIApplication(myappTypes, { \\
    'requests': [ \\
        {'type': 'action', 'name': 'myappDouble', 'path': '/double'}, \\
        {'type': 'request', 'path': '/index.html', 'function': wsgiStatic(systemFetch('frontend/index.html'))}, \\
        {'type': 'request', 'path': '/app.css', 'function': wsgiStatic(systemFetch('static/app.css'))}, \\
        {'type': 'request', 'path': '/data.bin', 'function': wsgiStatic(systemFetch({'url': 'data.bin', 'binary': true}))}, \\
        {'type': 'request', 'path': '/text.bin', 'function': wsgiStatic(systemFetch({'url': 'frontend/index.html', 'binary': true}))} \\
    ] \\
})
''',
            'lib/util.bare': '''\
function utilDouble(value):
    return 2 * value
endfunction
''',
            'frontend/index.html': '<html></html>',
            'static/app.css': b'body {}',
            'data.bin': b'\x00\x80\xff'
        }
        application = wsgi_application(src, 'myapp.bare', 'myappApplication')
        self.assertEqual(
            _request(application, 'POST', '/double', b'{"value": 3}'),
            ('200 OK', [('Content-Type', 'application/json')], b'{"answer":6}')
        )
        self.assertEqual(
            _request(application, 'GET', '/index.html'),
            ('200 OK', [('Content-Type', 'text/html; charset=utf-8')], b'<html></html>')
        )
        self.assertEqual(
            _request(application, 'GET', '/app.css'),
            ('200 OK', [('Content-Type', 'text/css; charset=utf-8')], b'body {}')
        )
        self.assertEqual(
            _request(application, 'GET', '/data.bin'),
            ('200 OK', [('Content-Type', 'application/octet-stream')], b'\x00\x80\xff')
        )
        self.assertEqual(
            _request(application, 'GET', '/text.bin'),
            ('200 OK', [('Content-Type', 'application/octet-stream')], b'<html></html>')
        )
        self.assertEqual(
            _request(application, 'GET', '/unknown'),
            ('404 Not Found', [('Content-Type', 'text/plain; charset=utf-8')], b'404 Not Found')
        )


    def test_wsgi_application_globals(self):
        src = {
            'myapp.bare': b'''\
counter = 0

function myappApplication():
    systemGlobalSet('counter', counter + 1)
    return {'status': '200 OK', 'content': myappMessage + ' ' + counter}
endfunction
'''
        }
        application = wsgi_application(src, 'myapp.bare', 'myappApplication', globals_={'myappMessage': 'Hello'})
        self.assertEqual(_request(application, 'GET', '/'), ('200 OK', [], b'Hello 1'))
        self.assertEqual(_request(application, 'GET', '/'), ('200 OK', [], b'Hello 1'))


    def test_wsgi_application_script_name(self):
        src = {'myapp.bare': 'function myappApplication():\n    return {\'status\': \'200 OK\', \'content\': \'Hello\'}\nendfunction\n'}

        # The script name is normalized like the source map's paths
        for script_name in ('./myapp.bare', Path('myapp.bare')):
            application = wsgi_application(src, script_name, 'myappApplication')
            self.assertEqual(_request(application, 'GET', '/'), ('200 OK', [], b'Hello'))


    def test_wsgi_application_unknown_script(self):
        with self.assertRaises(ValueError) as cm_exc:
            wsgi_application({'myapp.bare': ''}, 'other.bare', 'myappApplication')
        self.assertEqual(str(cm_exc.exception), 'Unknown application script "other.bare"')


    def test_wsgi_application_unknown_function(self):
        with self.assertRaises(ValueError) as cm_exc:
            wsgi_application({'myapp.bare': 'myappApplication = 1'}, 'myapp.bare', 'myappApplication')
        self.assertEqual(str(cm_exc.exception), 'Unknown application function "myappApplication"')


    def test_wsgi_application_fetch(self):
        src = {
            'myapp.bare': '''\
function myappApplication():
    return {'status': '200 OK', 'content': jsonStringify([ \\
        systemFetch('/other.txt'), \\
        systemFetch('http://example.com/remote.txt'), \\
        systemFetch({'url': 'other.txt', 'body': 'write'}), \\
        systemFetch({'url': 'other.txt', 'method': 'GET'}), \\
        systemFetch({'url': 'other.txt', 'method': 'PUT', 'body': 'put'}) \\
    ])}
endfunction
''',
            'other.txt': 'Other'
        }
        fetch_fn = unittest.mock.Mock(return_value='Remote')
        application = wsgi_application(src, 'myapp.bare', 'myappApplication', fetch_fn=fetch_fn)
        self.assertEqual(_request(application, 'GET', '/'), ('200 OK', [], b'["Other","Remote","Remote","Other","Remote"]'))
        self.assertEqual(fetch_fn.call_args_list, [
            unittest.mock.call({'url': 'http://example.com/remote.txt'}),
            unittest.mock.call({'url': 'other.txt', 'body': 'write'}),
            unittest.mock.call({'url': 'other.txt', 'method': 'PUT', 'body': 'put'})
        ])

        # No fetch function
        application = wsgi_application(src, 'myapp.bare', 'myappApplication', fetch_fn=None)
        self.assertEqual(_request(application, 'GET', '/'), ('200 OK', [], b'["Other",null,null,"Other",null]'))


    def test_wsgi_application_max_statements(self):
        application = _application('''\
function myappApplication():
    ix = 0
    while ix < 100:
        ix = ix + 1
    endwhile
    return {'status': '200 OK'}
endfunction
''', max_statements=50)
        wsgi_errors = StringIO()
        self.assertEqual(
            _request(application, 'GET', '/', environ={'wsgi.errors': wsgi_errors}),
            ('500 Internal Server Error', [('Content-Type', 'application/json')], b'{"error":"UnexpectedError"}')
        )
        self.assertEqual(
            wsgi_errors.getvalue(),
            'BareScript WSGI application error: myapp.bare:5: Exceeded maximum script statements (50)\n'
        )


    def test_wsgi_application_log(self):
        src = {
            'myapp.bare': '''\
systemLog('Starting')

function myappApplication():
    systemLog('Request')
    systemLogDebug('Request debug')
    return {'status': '200 OK'}
endfunction
'''
        }
        with unittest.mock.patch('sys.stderr', new_callable=StringIO) as stderr:
            application = wsgi_application(src, 'myapp.bare', 'myappApplication', debug=True)
        self.assertEqual(stderr.getvalue(), 'Starting\n')
        wsgi_errors = StringIO()
        self.assertEqual(_request(application, 'GET', '/', environ={'wsgi.errors': wsgi_errors}), ('200 OK', [], b''))
        self.assertEqual(wsgi_errors.getvalue(), 'Request\nRequest debug\n')

        # No wsgi.errors
        self.assertEqual(_request(application, 'GET', '/'), ('200 OK', [], b''))


    def test_wsgi_application_api_surrogate(self):
        application = _application('''\
include <schemaParser.bare>
include <wsgi.bare>

myappTypes = schemaParse('action myappAction', '    input', '        int value')

function myappAction():
endfunction

myappApplication = wsgiCreateAPIApplication(myappTypes, {'requests': [{'type': 'action', 'name': 'myappAction'}]})
''')

        # A lone surrogate in a response (here, echoed by the error message) is the replacement character
        self.assertEqual(
            _request(application, 'POST', '/myappAction', b'{"value": "\\ud800"}'),
            (
                '400 Bad Request',
                [('Content-Type', 'application/json')],
                '{"error":"InvalidInput","member":"value","message":"Invalid value \\"\ufffd\\" (type \\"string\\") '
                'for member \\"value\\", expected type \\"int\\" (content)"}'.encode('utf-8')
            )
        )


    def test_wsgi_application_api_unexpected_error(self):
        application = _application('''\
include <schemaParser.bare>
include <wsgi.bare>

myappTypes = schemaParse('action myappFail')

function myappFail():
    return myappUndefinedFunction()
endfunction

myappApplication = wsgiCreateAPIApplication(myappTypes, {'requests': [{'type': 'action', 'name': 'myappFail'}]})
''')

        # A failed action responds with the "UnexpectedError" error, and the failure is logged
        wsgi_errors = StringIO()
        self.assertEqual(
            _request(application, 'POST', '/myappFail', environ={'wsgi.errors': wsgi_errors}),
            ('500 Internal Server Error', [('Content-Type', 'application/json')], b'{"error":"UnexpectedError"}')
        )
        self.assertEqual(
            wsgi_errors.getvalue(), 'BareScript WSGI application error: myapp.bare:7: Undefined function "myappUndefinedFunction"\n'
        )


    def test_wsgi_application_response(self):
        application = _application('''\
function myappApplication(environ):
    return jsonParse(objectGet(environ, 'wsgi.input'))
endfunction
''')

        # Valid responses
        self.assertEqual(
            _request(application, 'POST', '/', b'{"status": "200 OK", "headers": [["A", "1"], ["A", "2"]], "content": "Hello"}'),
            ('200 OK', [('A', '1'), ('A', '2')], b'Hello')
        )
        self.assertEqual(
            _request(application, 'POST', '/', b'{"status": "404 ", "headers": [["X-A_b", "caf\\u00e9\\t1"]]}'),
            ('404 ', [('X-A_b', 'caf\u00e9\t1')], b'')
        )
        self.assertEqual(
            _request(application, 'POST', '/', b'{"status": "200 OK", "content": [0, 128, 255]}'),
            ('200 OK', [], b'\x00\x80\xff')
        )
        self.assertEqual(
            _request(application, 'POST', '/', b'{"status": "200 OK", "content": [0, 128, 255, 1.0]}'),
            ('200 OK', [], b'\x00\x80\xff\x01')
        )

        # Invalid responses
        for response, error in [
            (b'null', 'Invalid response status'),
            (b'{}', 'Invalid response status'),
            (b'{"status": 200}', 'Invalid response status'),
            (b'{"status": "OK"}', 'Invalid response status'),
            (b'{"status": "200"}', 'Invalid response status'),
            (b'{"status": "200 OK\\r\\nX-Injected: 1"}', 'Invalid response status'),
            (b'{"status": "200 \\u20ac"}', 'Invalid response status'),
            (b'{"status": "200 OK", "headers": {}}', 'Invalid response headers'),
            (b'{"status": "200 OK", "headers": ["A"]}', 'Invalid response headers'),
            (b'{"status": "200 OK", "headers": [["A"]]}', 'Invalid response headers'),
            (b'{"status": "200 OK", "headers": [["A", 1]]}', 'Invalid response headers'),
            (b'{"status": "200 OK", "headers": [["A B", "1"]]}', 'Invalid response headers'),
            (b'{"status": "200 OK", "headers": [["", "1"]]}', 'Invalid response headers'),
            (b'{"status": "200 OK", "headers": [["A", "1\\r\\nX-Injected: 1"]]}', 'Invalid response headers'),
            (b'{"status": "200 OK", "headers": [["A", "\\u20ac"]]}', 'Invalid response headers'),
            (b'{"status": "200 OK", "content": {}}', 'Invalid response content'),
            (b'{"status": "200 OK", "content": [256]}', 'Invalid response content'),
            (b'{"status": "200 OK", "content": [-1]}', 'Invalid response content'),
            (b'{"status": "200 OK", "content": [1.5]}', 'Invalid response content'),
            (b'{"status": "200 OK", "content": ["a"]}', 'Invalid response content'),
            (b'{"status": "200 OK", "content": [true]}', 'Invalid response content')
        ]:
            wsgi_errors = StringIO()
            self.assertEqual(
                _request(application, 'POST', '/', response, environ={'wsgi.errors': wsgi_errors}),
                ('500 Internal Server Error', [('Content-Type', 'application/json')], b'{"error":"UnexpectedError"}')
            )
            self.assertEqual(wsgi_errors.getvalue(), f'BareScript WSGI application error: {error}\n')


    def test_wsgi_application_content_length(self):
        application = _application('''\
function myappApplication(environ):
    return {'status': '200 OK', 'content': objectGet(environ, 'wsgi.input')}
endfunction
''')
        self.assertEqual(_request(application, 'POST', '/', b'abc', environ={'CONTENT_LENGTH': '2'}), ('200 OK', [], b'ab'))
        self.assertEqual(_request(application, 'POST', '/', b'abc', environ={'CONTENT_LENGTH': ''}), ('200 OK', [], b''))
        self.assertEqual(_request(application, 'POST', '/', b'abc', environ={'CONTENT_LENGTH': '0'}), ('200 OK', [], b''))

        # Without a content length (e.g. a chunked request), the input is read to its end if the server terminates it
        self.assertEqual(
            _request(application, 'POST', '/', b'abc', environ={'CONTENT_LENGTH': '', 'wsgi.input_terminated': True}),
            ('200 OK', [], b'abc')
        )
        self.assertEqual(_request(application, 'POST', '/', b'\xff', environ={'CONTENT_LENGTH': '1'}), ('200 OK', [], b'\xef\xbf\xbd'))
        self.assertEqual(
            _request(application, 'POST', '/', b'abc', environ={'CONTENT_LENGTH': 'abc'}),
            ('500 Internal Server Error', [('Content-Type', 'application/json')], b'{"error":"UnexpectedError"}')
        )


    def test_wsgi_load(self):
        with TemporaryDirectory() as root_dir:
            for path, content in (
                ('backend/myapp.bare', b'backend'),
                ('frontend/index.html', b'index'),
                ('frontend/images/logo.png', b'\x89PNG\xff'),
                ('frontend/sub/index.html', b'sub index'),
                ('build/markdown-up/app.css', b'css'),

                # Hidden files and directories are skipped
                ('backend/.env', b'secret'),
                ('frontend/.DS_Store', b'hidden'),
                ('frontend/.git/config', b'hidden'),
                ('build/markdown-up/.hidden/app.css', b'hidden')
            ):
                file_path = Path(root_dir, path)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(content)

            # Source - a missing directory is skipped
            self.assertEqual(wsgi_load_source(root_dir, ('backend', 'frontend', 'missing')), {
                'backend/myapp.bare': b'backend',
                'frontend/images/logo.png': b'\x89PNG\xff',
                'frontend/index.html': b'index',
                'frontend/sub/index.html': b'sub index'
            })

            # Statics - an index file is also served at its directory's URL path
            self.assertEqual(wsgi_load_statics(Path(root_dir), {'/': 'frontend', '/markdown-up/': 'build/markdown-up'}), {
                '/': 'frontend/index.html',
                '/images/logo.png': 'frontend/images/logo.png',
                '/index.html': 'frontend/index.html',
                '/markdown-up/app.css': 'build/markdown-up/app.css',
                '/sub/': 'frontend/sub/index.html',
                '/sub/index.html': 'frontend/sub/index.html'
            })

            # No index files, and a missing directory is skipped
            self.assertEqual(wsgi_load_statics(root_dir, {'/': 'frontend', '/missing/': 'missing'}, index=None), {
                '/images/logo.png': 'frontend/images/logo.png',
                '/index.html': 'frontend/index.html',
                '/sub/index.html': 'frontend/sub/index.html'
            })

            # A URL prefix without a trailing slash gets one
            self.assertEqual(wsgi_load_statics(root_dir, {'/static': 'build/markdown-up'}), {
                '/static/app.css': 'build/markdown-up/app.css'
            })
