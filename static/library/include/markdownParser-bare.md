The "markdownParser.bare" include library provides a function for parsing Markdown text into a
[Markdown model](model.html#var.vName='Markdown'). The resulting model can be rendered to HTML
using [markdownElements.bare](#var.vGroup='markdownElements.bare'&_top).

Parse a Markdown string into a model:

~~~ bare-script
include <markdownParser.bare>

markdown = markdownParse('# Hello, World!', '', 'This is a paragraph.')
~~~

You can pass multiple strings or arrays of strings — they are joined as lines of Markdown text:

~~~ bare-script
lines = ['## Section', '', '- Item 1', '- Item 2']
markdown = markdownParse(lines)
~~~

The parsed model can be passed directly to
[markdownElements](#var.vGroup='markdownElements.bare'&markdownelements) for rendering:

~~~ bare-script
include <markdownElements.bare>

elements = markdownElements(markdown)
elementModelRender(elements)
~~~

The Markdown parser supports standard CommonMark features including headings, paragraphs, bold,
italic, strikethrough, inline code, fenced code blocks, links, images, ordered and unordered lists,
block quotes, horizontal rules, and tables.

The parsed [Markdown model](model.html#var.vName='Markdown') is a structured object you can inspect
and manipulate programmatically. For example, to extract the title:

~~~ bare-script
include <markdown.bare>

title = markdownTitle(markdown)
~~~
