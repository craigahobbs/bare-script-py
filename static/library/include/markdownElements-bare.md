The "markdownElements.bare" include library provides functions for converting a parsed
[Markdown model](model.html#var.vName='Markdown') into an
[element model](https://github.com/craigahobbs/element-model#readme) for rendering in the browser.

To render Markdown content as HTML elements, first parse the Markdown text with
[markdownParse](#var.vGroup='markdownParser.bare'&markdownparse), then generate the element model:

~~~ bare-script
include <markdownParser.bare>
include <markdownElements.bare>

markdown = markdownParse('# Hello, World!', '', 'This is a paragraph with **bold** text.')
elements = markdownElements(markdown)
elementModelRender(elements)
~~~

You can pass an options object to control rendering behavior. For example, to generate header IDs
for navigation anchors:

~~~ bare-script
options = {'headerIds': true}
elements = markdownElements(markdown, options)
~~~

To modify URLs (e.g., to resolve relative paths), provide a URL modifier function:

~~~ bare-script
function myURLFn(url):
    if stringStartsWith(url, 'http'):
        return url
    endif
    return 'https://example.com/' + url
endfunction

options = {'urlFn': myURLFn}
elements = markdownElements(markdown, options)
~~~

To add copy-to-clipboard links to code blocks, use the `copyLinks` option:

~~~ bare-script
options = {'copyLinks': true}
elements = markdownElements(markdown, options)
~~~

For applications that include asynchronous code block renderers, use the
[markdownElementsAsync](#var.vGroup='markdownElements.bare'&markdownelementsasync) function instead.
