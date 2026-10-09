# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import concurrent.futures
import datetime
import unittest

from bare_script import barescript_parse_expression, barescript_parse_script
from bare_script.include import SchemaParserError, SchemaValidationError, barescript_lint_unbound_globals, barescript_type_model, \
    barescript_validate_expression, barescript_validate_script, base64_decode, base64_encode, data_aggregate, \
    data_calculated_field, data_filter, data_join, data_line_chart_elements, data_line_chart_validate, data_parse_csv, data_sort, \
    data_table_elements, data_table_markdown, data_table_validate, data_top, data_validate, element_model_to_string, \
    element_model_validate, gzip_compress, gzip_uncompress, hash_equal, hash_hex, hash_hmac_sha256, hash_sha256, include_set_log_fn, \
    markdown_elements, markdown_escape, markdown_header_id, markdown_paragraph_text, markdown_parse, markdown_title, \
    markdown_to_string, markdown_validate, qrcode_elements, qrcode_matrix, schema_doc_markdown, schema_get_enum_values, \
    schema_get_referenced_types, schema_get_struct_members, schema_parse, schema_type_model, schema_type_model_validate, \
    schema_validate, tar_create, tar_extract, url_decode_component, url_decode_query_string, url_encode, url_encode_component, \
    url_encode_query_string
from bare_script.library import SCRIPT_FUNCTIONS


class TestInclude(unittest.TestCase):

    # The include library stubs share one globals dict - concurrent calls must not interfere
    def test_include_threads(self):
        types = schema_parse('''\
# A test struct
struct TestStruct
    int a
''')
        data = [{'a': 1, 'b': 2}, {'a': 1, 'b': 4}]
        aggregation = {'categories': ['a'], 'measures': [{'field': 'b', 'function': 'sum'}]}

        def run(unused_ix):
            return (
                schema_validate(types, 'TestStruct', {'a': 5}),
                markdown_parse('# Title\n\nSome *text*'),
                data_aggregate(data, aggregation)
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(run, range(8)))
        self.assertListEqual(results, [run(0)] * 8)
        self.assertListEqual(results[0][2], [{'a': 1, 'b': 6}])

    def test_include_set_log_fn(self):
        data = [{'a': 1, 'b': 2}, {'a': 1, 'b': 4}]
        logs = []
        try:
            include_set_log_fn(logs.append)
            self.assertIsNone(data_aggregate(data, {'invalid': 'model'}))
            self.assertListEqual(logs, [
                'schema.bare: Required member "measures" missing',
                'data.bare: dataAggregate - invalid aggregation model'
            ])

            # Disable logging
            include_set_log_fn(None)
            self.assertIsNone(data_aggregate(data, {'invalid': 'model'}))
            self.assertListEqual(logs, [
                'schema.bare: Required member "measures" missing',
                'data.bare: dataAggregate - invalid aggregation model'
            ])
        finally:
            include_set_log_fn(None)


    def test_barescript_lint_unbound_globals(self):
        script = barescript_parse_script('''\
# Double a number
function double(n):
    return n * 2
endfunction

return N + ' times 2 is ' + double(N)
''')
        self.assertListEqual(barescript_lint_unbound_globals(script), ['N'])
        self.assertListEqual(barescript_lint_unbound_globals(script, {'N': 10}), [])


    def test_barescript_lint_unbound_globals_expression(self):
        expr = barescript_parse_expression('a + mathMax(b, 1)')
        self.assertListEqual(barescript_lint_unbound_globals(expr), ['a', 'b', 'mathMax'])
        self.assertListEqual(barescript_lint_unbound_globals(expr, SCRIPT_FUNCTIONS), ['a', 'b'])


    def test_barescript_type_model(self):
        type_model = barescript_type_model()
        self.assertIn('BareScript', type_model)
        self.assertIn('ScriptStatement', type_model)
        self.assertIn('Expression', type_model)


    def test_barescript_validate_expression(self):
        expr = {'number': 1}
        self.assertDictEqual(barescript_validate_expression(expr), expr)


    def test_barescript_validate_expression_error(self):
        with self.assertRaises(SchemaValidationError) as cm_exc:
            barescript_validate_expression({})
        self.assertEqual(str(cm_exc.exception), 'Invalid value {} (type "object"), expected type "Expression"')
        self.assertIsNone(cm_exc.exception.member_fqn)


    def test_barescript_validate_script(self):
        script = {'statements': []}
        self.assertDictEqual(barescript_validate_script(script), script)


    def test_barescript_validate_script_error(self):
        with self.assertRaises(SchemaValidationError) as cm_exc:
            barescript_validate_script({})
        self.assertEqual(str(cm_exc.exception), 'Required member "statements" missing')
        self.assertIsNone(cm_exc.exception.member_fqn)


    def test_data_aggregate(self):
        data = [{'a': 1, 'b': 2}, {'a': 1, 'b': 4}]
        self.assertListEqual(
            data_aggregate(data, {'categories': ['a'], 'measures': [{'field': 'b', 'function': 'sum'}]}),
            [{'a': 1, 'b': 6}]
        )


    def test_data_calculated_field(self):
        self.assertListEqual(data_calculated_field([{'a': 2}], 'c', 'a * 2'), [{'a': 2, 'c': 4}])


    def test_data_filter(self):
        self.assertListEqual(data_filter([{'a': 1}, {'a': 3}], 'a > aMin', {'aMin': 1}), [{'a': 3}])


    def test_data_join(self):
        self.assertListEqual(data_join([{'a': 1, 'b': 2}], [{'a': 1, 'c': 3}], 'a'), [{'a': 1, 'b': 2, 'a2': 1, 'c': 3}])


    def test_data_parse_csv(self):
        self.assertListEqual(data_parse_csv('a,b\n1,2\n3,4'), [{'a': 1, 'b': 2}, {'a': 3, 'b': 4}])


    def test_data_sort(self):
        self.assertListEqual(data_sort([{'a': 1}, {'a': 3}], [['a', True]]), [{'a': 3}, {'a': 1}])


    def test_data_top(self):
        self.assertListEqual(data_top([{'a': 1}, {'a': 2}, {'a': 3}], 2), [{'a': 1}, {'a': 2}])


    def test_data_validate(self):
        self.assertDictEqual(data_validate([{'a': 1, 'b': 'x'}]), {'a': 'number', 'b': 'string'})


    def test_data_validate_error(self):
        with self.assertRaises(SchemaValidationError) as cm_exc:
            data_validate([{'a': 1}, {'a': '2'}])
        self.assertEqual(str(cm_exc.exception), 'Invalid "a" field value "2", expected type number')
        self.assertIsNone(cm_exc.exception.member_fqn)


    def test_data_line_chart_elements(self):
        data = [{'a': 1, 'b': 2}, {'a': 2, 'b': 3}]
        elements = data_line_chart_elements(data, {'x': 'a', 'y': ['b'], 'width': 100, 'height': 50})
        self.assertEqual(elements['svg'], 'svg')


    def test_data_line_chart_validate(self):
        self.assertDictEqual(data_line_chart_validate({'x': 'a', 'y': ['b']}), {'x': 'a', 'y': ['b']})


    def test_data_line_chart_validate_error(self):
        with self.assertRaises(SchemaValidationError) as cm_exc:
            data_line_chart_validate({'x': 1, 'y': ['b']})
        self.assertEqual(str(cm_exc.exception), 'Invalid value 1 (type "number") for member "x", expected type "string"')
        self.assertEqual(cm_exc.exception.member_fqn, 'x')


    def test_data_table_elements(self):
        self.assertDictEqual(data_table_elements([{'a': 1}]), {
            'html': 'table',
            'elem': [
                {'html': 'tr', 'elem': [{'html': 'th', 'attr': None, 'elem': {'text': 'a'}}]},
                {'html': 'tr', 'elem': [{'html': 'td', 'attr': None, 'elem': {'text': '1'}}]}
            ]
        })


    def test_data_table_markdown(self):
        self.assertListEqual(data_table_markdown([{'a': 1}]), ['| a |', '|---|', '| 1 |'])


    def test_data_table_validate(self):
        self.assertDictEqual(data_table_validate({'fields': ['a']}), {'fields': ['a']})


    def test_data_table_validate_error(self):
        with self.assertRaises(SchemaValidationError) as cm_exc:
            data_table_validate({'fields': 1})
        self.assertEqual(str(cm_exc.exception), 'Invalid value 1 (type "number") for member "fields", expected type "array"')
        self.assertEqual(cm_exc.exception.member_fqn, 'fields')


    def test_element_model_to_string(self):
        self.assertEqual(element_model_to_string({'html': 'div'}), '<div></div>')


    def test_element_model_validate(self):
        self.assertDictEqual(element_model_validate({'html': 'div'}), {'html': 'div'})


    def test_element_model_validate_error(self):
        with self.assertRaises(SchemaValidationError) as cm_exc:
            element_model_validate({})
        self.assertEqual(str(cm_exc.exception), 'Missing element member {}')
        self.assertIsNone(cm_exc.exception.member_fqn)


    def test_markdown_escape(self):
        self.assertEqual(markdown_escape('*text*'), '\\*text\\*')


    def test_markdown_header_id(self):
        self.assertEqual(markdown_header_id('Hello, World!'), 'hello-world')


    def test_markdown_paragraph_text(self):
        markdown = markdown_parse('# Title')
        self.assertEqual(markdown_paragraph_text(markdown['parts'][0]['paragraph']), 'Title')


    def test_markdown_title(self):
        self.assertEqual(markdown_title(markdown_parse('# Title')), 'Title')


    def test_markdown_validate(self):
        markdown = {'parts': [{'paragraph': {'style': 'h1', 'spans': [{'text': 'Title'}]}}]}
        self.assertDictEqual(markdown_validate(markdown), markdown)


    def test_markdown_validate_error(self):
        with self.assertRaises(SchemaValidationError) as cm_exc:
            markdown_validate({'parts': 1})
        self.assertEqual(str(cm_exc.exception), 'Invalid value 1 (type "number") for member "parts", expected type "array"')
        self.assertEqual(cm_exc.exception.member_fqn, 'parts')


    def test_markdown_elements(self):
        markdown = markdown_parse('# Title')
        self.assertListEqual(markdown_elements(markdown), [{'html': 'h1', 'attr': None, 'elem': [{'text': 'Title'}]}])


    def test_markdown_parse(self):
        self.assertDictEqual(markdown_parse('# Title'), {'parts': [{'paragraph': {'spans': [{'text': 'Title'}], 'style': 'h1'}}]})


    def test_markdown_to_string(self):
        self.assertEqual(markdown_to_string(markdown_parse('#  Title\n\nSome\ntext')), '# Title\n\nSome text\n')


    def test_markdown_to_string_wrap_width(self):
        self.assertEqual(markdown_to_string(markdown_parse('aaa bbb ccc'), 7), 'aaa bbb\nccc\n')


    def test_markdown_to_string_ref_count(self):
        self.assertEqual(
            markdown_to_string(markdown_parse('[a](u.html) [b](u.html)'), 0, 2),
            '[a][1] [b][1]\n\n[1]: u.html\n'
        )


    def test_qrcode_elements(self):
        elements = qrcode_elements('hello', 100)
        self.assertEqual(elements['svg'], 'svg')
        self.assertDictEqual(elements['attr'], {'width': 100, 'height': 100})


    def test_qrcode_matrix(self):
        matrix = qrcode_matrix('hello')
        self.assertEqual(len(matrix), 25)
        self.assertEqual(matrix[0][0], 1)


    def test_schema_get_enum_values(self):
        types = schema_parse('enum E\n    A\n    B')
        self.assertListEqual(schema_get_enum_values(types, types['E']['enum']), [{'name': 'A'}, {'name': 'B'}])


    def test_schema_get_referenced_types(self):
        types = schema_parse('# My struct\nstruct S\n    int a')
        self.assertDictEqual(schema_get_referenced_types(types, 'S'), {
            'S': {'struct': {'name': 'S', 'doc': ['My struct'], 'members': [{'name': 'a', 'type': {'builtin': 'int'}}]}}
        })


    def test_schema_get_struct_members(self):
        types = schema_parse('struct S\n    int a')
        self.assertListEqual(schema_get_struct_members(types, types['S']['struct']), [{'name': 'a', 'type': {'builtin': 'int'}}])


    def test_schema_doc_markdown(self):
        types = schema_parse('# My struct\nstruct S\n    int a')
        self.assertListEqual(schema_doc_markdown(types, 'S'), [
            '# struct S',
            '',
            'My struct',
            '',
            '| Name | Type |',
            '|------|------|',
            '| a    | int  |'
        ])


    def test_schema_type_model(self):
        types = schema_type_model()
        self.assertIn('Types', types)


    def test_schema_type_model_validate(self):
        types = schema_type_model()
        self.assertDictEqual(schema_type_model_validate(types), types)


    def test_schema_type_model_validate_error(self):
        with self.assertRaises(SchemaValidationError) as cm_exc:
            schema_type_model_validate({'Bad': {'struct': {}}})
        self.assertEqual(str(cm_exc.exception), 'Required member "Bad.struct.name" missing')
        self.assertIsNone(cm_exc.exception.member_fqn)


    def test_base64_decode(self):
        self.assertListEqual(base64_decode('aGVsbG8='), [104, 101, 108, 108, 111])
        self.assertIsNone(base64_decode('!!!!'))


    def test_base64_encode(self):
        self.assertEqual(base64_encode([104, 101, 108, 108, 111]), 'aGVsbG8=')
        self.assertEqual(base64_encode('hello'), 'aGVsbG8=')
        self.assertIsNone(base64_encode([256]))


    def test_gzip_compress(self):
        bytes_ = list('hello hello hello'.encode('utf-8'))
        compressed = gzip_compress(bytes_)
        self.assertListEqual(compressed[:3], [31, 139, 8])
        self.assertListEqual(gzip_uncompress(compressed), bytes_)
        self.assertListEqual(gzip_uncompress(gzip_compress(bytes_, 0)), bytes_)
        self.assertListEqual(gzip_uncompress(gzip_compress('hello hello hello')), bytes_)
        self.assertIsNone(gzip_compress(bytes_, 10))


    def test_gzip_uncompress(self):
        self.assertListEqual(gzip_uncompress(base64_decode('H4sIAAAAAAAC/8tIzcnJBwCGphA2BQAAAA==')), [104, 101, 108, 108, 111])
        self.assertIsNone(gzip_uncompress([1, 2, 3]))


    def test_hash_equal(self):
        self.assertIs(hash_equal('abc', [97, 98, 99]), True)
        self.assertIs(hash_equal('abc', 'abd'), False)
        self.assertIsNone(hash_equal(None, 'abc'))


    def test_hash_hex(self):
        self.assertEqual(hash_hex([0, 15, 16, 255]), '000f10ff')
        self.assertIsNone(hash_hex([256]))


    def test_hash_hmac_sha256(self):
        self.assertEqual(
            hash_hex(hash_hmac_sha256('Jefe', 'what do ya want for nothing?')),
            '5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843'
        )
        self.assertIsNone(hash_hmac_sha256(None, 'message'))


    def test_hash_sha256(self):
        self.assertEqual(hash_hex(hash_sha256('abc')), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
        self.assertEqual(len(hash_sha256([0, 128, 255])), 32)
        self.assertIsNone(hash_sha256(None))


    def test_tar_create(self):
        files = [{'name': 'hello.txt', 'bytes': [104, 105]}]
        tar_bytes = tar_create(files)
        self.assertEqual(len(tar_bytes), 2048)
        self.assertListEqual(
            tar_extract(tar_bytes), [{'name': 'hello.txt', 'bytes': [104, 105], 'mtime': datetime.datetime.fromtimestamp(0)}]
        )
        self.assertListEqual(tar_create([{'name': 'hello.txt', 'bytes': 'hi'}]), tar_bytes)
        mtime = datetime.datetime(2024, 3, 5, 12, 34, 56)
        self.assertListEqual(
            tar_extract(tar_create([{'name': 'hello.txt', 'bytes': [104, 105], 'mtime': mtime}])),
            [{'name': 'hello.txt', 'bytes': [104, 105], 'mtime': mtime}]
        )
        self.assertIsNone(tar_create([{'name': 'hello.txt'}]))


    def test_tar_extract(self):
        self.assertListEqual(tar_extract([0] * 1024), [])
        self.assertIsNone(tar_extract([1] * 512))


    def test_url_decode_component(self):
        self.assertEqual(url_decode_component('a%20b'), 'a b')


    def test_url_decode_query_string(self):
        self.assertDictEqual(url_decode_query_string('a=1&b=x%20y'), {'a': '1', 'b': 'x y'})


    def test_url_encode(self):
        self.assertEqual(url_encode('http://foo.com/a b'), 'http://foo.com/a%20b')


    def test_url_encode_component(self):
        self.assertEqual(url_encode_component('a b/c'), 'a%20b%2Fc')


    def test_url_encode_query_string(self):
        self.assertEqual(url_encode_query_string({'a': 1, 'b': 'x y'}), 'a=1&b=x%20y')


    def test_schema_parse(self):
        types = schema_parse('''\
# A test struct
struct TestStruct

    # The test member
    int a
''')
        self.assertDictEqual(types, {
            'TestStruct': {
                'struct': {
                    'name': 'TestStruct',
                    'doc': ['A test struct'],
                    'members': [
                        {'name': 'a', 'doc': ['The test member'], 'type': {'builtin': 'int'}}
                    ]
                }
            }
        })

    def test_schema_parse_error(self):
        with self.assertRaises(SchemaParserError) as cm_exc:
            schema_parse('asdf asdf')
        self.assertEqual(str(cm_exc.exception), ':1: error: Syntax error')
        self.assertListEqual(cm_exc.exception.errors, [':1: error: Syntax error'])

    def test_schema_parse_types(self):
        types = schema_parse('struct S1\n    int a')
        types2 = schema_parse('struct S2\n    S1 s1', types)
        self.assertIs(types2, types)
        self.assertDictEqual(types, {
            'S1': {
                'struct': {
                    'name': 'S1',
                    'members': [
                        {'name': 'a', 'type': {'builtin': 'int'}}
                    ]
                }
            },
            'S2': {
                'struct': {
                    'name': 'S2',
                    'members': [
                        {'name': 's1', 'type': {'user': 'S1'}}
                    ]
                }
            }
        })

    def test_schema_parse_filename(self):
        with self.assertRaises(SchemaParserError) as cm_exc:
            schema_parse('asdf asdf', None, 'test.smd')
        self.assertEqual(str(cm_exc.exception), 'test.smd:1: error: Syntax error')
        self.assertListEqual(cm_exc.exception.errors, ['test.smd:1: error: Syntax error'])

    def test_schema_parse_validate(self):
        with self.assertRaises(SchemaParserError) as cm_exc:
            schema_parse('struct S\n    Unknown a')
        self.assertEqual(str(cm_exc.exception), ':2: error: Unknown type "Unknown" from "S" member "a"')
        self.assertListEqual(cm_exc.exception.errors, [':2: error: Unknown type "Unknown" from "S" member "a"'])
        self.assertDictEqual(schema_parse('struct S\n    Unknown a', None, None, False), {
            'S': {
                'struct': {
                    'name': 'S',
                    'members': [
                        {'name': 'a', 'type': {'user': 'Unknown'}}
                    ]
                }
            }
        })

    def test_schema_validate(self):
        types = schema_parse('''\
# A test struct
struct TestStruct

    # The test member
    int a
''')
        self.assertDictEqual(schema_validate(types, 'TestStruct', {'a': 5}), {'a': 5})

    def test_schema_validate_error(self):
        types = schema_parse('''\
# A test struct
struct TestStruct

    # The test member
    int a
''')
        with self.assertRaises(SchemaValidationError) as cm_exc:
            schema_validate(types, 'TestStruct', {'a': 'abc'})
        self.assertEqual(str(cm_exc.exception), 'Invalid value "abc" (type "string") for member "a", expected type "int"')
        self.assertEqual(cm_exc.exception.member_fqn, 'a')

    def test_schema_validate_error_member_fqn(self):
        types = schema_parse('''\
# A test struct
struct TestStruct

    # The test member
    int a
''')
        with self.assertRaises(SchemaValidationError) as cm_exc:
            schema_validate(types, 'TestStruct', {'a': 'abc'}, 'test')
        self.assertEqual(str(cm_exc.exception), 'Invalid value "abc" (type "string") for member "test.a", expected type "int"')
        self.assertEqual(cm_exc.exception.member_fqn, 'test.a')
